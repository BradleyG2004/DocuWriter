"""DOCX placeholder and context extraction."""

from collections.abc import Iterable, Sequence
from pathlib import Path
import re

from docx import Document
from docx.text.paragraph import Paragraph

from .models import ContextChunk, DocumentBlock, InteractiveMarker, Placeholder

TAG_PATTERN = re.compile(r"<here>(.*?)</here>", re.DOTALL)


class SectionTracker:
    def __init__(self) -> None:
        self._levels: list[str] = []
        self._numbers: list[int] = []

    @property
    def path(self) -> str:
        return " / ".join(
            f"{'.'.join(str(number) for number in self._numbers[:index + 1])} {title}"
            for index, title in enumerate(self._levels)
        )

    def update(self, paragraph: Paragraph) -> None:
        style = paragraph.style.name if paragraph.style else ""
        self.update_heading(style, paragraph.text)

    def update_heading(self, style: str, title: str) -> None:
        if style == "Title":
            level = 1
        else:
            match = re.match(r"Heading\s+(\d+)", style)
            if not match:
                return
            level = int(match.group(1))
        title = title.strip()
        if not title:
            return
        self._levels = self._levels[:level - 1] + [title]
        self._numbers = self._numbers[:level - 1]
        if len(self._numbers) < level:
            self._numbers.append(1)
        else:
            self._numbers[-1] += 1


def _extract_from_paragraph_sequence(
    paragraphs: Sequence[Paragraph],
    location_type: str,
    tracker: SectionTracker,
    table_coords: tuple[int, int, int] | None = None,
    id_prefix: str = "p",
) -> list[Placeholder]:
    found: list[Placeholder] = []
    open_parts: list[str] = []
    open_path = ""
    open_index: int | None = None
    for index, paragraph in enumerate(paragraphs):
        text = paragraph.text
        if location_type == "paragraph":
            tracker.update(paragraph)
        if open_parts:
            open_parts.append(text)
            if "</here>" in text:
                raw = "\n".join(open_parts)
                for match in TAG_PATTERN.finditer(raw):
                    found.append(Placeholder(
                        f"{id_prefix}_{len(found)}", open_path, match.group(1).strip(),
                        match.group(0), location_type, open_index, table_coords,
                    ))
                open_parts = []
            continue
        matches = list(TAG_PATTERN.finditer(text))
        if matches:
            for match in matches:
                found.append(Placeholder(
                    f"{id_prefix}_{len(found)}", tracker.path, match.group(1).strip(),
                    match.group(0), location_type, index, table_coords,
                ))
            continue
        if "<here>" in text:
            open_parts = [text]
            open_path = tracker.path
            open_index = index
    return found


def parse_target_docx(docx_path: Path) -> list[Placeholder]:
    doc = Document(docx_path)
    tracker = SectionTracker()
    placeholders = _extract_from_paragraph_sequence(
        doc.paragraphs, "paragraph", tracker, id_prefix="paragraph"
    )
    for table_index, table in enumerate(doc.tables):
        for row_index, row in enumerate(table.rows):
            for col_index, cell in enumerate(row.cells):
                placeholders.extend(_extract_from_paragraph_sequence(
                    cell.paragraphs, "table", tracker,
                    (table_index, row_index, col_index),
                    f"table_{table_index}_{row_index}_{col_index}",
                ))
    return placeholders


def serialize_docx_for_reader(docx_path: Path) -> dict[str, object]:
    doc = Document(docx_path)
    blocks: list[DocumentBlock] = []
    markers: list[InteractiveMarker] = []
    for index, paragraph in enumerate(doc.paragraphs):
        if not paragraph.text.strip():
            continue
        style = paragraph.style.name if paragraph.style else ""
        block_type = "heading" if style == "Title" or style.startswith("Heading") else "paragraph"
        blocks.append(DocumentBlock(block_type, paragraph.text, "", None, []))
        for occurrence, match in enumerate(TAG_PATTERN.finditer(paragraph.text)):
            marker = InteractiveMarker(
                f"paragraph_{index}_{occurrence}", "", match.group(1).strip(),
                match.group(0), "paragraph", has_existing_tags=True,
            )
            markers.append(marker)
            blocks[-1].marker_ids.append(marker.placeholder_id)
    return {
        "file": docx_path.name,
        "file_type": "docx",
        "blocks": [vars(block) for block in blocks],
        "markers": [vars(marker) for marker in markers],
    }


def _context_texts(doc: Document) -> Iterable[str]:
    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            yield paragraph.text.strip()
    for table in doc.tables:
        for row in table.rows:
            text = " | ".join(cell.text.strip() for cell in row.cells).strip()
            if text:
                yield text


def load_context_chunks(context_dir: Path, chunk_size_chars: int = 800) -> list[ContextChunk]:
    chunks: list[ContextChunk] = []
    from .pdf_parser import load_pdf_context_chunks

    for source in sorted(context_dir.iterdir()):
        if source.name.startswith("~$"):
            continue
        if source.suffix.lower() == ".pdf":
            chunks.extend(load_pdf_context_chunks(source, chunk_size_chars))
            continue
        if source.suffix.lower() != ".docx":
            continue
        paragraphs = list(_context_texts(Document(source)))
        start = 0
        chunk_index = 0
        while start < len(paragraphs):
            text_parts: list[str] = []
            length = 0
            end = start
            while end < len(paragraphs) and (not text_parts or length + len(paragraphs[end]) + 1 <= chunk_size_chars):
                text_parts.append(paragraphs[end])
                length += len(paragraphs[end]) + 1
                end += 1
            chunks.append(ContextChunk(source.name, chunk_index, "\n".join(text_parts)))
            chunk_index += 1
            if end >= len(paragraphs):
                break
            start = max(start + 1, end - 1)
    return chunks


def parse_target_document(file_path: Path) -> list[Placeholder]:
    if file_path.suffix.lower() == ".pdf":
        from .pdf_parser import parse_target_pdf
        return parse_target_pdf(file_path)
    if file_path.suffix.lower() == ".docx":
        return parse_target_docx(file_path)
    raise ValueError(f"Unsupported document format: {file_path.suffix}")


def serialize_document_for_reader(file_path: Path) -> dict[str, object]:
    if file_path.suffix.lower() == ".pdf":
        from .pdf_parser import serialize_pdf_for_reader
        return serialize_pdf_for_reader(file_path)
    if file_path.suffix.lower() == ".docx":
        return serialize_docx_for_reader(file_path)
    raise ValueError(f"Unsupported document format: {file_path.suffix}")
