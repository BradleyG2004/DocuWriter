"""PDF replacement engine backed by PyMuPDF."""

from pathlib import Path

import fitz

from .models import InteractiveMarker, Placeholder, ReplacementPair


def _rect_for_placeholder(page: fitz.Page, placeholder: Placeholder) -> fitz.Rect | None:
    if placeholder.bbox is not None:
        return fitz.Rect(placeholder.bbox)
    matches = page.search_for(placeholder.raw_tag)
    return matches[0] if matches else None


def _font_size(page: fitz.Page, rect: fitz.Rect) -> float:
    sizes = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if fitz.Rect(span["bbox"]).intersects(rect):
                    sizes.append(span.get("size", 11.0))
    return max(sizes, default=11.0)


def apply_replacements_to_pdf(
    source_pdf: Path,
    output_pdf: Path,
    placeholders: list[Placeholder],
    pairs: list[ReplacementPair],
    highlight: bool = True,
) -> int:
    document = fitz.open(source_pdf)
    pair_map = {pair.placeholder_id: pair for pair in pairs}
    annex: list[tuple[str, str]] = []
    count = 0
    try:
        for placeholder in placeholders:
            pair = pair_map.get(placeholder.placeholder_id)
            if pair is None or placeholder.page_number is None:
                continue
            page = document[placeholder.page_number - 1]
            rect = _rect_for_placeholder(page, placeholder)
            if rect is None:
                annex.append((placeholder.section_path, pair.proposed_replacement))
                continue
            if placeholder.mode == "insert_after":
                annex.append((placeholder.section_path, pair.proposed_replacement))
                continue
            page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()
            if highlight:
                page.draw_rect(rect, color=None, fill=(1, 0.96, 0.6), overlay=False)
            fontsize = _font_size(page, rect)
            inserted = -1.0
            while fontsize >= 7.5 and inserted < 0:
                inserted = page.insert_textbox(
                    rect, pair.proposed_replacement, fontsize=fontsize,
                    fontname="helv", align=fitz.TEXT_ALIGN_LEFT,
                )
                if inserted < 0:
                    fontsize -= 0.5
            if inserted < 0:
                annex.append((placeholder.section_path, pair.proposed_replacement))
            else:
                count += 1
        if annex:
            page = document.new_page()
            page.insert_text((50, 50), "Annexe — contenus générés", fontsize=16, fontname="helv")
            y = 80
            for section, text in annex:
                content = f"{section or 'Sans section'}\n{text}"
                result = page.insert_textbox(
                    fitz.Rect(50, y, page.rect.width - 50, page.rect.height - 40),
                    content, fontsize=10, fontname="helv",
                )
                y += max(45, abs(result) + 20)
                if y > page.rect.height - 60:
                    page = document.new_page()
                    y = 50
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        document.save(output_pdf)
    finally:
        document.close()
    return count


def export_tagged_template_pdf(
    source_pdf: Path, output_pdf: Path, markers: list[InteractiveMarker]
) -> Path:
    document = fitz.open(source_pdf)
    annex: list[tuple[str, str]] = []
    try:
        for marker in markers:
            if marker.page_number is None:
                annex.append((marker.section_path, marker.user_instruction))
                continue
            page = document[marker.page_number - 1]
            rect = fitz.Rect(marker.bbox) if marker.bbox else None
            if rect is None:
                annex.append((marker.section_path, marker.user_instruction))
                continue
            page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()
            tag = f"<here>{marker.user_instruction}</here>"
            if page.insert_textbox(rect, tag, fontsize=10, fontname="helv") < 0:
                annex.append((marker.section_path, marker.user_instruction))
        if annex:
            page = document.new_page()
            y = 50
            for section, instruction in annex:
                page.insert_textbox(
                    fitz.Rect(50, y, page.rect.width - 50, page.rect.height - 40),
                    f"<here>{instruction}</here>\n{section}", fontsize=10,
                )
                y += 50
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        document.save(output_pdf)
    finally:
        document.close()
    return output_pdf
