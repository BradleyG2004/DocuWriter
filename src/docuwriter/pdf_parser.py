"""PDF parsing and reader serialization using PyMuPDF."""

from collections.abc import Iterable
from pathlib import Path
import re
from statistics import median
from typing import Any

import fitz

from .models import ContextChunk, DocumentBlock, InteractiveMarker, Placeholder
from .parser import SectionTracker, TAG_PATTERN


def _page_blocks(page: fitz.Page) -> list[dict[str, Any]]:
    return [
        block for block in page.get_text("dict").get("blocks", [])
        if block.get("type") == 0 and block.get("lines")
    ]


def _block_text(block: dict[str, Any]) -> str:
    return "\n".join(
        "".join(span.get("text", "") for span in line.get("spans", []))
        for line in block.get("lines", [])
    ).strip()


def _block_font_size(block: dict[str, Any]) -> float:
    sizes = [
        span.get("size", 0.0)
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text", "").strip()
    ]
    return max(sizes, default=0.0)


def _all_pdf_text(pdf_path: Path) -> list[tuple[int, str, float, fitz.Rect]]:
    values = []
    with fitz.open(pdf_path) as document:
        for page_number, page in enumerate(document, 1):
            for block in _page_blocks(page):
                text = _block_text(block)
                if text:
                    values.append((page_number, text, _block_font_size(block), fitz.Rect(block["bbox"])))
    return values


def parse_target_pdf(pdf_path: Path) -> list[Placeholder]:
    values = _all_pdf_text(pdf_path)
    sizes = [size for _, text, size, _ in values if text]
    typical_size = median(sizes) if sizes else 11.0
    tracker = SectionTracker()
    placeholders: list[Placeholder] = []
    with fitz.open(pdf_path) as document:
        for page_number, page in enumerate(document, 1):
            for block in _page_blocks(page):
                text = _block_text(block)
                size = _block_font_size(block)
                if size >= typical_size * 1.35:
                    tracker.update_heading("Heading 1", text)
                elif size >= typical_size * 1.15:
                    tracker.update_heading("Heading 2", text)
                for match in TAG_PATTERN.finditer(text):
                    rectangles = page.search_for(match.group(0))
                    rect = rectangles[0] if rectangles else fitz.Rect(block["bbox"])
                    placeholders.append(Placeholder(
                        f"pdf_{page_number}_{len(placeholders)}",
                        tracker.path,
                        match.group(1).strip(),
                        match.group(0),
                        "pdf",
                        page_number=page_number,
                        bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
                    ))
            try:
                tables = page.find_tables().tables
            except (AttributeError, RuntimeError):
                tables = []
            for table in tables:
                for row in table.extract() or []:
                    for cell_text in row:
                        if not cell_text:
                            continue
                        for match in TAG_PATTERN.finditer(cell_text):
                            if any(
                                item.page_number == page_number and item.raw_tag == match.group(0)
                                for item in placeholders
                            ):
                                continue
                            rectangles = page.search_for(match.group(0))
                            rect = rectangles[0] if rectangles else fitz.Rect(table.bbox)
                            placeholders.append(Placeholder(
                                f"pdf_{page_number}_{len(placeholders)}",
                                tracker.path, match.group(1).strip(), match.group(0), "table",
                                page_number=page_number,
                                bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
                            ))
    return placeholders


def serialize_pdf_for_reader(pdf_path: Path) -> dict[str, Any]:
    placeholders = parse_target_pdf(pdf_path)
    marker_map = {placeholder.placeholder_id: InteractiveMarker(
        placeholder.placeholder_id, placeholder.section_path, placeholder.original_hint,
        placeholder.raw_tag, placeholder.location_type, placeholder.page_number,
        placeholder.bbox, True,
        "replace", None, None, None, placeholder.table_coords,
    ) for placeholder in placeholders}
    blocks: list[dict[str, Any]] = []
    block_counter = 0
    with fitz.open(pdf_path) as document:
        for page_number, page in enumerate(document, 1):
            for raw_block in _page_blocks(page):
                text = _block_text(raw_block)
                if not text:
                    continue
                block_markers = [
                    marker.placeholder_id for marker in marker_map.values()
                    if marker.page_number == page_number and marker.raw_tag in text
                ]
                block_type = "heading" if _block_font_size(raw_block) >= 14 else "paragraph"
                level = 1 if block_type == "heading" else None
                section_path = next(
                    (marker.section_path for marker in marker_map.values()
                     if marker.placeholder_id in block_markers), ""
                )
                blocks.append({
                    "block_id": f"blk_{block_counter}",
                    "block_type": block_type,
                    "text": text,
                    "section_path": section_path,
                    "level": level,
                    "paragraph_index": block_counter,
                    "table_index": None,
                    "rows": [],
                    "page_number": page_number,
                    "marker_ids": block_markers,
                })
                block_counter += 1
    return {
        "file": pdf_path.name,
        "file_type": "pdf",
        "blocks": blocks,
        "markers": [vars(marker) for marker in marker_map.values()],
    }


def load_pdf_context_chunks(pdf_path: Path, chunk_size_chars: int = 800) -> list[ContextChunk]:
    chunks: list[ContextChunk] = []
    with fitz.open(pdf_path) as document:
        for page_number, page in enumerate(document, 1):
            paragraphs = [
                _block_text(block) for block in _page_blocks(page)
                if _block_text(block)
            ]
            start = 0
            chunk_index = 0
            while start < len(paragraphs):
                parts: list[str] = []
                length = 0
                end = start
                while end < len(paragraphs) and (
                    not parts or length + len(paragraphs[end]) + 1 <= chunk_size_chars
                ):
                    parts.append(paragraphs[end])
                    length += len(paragraphs[end]) + 1
                    end += 1
                chunks.append(ContextChunk(
                    pdf_path.name, chunk_index, "\n".join(parts), page_number
                ))
                chunk_index += 1
                if end >= len(paragraphs):
                    break
                start = max(start + 1, end - 1)
    return chunks
