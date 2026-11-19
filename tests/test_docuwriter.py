from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from fastapi.testclient import TestClient
import fitz

from docuwriter.config import Settings
from docuwriter.llm_client import OllamaProvider
from docuwriter.models import ContextChunk, Placeholder, ReplacementPair
from docuwriter.parser import load_context_chunks, parse_target_docx
from docuwriter.pdf_parser import load_pdf_context_chunks, parse_target_pdf
from docuwriter.retriever import BM25ContextRetriever
from docuwriter.pdf_writer import apply_replacements_to_pdf
from docuwriter.web import app
from docuwriter.writer import (
    apply_interactive_replacements_to_docx,
    apply_replacements_to_docx,
    export_tagged_template_docx,
)


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {"response": self.content}


class FakeProvider:
    def complete_batch(self, context_text, batch):
        return [
            ReplacementPair(
                item.placeholder_id, item.section_path, item.location_type,
                item.raw_tag, f"Généré pour {item.original_hint}"
            )
            for item in batch
        ], True


class DocuWriterTests(unittest.TestCase):
    def test_docx_interactive_markers_tag_export_and_final(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "blank.docx"
            tagged = root / "tagged.docx"
            final = root / "final.docx"
            document = Document()
            document.add_heading("Architecture", level=1)
            document.add_paragraph("PostgreSQL est la base de données principale.")
            document.add_paragraph("Ajouter le plan sécurité après ce texte.")
            document.add_table(rows=1, cols=2)
            document.tables[0].cell(0, 0).text = "Composant"
            document.tables[0].cell(0, 1).text = "Protocole"
            document.save(source)

            markers = [
                type("Marker", (), {})(),
            ]
            from docuwriter.models import InteractiveMarker, Placeholder
            selection = InteractiveMarker(
                "selection-1", "Architecture", "Décrire PostgreSQL",
                "", "paragraph", None, None, False, "selection",
                1, 0, 11, None,
            )
            insertion = InteractiveMarker(
                "insert-1", "Architecture", "Ajouter sécurité",
                "", "paragraph", None, None, False, "insert_after",
                2,
            )
            table = InteractiveMarker(
                "table-1", "Architecture", "Préciser le protocole",
                "", "table", None, None, False, "table_cell",
                None, None, None, (0, 0, 1),
            )
            markers = [selection, insertion, table]

            export_tagged_template_docx(source, tagged, markers)
            tagged_text = "\n".join(p.text for p in Document(tagged).paragraphs)
            tagged_text += "\n".join(
                cell.text for table_doc in Document(tagged).tables
                for row in table_doc.rows for cell in row.cells
            )
            self.assertGreaterEqual(tagged_text.count("<here>"), 3)

            placeholders = [
                Placeholder(
                    "selection-1", "Architecture", "Décrire PostgreSQL", "",
                    "paragraph", 1, None, None, None, "selection", 0, 11,
                ),
                Placeholder(
                    "insert-1", "Architecture", "Ajouter sécurité", "",
                    "paragraph", 2, None, None, None, "insert_after",
                ),
                Placeholder(
                    "table-1", "Architecture", "Préciser le protocole", "",
                    "table", None, (0, 0, 1), None, None, "table_cell",
                ),
            ]
            pairs = [
                ReplacementPair(p.placeholder_id, p.section_path, p.location_type,
                                p.raw_tag, replacement)
                for p, replacement in zip(placeholders, [
                    "Base PostgreSQL 15",
                    "Authentification OAuth2 / JWT RS256",
                    "HTTPS TLS 1.3",
                ])
            ]
            count = apply_interactive_replacements_to_docx(
                source, final, placeholders, pairs, highlight=True
            )
            self.assertEqual(count, 3)
            result = Document(final)
            text = "\n".join(p.text for p in result.paragraphs)
            text += "\n".join(
                cell.text for table_doc in result.tables
                for row in table_doc.rows for cell in row.cells
            )
            self.assertIn("Base PostgreSQL 15", text)
            self.assertIn("Authentification OAuth2 / JWT RS256", text)
            self.assertIn("HTTPS TLS 1.3", text)
            self.assertFalse(any("<here>" in p.text for p in result.paragraphs))
            yellow = any(
                run.font.highlight_color == WD_COLOR_INDEX.YELLOW
                for p in result.paragraphs for run in p.runs
            )
            self.assertTrue(yellow)
    def test_parser_headings_tables_and_multiline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "target.docx"
            document = Document()
            document.add_heading("Architecture", level=1)
            document.add_heading("Database", level=2)
            document.add_paragraph("<here>single</here> and <here>two</here>")
            document.add_paragraph("<here>multi")
            document.add_paragraph("line</here>")
            document.add_table(rows=1, cols=1).cell(0, 0).text = "<here>table</here>"
            document.save(path)
            placeholders = parse_target_docx(path)
            self.assertEqual([p.original_hint for p in placeholders], ["single", "two", "multi\nline", "table"])
            self.assertEqual(placeholders[0].section_path, "1 Architecture / 1.1 Database")
            self.assertEqual(placeholders[-1].location_type, "table")

    def test_bm25_retrieves_relevant_chunk_with_limit(self) -> None:
        chunks = [
            ContextChunk("a.docx", 0, "database migration schema"),
            ContextChunk("b.docx", 1, "unrelated cooking recipe"),
        ]
        placeholder = Placeholder("p", "Database", "migration", "<here>migration</here>", "paragraph")
        result = BM25ContextRetriever(chunks).retrieve_for_batch([placeholder], 45)
        self.assertIn("database", result)
        self.assertNotIn("cooking", result)

    def test_ollama_uses_zero_based_indices_and_filters_invalid(self) -> None:
        settings = Settings.from_env(Path.cwd())
        settings = settings.__class__(**{**settings.__dict__, "max_retries": 0})
        batch = [
            Placeholder("a", "", "a", "<here>a</here>", "paragraph"),
            Placeholder("b", "", "b", "<here>b</here>", "paragraph"),
        ]
        response = '{"replacements":[{"index":1,"replacement":"B"},{"index":1,"replacement":"dup"},{"index":2,"replacement":"bad"}]}'
        with patch("docuwriter.llm_client.requests.post", return_value=FakeResponse(response)) as post:
            pairs, first = OllamaProvider(settings).complete_batch("", batch)
        self.assertTrue(first)
        self.assertEqual([pair.placeholder_id for pair in pairs], ["b"])
        self.assertEqual(post.call_args.kwargs["json"]["format"], "json")
        self.assertIn("[0]", post.call_args.kwargs["json"]["prompt"])

    def test_writer_replaces_paragraph_and_table_and_highlights(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.docx"
            output = root / "out.docx"
            document = Document()
            document.add_paragraph("<here>paragraph</here>")
            document.add_table(rows=1, cols=1).cell(0, 0).text = "<here>table</here>"
            document.save(source)
            placeholders = parse_target_docx(source)
            pairs = [
                ReplacementPair(p.placeholder_id, p.section_path, p.location_type, p.raw_tag, "done")
                for p in placeholders
            ]
            self.assertEqual(apply_replacements_to_docx(source, output, placeholders, pairs), 2)
            result = Document(output)
            self.assertEqual(result.paragraphs[0].text, "done")
            self.assertEqual(result.tables[0].cell(0, 0).text, "done")
            self.assertEqual(result.paragraphs[0].runs[0].font.highlight_color, WD_COLOR_INDEX.YELLOW)

    def test_context_ignores_word_temporary_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Document().save(root / "valid.docx")
            Document().save(root / "~$valid.docx")
            chunks = load_context_chunks(root)
            self.assertTrue(all(chunk.source_file == "valid.docx" for chunk in chunks))

    def test_preserve_paragraph_style_and_font_on_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.docx"
            output = root / "out.docx"
            document = Document()
            paragraph = document.add_paragraph(style="Intense Quote")
            run = paragraph.add_run("<here>texte</here>")
            run.bold = True
            run.font.name = "Arial"
            document.save(source)
            placeholders = parse_target_docx(source)
            pairs = [ReplacementPair(
                placeholders[0].placeholder_id, "", "paragraph",
                placeholders[0].raw_tag, "remplacé"
            )]
            apply_replacements_to_docx(source, output, placeholders, pairs, highlight=False)
            result = Document(output)
            replacement = result.paragraphs[0].runs[0]
            self.assertEqual(result.paragraphs[0].style.name, "Intense Quote")
            self.assertTrue(replacement.bold)
            self.assertEqual(replacement.font.name, "Arial")

    def test_demo_session_and_single_marker_regeneration(self) -> None:
        with patch("docuwriter.web.create_provider", return_value=FakeProvider()):
            client = TestClient(app)
            session_response = client.post("/api/sessions/demo")
            self.assertEqual(session_response.status_code, 200)
            session = session_response.json()
            marker = session["markers"][0]
            regenerated = client.post(
                f"/api/sessions/{session['session_id']}/regenerate-marker",
                json={"marker": marker, "provider": "ollama", "model": "llama3.1"},
            )
            self.assertEqual(regenerated.status_code, 200)
            replacement = regenerated.json()
            replacement["proposed_replacement"] = "Texte édité manuellement"
            exported = client.post(
                f"/api/sessions/{session['session_id']}/export-final",
                json={
                    "markers": session["markers"],
                    "replacements": [replacement],
                    "highlight": True,
                },
            )
            self.assertEqual(exported.status_code, 200)
            self.assertIn("docx_url", exported.json())
            downloaded = client.get(exported.json()["docx_url"])
            self.assertEqual(downloaded.status_code, 200)
            self.assertIn(b"word/document.xml", downloaded.content)

    def test_load_pdf_context_chunks_with_page_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.pdf"
            document = fitz.open()
            document.new_page().insert_text((50, 50), "TLS architecture PostgreSQL", fontsize=11)
            document.new_page().insert_text((50, 50), "Unrelated content", fontsize=11)
            document.save(path)
            document.close()
            chunks = load_pdf_context_chunks(path)
            self.assertEqual({chunk.page_number for chunk in chunks}, {1, 2})
            query = Placeholder("p", "TLS", "architecture", "<here>x</here>", "pdf")
            retrieved = BM25ContextRetriever(chunks).retrieve_for_batch([query], 500)
            self.assertIn("| Page 1", retrieved)

    def test_parse_and_replace_pdf_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "target.pdf"
            output = root / "completed.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text((50, 50), "Architecture", fontsize=18)
            page.insert_text((50, 100), "Description <here>Décrire l'architecture</here>", fontsize=11)
            page.insert_text((50, 140), "Component | Protocol", fontsize=11)
            document.save(source)
            document.close()
            placeholders = parse_target_pdf(source)
            pairs = [ReplacementPair(
                item.placeholder_id, item.section_path, item.location_type,
                item.raw_tag, "Architecture conteneurisée TLS"
            ) for item in placeholders]
            self.assertEqual(apply_replacements_to_pdf(source, output, placeholders, pairs), 1)
            result = fitz.open(output)
            text = "".join(page.get_text() for page in result)
            result.close()
            self.assertNotIn("<here>", text)
            self.assertIn("Architecture conteneurisée TLS", text)

    def test_fastapi_pdf_interactive_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "plain.pdf"
            document = fitz.open()
            document.new_page().insert_text((50, 50), "PDF sans balise", fontsize=11)
            document.save(pdf_path)
            document.close()
            client = TestClient(app)
            with pdf_path.open("rb") as handle:
                session_response = client.post(
                    "/api/sessions",
                    files={"target_file": ("plain.pdf", handle, "application/pdf")},
                )
            self.assertEqual(session_response.status_code, 200)
            session = session_response.json()
            marker_response = client.post(
                f"/api/sessions/{session['session_id']}/markers",
                json={"page_number": 1, "bbox": [40, 35, 180, 60],
                      "original_hint": "Ajouter une description"},
            )
            self.assertEqual(marker_response.status_code, 200)
            marker = marker_response.json()
            export_response = client.post(
                f"/api/sessions/{session['session_id']}/export-final",
                json={"markers": [marker], "replacements": [{
                    "placeholder_id": marker["placeholder_id"],
                    "proposed_replacement": "Contenu PDF ajouté",
                }]},
            )
            self.assertEqual(export_response.status_code, 200)
            downloaded = client.get(export_response.json()["document_url"])
            self.assertEqual(downloaded.status_code, 200)
            result = fitz.open(stream=downloaded.content, filetype="pdf")
            self.assertIn("Contenu PDF ajouté", result[0].get_text())
            result.close()


if __name__ == "__main__":
    unittest.main()
