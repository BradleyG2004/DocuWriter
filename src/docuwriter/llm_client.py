"""Completion provider adapters."""

from abc import ABC, abstractmethod
import json
import re
import time
from typing import Any

import requests

from .config import Settings
from .models import Placeholder, ReplacementPair


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
