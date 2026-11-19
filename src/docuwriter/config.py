"""Application configuration."""

from dataclasses import dataclass
import os
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() in {"1", "true", "yes", "on"}:
        return True
    if value.lower() in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    context_dir: Path
    tocomplete_dir: Path
    output_dir: Path
    llm_provider: str = "ollama"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    batch_size: int = 5
    request_timeout: int = 300
    max_retries: int = 2
    max_context_chars: int = 6000
    chunk_size_chars: int = 800
    highlight_replacements: bool = True

    @classmethod
    def from_env(cls, root_dir: Path | None = None) -> "Settings":
        root = (root_dir or Path.cwd()).resolve()
        provider = os.getenv("LLM_PROVIDER", "ollama").lower()
        if provider not in {"ollama", "openai"}:
            raise ValueError("LLM_PROVIDER must be 'ollama' or 'openai'")
        return cls(
            root_dir=root,
            context_dir=Path(os.getenv("DOCUWRITER_CONTEXT_DIR", str(root / "context"))),
            tocomplete_dir=Path(os.getenv("DOCUWRITER_INPUT_DIR", str(root / "tocomplete"))),
            output_dir=Path(os.getenv("DOCUWRITER_OUTPUT_DIR", str(root / "output"))),
            llm_provider=provider,
            ollama_host=os.getenv("OLLAMA_HOST", cls.ollama_host),
            ollama_model=os.getenv("OLLAMA_MODEL", cls.ollama_model),
            openai_base_url=os.getenv("OPENAI_BASE_URL", cls.openai_base_url),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", cls.openai_model),
            batch_size=_env_int("BATCH_SIZE", cls.batch_size),
            request_timeout=_env_int("REQUEST_TIMEOUT", cls.request_timeout),
            max_retries=_env_int("MAX_RETRIES", cls.max_retries),
            max_context_chars=_env_int("MAX_CONTEXT_CHARS", cls.max_context_chars),
            chunk_size_chars=_env_int("CHUNK_SIZE_CHARS", cls.chunk_size_chars),
            highlight_replacements=_env_bool("HIGHLIGHT_REPLACEMENTS", True),
        )
