"""Completion provider adapters."""

from abc import ABC, abstractmethod
import json
import re
import time
from pathlib import Path
from typing import Any

import requests

from .config import Settings
from .models import InteractiveMarker, Placeholder, ReplacementPair


def _parse_json(content: str) -> Any:
    cleaned = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    cleaned = re.sub(r"//[^\n]*", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


class CompletionProvider(ABC):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @abstractmethod
    def complete_batch(self, context_text: str, batch: list[Placeholder]) -> tuple[list[ReplacementPair], bool]:
        pass

    @staticmethod
    def _pairs(data: Any, batch: list[Placeholder]) -> list[ReplacementPair]:
        replacements = data.get("replacements", []) if isinstance(data, dict) else []
        if not isinstance(replacements, list):
            return []
        pairs: list[ReplacementPair] = []
        seen: set[int] = set()
        for item in replacements:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            replacement = item.get("replacement")
            if type(index) is not int or not 0 <= index < len(batch) or index in seen or not isinstance(replacement, str):
                continue
            seen.add(index)
            placeholder = batch[index]
            pairs.append(ReplacementPair(
                placeholder.placeholder_id, placeholder.section_path, placeholder.location_type,
                placeholder.raw_tag, replacement,
            ))
        return pairs


class OllamaProvider(CompletionProvider):
    def complete_batch(self, context_text: str, batch: list[Placeholder]) -> tuple[list[ReplacementPair], bool]:
        entries = "\n".join(
            f"[{index}] Section: {item.section_path}\nOriginal: {item.original_hint}"
            for index, item in enumerate(batch)
        )
        prompt = (
            "Replace each placeholder using the context. Return only JSON with "
            '{"replacements":[{"index":0,"replacement":"..."}]}.\n'
            f"Context:\n{context_text}\nPlaceholders:\n{entries}"
        )
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = requests.post(
                    f"{self.settings.ollama_host.rstrip('/')}/api/generate",
                    json={"model": self.settings.ollama_model, "prompt": prompt, "stream": False,
                          "format": "json", "options": {"temperature": 0.2}},
                    timeout=self.settings.request_timeout,
                )
                response.raise_for_status()
                body = response.json()
                content = body.get("response", "") if isinstance(body, dict) else ""
                data = _parse_json(content)
                if not isinstance(data, dict) or not isinstance(data.get("replacements"), list):
                    raise ValueError("Model response has no replacements list")
                return self._pairs(data, batch), attempt == 0
            except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.settings.max_retries:
                    time.sleep(2 ** attempt)
        raise RuntimeError("Unable to obtain valid Ollama JSON response") from last_error


class OpenAICompatibleProvider(CompletionProvider):
    def complete_batch(self, context_text: str, batch: list[Placeholder]) -> tuple[list[ReplacementPair], bool]:
        entries = "\n".join(f"[{i}] {p.section_path}: {p.original_hint}" for i, p in enumerate(batch))
        payload = {
            "model": self.settings.openai_model,
            "messages": [{"role": "user", "content": f"Context:\n{context_text}\nPlaceholders:\n{entries}"}],
            "response_format": {"type": "json_object"},
        }
        response = requests.post(
            f"{self.settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
            json=payload,
            timeout=self.settings.request_timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return self._pairs(_parse_json(content), batch), True


def create_provider(settings: Settings) -> CompletionProvider:
    if settings.llm_provider == "ollama":
        return OllamaProvider(settings)
    if settings.llm_provider == "openai":
        return OpenAICompatibleProvider(settings)
    raise ValueError(f"Unsupported provider: {settings.llm_provider}")


def detect_zones_with_ai(file_path: Path) -> list[InteractiveMarker]:
    """Detect explicit and deterministic completion zones for a target file.

    Explicit ``<here>`` tags remain authoritative.  For untagged documents the
    fallback intentionally stays deterministic so the web workflow is usable
    when an LLM is unavailable.
    """
    from .parser import serialize_document_for_reader

    serialized = serialize_document_for_reader(file_path)
    markers = [
        InteractiveMarker(
            item["placeholder_id"], item.get("section_path", ""),
            item.get("original_hint", item.get("user_instruction", "")),
            item.get("raw_tag", ""), item.get("location_type", "paragraph"),
            item.get("page_number"), tuple(item["bbox"]) if item.get("bbox") else None,
            bool(item.get("has_existing_tags", True)), item.get("mode", "replace"),
            item.get("paragraph_index"), item.get("start_offset"),
            item.get("end_offset"), tuple(item["table_coords"]) if item.get("table_coords") else None,
        )
        for item in serialized.get("markers", [])
    ]
    if markers:
        return markers

    marker_index = 0
    for block in serialized.get("blocks", []):
        text = str(block.get("text", ""))
        match = re.search(
            r"\.{3,}|_{3,}|\[[^\]]+\]|À compléter|à remplacer|placeholder",
            text, re.I,
        )
        if match:
            marker_index += 1
            markers.append(InteractiveMarker(
                f"ai_{marker_index}", block.get("section_path", ""),
                f"Compléter la zone : {match.group(0)}", "", "paragraph",
                block.get("page_number"), None, False, "selection",
                block.get("paragraph_index"), match.start(), match.end(), None,
                selected_text=match.group(0),
            ))
        for row in block.get("rows", []):
            for cell in row:
                if not str(cell.get("text", "")).strip():
                    marker_index += 1
                    markers.append(InteractiveMarker(
                        f"ai_{marker_index}", block.get("section_path", ""),
                        "Compléter cette cellule", "", "table",
                        block.get("page_number"), None, False, "table_cell",
                        table_coords=(block.get("table_index"), cell.get("row_idx"), cell.get("col_idx")),
                    ))
    return markers


def build_document_context_with_ai(
    target_blocks: list[dict[str, Any]],
    context_text: str,
) -> str:
    """Build a compact per-target context summary without requiring a model."""
    target_text = "\n".join(str(block.get("text", "")) for block in target_blocks)
    return (
        "Objet du document : document à compléter à partir de sa structure et de ses zones.\n"
        f"Structure cible : {target_text[:1200]}\n"
        f"Informations applicables : {context_text[:2400]}\n"
        "Règles : conserver le ton et la précision technique du document cible."
    )
