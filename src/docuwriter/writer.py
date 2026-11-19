"""DOCX rendering and report export."""

from dataclasses import asdict
import json
from pathlib import Path

from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.text.paragraph import Paragraph

from .models import CompletionReport, InteractiveMarker, Placeholder, ReplacementPair


def _replace_paragraph_preserving_style(
    paragraph: Paragraph, new_text: str, highlight: bool = False
) -> None:
    source_run = next((run for run in paragraph.runs if run.text), None)
    properties = {}
    if source_run is not None:
        properties = {
            "name": source_run.font.name,
            "size": source_run.font.size,
            "bold": source_run.font.bold,
            "italic": source_run.font.italic,
            "color": source_run.font.color.rgb if source_run.font.color else None,
        }
    for run in list(paragraph.runs):
        paragraph._p.remove(run._r)
    run = paragraph.add_run(new_text)
    run.font.name = properties.get("name")
    run.font.size = properties.get("size")
    run.font.bold = properties.get("bold")
    run.font.italic = properties.get("italic")
    if properties.get("color") is not None:
        run.font.color.rgb = properties["color"]
    if highlight:
        run.font.highlight_color = WD_COLOR_INDEX.YELLOW


def _replace_sequence(paragraphs: list[Paragraph], placeholders: list[Placeholder],
                      pairs: dict[str, ReplacementPair], highlight: bool) -> int:
    count = 0
    for placeholder in placeholders:
        pair = pairs.get(placeholder.placeholder_id)
        if pair is None or placeholder.paragraph_index is None:
            continue
        start = placeholder.paragraph_index
        if start >= len(paragraphs):
            continue
        text = paragraphs[start].text
        if placeholder.raw_tag in text:
            _replace_paragraph_preserving_style(paragraphs[start], text.replace(
                placeholder.raw_tag, pair.proposed_replacement, 1
            ), highlight)
            count += 1
            continue
        end = next((i for i in range(start, len(paragraphs)) if "</here>" in paragraphs[i].text), None)
        if end is None:
            continue
        opening = text.find("<here>")
        closing = paragraphs[end].text.find("</here>")
        if opening < 0 or closing < 0:
            continue
        _replace_paragraph_preserving_style(
            paragraphs[start], text[:opening] + pair.proposed_replacement, highlight
        )
        if end != start:
            _replace_paragraph_preserving_style(
                paragraphs[end], paragraphs[end].text[closing + len("</here>"):]
            )
            for index in range(start + 1, end):
                _replace_paragraph_preserving_style(paragraphs[index], "")
        count += 1
    return count


def apply_replacements_to_docx(
    source_docx: Path, output_docx: Path, placeholders: list[Placeholder],
    pairs: list[ReplacementPair], highlight: bool = True,
) -> int:
    doc = Document(source_docx)
    pair_map = {pair.placeholder_id: pair for pair in pairs}
    count = _replace_sequence(
        doc.paragraphs, [p for p in placeholders if p.location_type == "paragraph"],
        pair_map, highlight
    )
    for table_index, table in enumerate(doc.tables):
        for row_index, row in enumerate(table.rows):
            for col_index, cell in enumerate(row.cells):
                cell_placeholders = [
                    p for p in placeholders
                    if p.location_type == "table" and p.table_coords == (table_index, row_index, col_index)
                ]
                count += _replace_sequence(cell.paragraphs, cell_placeholders, pair_map, highlight)
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_docx)
    return count


def apply_interactive_replacements_to_docx(
    source_docx: Path,
    output_docx: Path,
    placeholders: list[Placeholder],
    pairs: list[ReplacementPair],
    highlight: bool = True,
) -> int:
    doc = Document(source_docx)
    pair_map = {pair.placeholder_id: pair for pair in pairs}
    count = 0
    for placeholder in placeholders:
        pair = pair_map.get(placeholder.placeholder_id)
        if pair is None:
            continue
        if placeholder.mode == "selection":
            if placeholder.paragraph_index is None:
                continue
            paragraphs = doc.paragraphs
            if placeholder.paragraph_index >= len(paragraphs):
                continue
            paragraph = paragraphs[placeholder.paragraph_index]
            text = paragraph.text
            start = placeholder.start_offset
            end = placeholder.end_offset
            if start is not None and end is not None and 0 <= start <= end <= len(text):
                _replace_paragraph_preserving_style(
                    paragraph, text[:start] + pair.proposed_replacement + text[end:], highlight
                )
                count += 1
        elif placeholder.mode == "insert_after":
            index = placeholder.paragraph_index
            target = doc.paragraphs[index]._p if index is not None and 0 <= index < len(doc.paragraphs) else (
                doc.paragraphs[-1]._p if doc.paragraphs else doc.add_paragraph()._p
            )
            new_paragraph = doc.add_paragraph(pair.proposed_replacement)
            target.addnext(new_paragraph._p)
            if highlight:
                for run in new_paragraph.runs:
                    run.font.highlight_color = WD_COLOR_INDEX.YELLOW
            count += 1
        elif placeholder.mode == "table_cell" and placeholder.table_coords:
            table_index, row_index, col_index = placeholder.table_coords
            if table_index < len(doc.tables) and row_index < len(doc.tables[table_index].rows):
                cell = doc.tables[table_index].rows[row_index].cells[col_index]
                cell.text = ""
                run = cell.paragraphs[0].add_run(pair.proposed_replacement)
                if highlight:
                    run.font.highlight_color = WD_COLOR_INDEX.YELLOW
                count += 1
        elif placeholder.raw_tag:
            count += _replace_sequence(
                doc.paragraphs, [placeholder], pair_map, highlight
            )
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_docx)
    return count


def export_tagged_template_docx(
    source_docx: Path,
    output_docx: Path,
    markers: list[InteractiveMarker],
) -> Path:
    doc = Document(source_docx)
    for marker in sorted(markers, key=lambda item: (
        item.paragraph_index if item.paragraph_index is not None else -1,
        item.end_offset if item.end_offset is not None else -1,
    ), reverse=True):
        tag = f"<here>{marker.user_instruction}</here>"
        if marker.mode == "selection":
            if marker.paragraph_index is None or marker.start_offset is None or marker.end_offset is None:
                continue
            if 0 <= marker.paragraph_index < len(doc.paragraphs):
                paragraph = doc.paragraphs[marker.paragraph_index]
                text = paragraph.text
                start = marker.start_offset
                end = marker.end_offset
                if 0 <= start <= end <= len(text):
                    _replace_paragraph_preserving_style(
                        paragraph, text[:start] + tag + text[end:], False
                    )
        elif marker.mode == "insert_after":
            index = marker.paragraph_index
            target = doc.paragraphs[index]._p if index is not None and 0 <= index < len(doc.paragraphs) else (
                doc.paragraphs[-1]._p if doc.paragraphs else doc.add_paragraph()._p
            )
            new_paragraph = doc.add_paragraph(tag)
            target.addnext(new_paragraph._p)
        elif marker.mode == "table_cell" and marker.table_coords:
            table_index, row_index, col_index = marker.table_coords
            if table_index < len(doc.tables) and row_index < len(doc.tables[table_index].rows):
                doc.tables[table_index].rows[row_index].cells[col_index].text = tag
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_docx)
    return output_docx


def apply_replacements_to_document(
    source_document: Path,
    output_document: Path,
    placeholders: list[Placeholder],
    pairs: list[ReplacementPair],
    highlight: bool = True,
) -> int:
    if source_document.suffix.lower() == ".pdf":
        from .pdf_writer import apply_replacements_to_pdf
        return apply_replacements_to_pdf(
            source_document, output_document, placeholders, pairs, highlight
        )
    if source_document.suffix.lower() == ".docx":
        return apply_replacements_to_docx(
            source_document, output_document, placeholders, pairs, highlight
        )
    raise ValueError(f"Unsupported document format: {source_document.suffix}")


def export_tagged_template_document(
    source_document: Path,
    output_document: Path,
    markers: list[InteractiveMarker],
) -> Path:
    if source_document.suffix.lower() == ".pdf":
        from .pdf_writer import export_tagged_template_pdf
        return export_tagged_template_pdf(source_document, output_document, markers)
    if source_document.suffix.lower() == ".docx":
        return export_tagged_template_docx(source_document, output_document, markers)
    raise ValueError(f"Unsupported document format: {source_document.suffix}")


def export_report_json(report: CompletionReport, output_json: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False), encoding="utf-8")
