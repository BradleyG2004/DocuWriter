"""Typed domain models."""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Placeholder:
    placeholder_id: str
    section_path: str
    original_hint: str
    raw_tag: str
    location_type: str
    paragraph_index: int | None = None
    table_coords: tuple[int, int, int] | None = None
    page_number: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    mode: str = "replace"
    start_offset: int | None = None
    end_offset: int | None = None


@dataclass(frozen=True)
class ContextChunk:
    source_file: str
    chunk_index: int
    text: str
    page_number: int | None = None


@dataclass(frozen=True)
class ReplacementPair:
    placeholder_id: str
    section_path: str
    location_type: str
    original_text_with_tags: str
    proposed_replacement: str
    sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InteractiveMarker:
    placeholder_id: str
    section_path: str
    user_instruction: str
    raw_tag: str = ""
    location_type: str = "paragraph"
    page_number: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    has_existing_tags: bool = False
    mode: str = "replace"
    paragraph_index: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    table_coords: tuple[int, int, int] | None = None
    color: str = "#FDE047"
    selected_text: str = ""
    review_comments: list[str] = field(default_factory=list)
    proposed_replacement: str = ""

    @property
    def marker_id(self) -> str:
        return self.placeholder_id


@dataclass(frozen=True)
class DocumentBlock:
    block_type: str
    text: str
    section_path: str = ""
    page_number: int | None = None
    marker_ids: list[str] = field(default_factory=list)


@dataclass
class TargetDocumentState:
    doc_id: str
    filename: str
    file_type: Literal["docx", "pdf"]
    status: Literal["to_fill", "in_validation", "validated"] = "to_fill"
    generated_context_summary: str = ""
    blocks: list[dict[str, Any]] = field(default_factory=list)
    markers: list[InteractiveMarker] = field(default_factory=list)
    iteration_count: int = 0
    source_path: str = ""
    output_path: str = ""


@dataclass
class ContextDocumentState:
    doc_id: str
    filename: str
    file_type: Literal["docx", "pdf"]
    chunk_count: int = 0
    preview_excerpt: str = ""
    blocks: list[dict[str, Any]] = field(default_factory=list)
    source_path: str = ""


@dataclass
class CompletionReport:
    elapsed_seconds: float
    total_placeholders_found: int
    total_replacements_proposed: int
    batches_processed: int
    failed_batches: int
    first_attempt_json_success_rate: float
    replacement_pairs: list[ReplacementPair] = field(default_factory=list)
