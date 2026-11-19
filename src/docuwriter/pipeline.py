"""Command-line pipeline."""

import argparse
from dataclasses import replace
import logging
from pathlib import Path
import shutil
import time

from .config import Settings
from .llm_client import create_provider
from .models import CompletionReport
from .parser import load_context_chunks, parse_target_document
from .retriever import BM25ContextRetriever
from .writer import apply_replacements_to_document, export_report_json

LOGGER = logging.getLogger("docuwriter")


def _clean_output(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for item in output_dir.iterdir():
        if item.name != ".gitkeep":
            shutil.rmtree(item) if item.is_dir() else item.unlink()


def find_target_document(tocomplete_dir: Path) -> Path:
    candidates = sorted(
        path for path in tocomplete_dir.iterdir()
        if path.suffix.lower() in {".docx", ".pdf"} and not path.name.startswith("~$")
    )
    if not candidates:
        raise FileNotFoundError(f"No DOCX or PDF found in {tocomplete_dir}")
    return candidates[0]


def run(settings: Settings, clean: bool = True) -> CompletionReport:
    if clean:
        _clean_output(settings.output_dir)
    source = find_target_document(settings.tocomplete_dir)
    placeholders = parse_target_document(source)
    retriever = BM25ContextRetriever(load_context_chunks(settings.context_dir, settings.chunk_size_chars))
    provider = create_provider(settings)
    pairs = []
    batches = failed = first_successes = 0
    started = time.perf_counter()
    for start in range(0, len(placeholders), settings.batch_size):
        batch = placeholders[start:start + settings.batch_size]
        batches += 1
        try:
            batch_pairs, first_success = provider.complete_batch(
                retriever.retrieve_for_batch(batch, settings.max_context_chars), batch
            )
            pairs.extend(batch_pairs)
            first_successes += int(first_success)
        except RuntimeError:
            failed += 1
            LOGGER.exception("Completion batch %d failed", batches)
    report = CompletionReport(
        time.perf_counter() - started, len(placeholders), len(pairs), batches, failed,
        first_successes / batches if batches else 1.0, pairs,
    )
    apply_replacements_to_document(
        source, settings.output_dir / f"completed_{source.name}", placeholders, pairs,
        settings.highlight_replacements,
    )
    export_report_json(report, settings.output_dir / "completed_document.json")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Complete DOCX placeholders with an LLM")
    parser.add_argument("--provider", choices=("ollama", "openai"))
    parser.add_argument("--model")
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--no-highlight", action="store_true")
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    settings = replace(
        settings,
        llm_provider=args.provider or settings.llm_provider,
        batch_size=args.batch_size or settings.batch_size,
        highlight_replacements=False if args.no_highlight else settings.highlight_replacements,
        ollama_model=args.model if args.provider != "openai" and args.model else settings.ollama_model,
        openai_model=args.model if args.provider == "openai" and args.model else settings.openai_model,
    )
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run(settings, clean=not args.no_clean)


if __name__ == "__main__":
    main()
