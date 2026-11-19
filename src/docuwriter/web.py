"""FastAPI application for the interactive reader."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import tempfile
from typing import Any, AsyncIterator
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .demo import build_demo_workspace
from .llm_client import create_provider
from .models import CompletionReport, InteractiveMarker, Placeholder, ReplacementPair
from .parser import load_context_chunks, parse_target_document, serialize_document_for_reader
from .retriever import BM25ContextRetriever
from .writer import apply_replacements_to_document, export_report_json, export_tagged_template_document


@dataclass
class Session:
    session_id: str
    root: Path
    source: Path
    settings: Settings
    placeholders: list[Placeholder]


SESSIONS: dict[str, Session] = {}


def _marker(placeholder: Placeholder) -> dict[str, Any]:
    return asdict(placeholder)


def _pair(data: dict[str, Any], placeholder: Placeholder) -> ReplacementPair:
    text = data.get("proposed_replacement", data.get("text", ""))
    return ReplacementPair(
        placeholder.placeholder_id, placeholder.section_path, placeholder.location_type,
        placeholder.raw_tag, str(text),
    )


def _session_payload(session: Session) -> dict[str, Any]:
    payload = serialize_document_for_reader(session.source)
    payload.update({
        "session_id": session.session_id,
        "filename": session.source.name,
        "markers": [_marker(placeholder) for placeholder in session.placeholders],
    })
    return payload


def _get_session(session_id: str) -> Session:
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    return session


def _create_session(root: Path) -> Session:
    source = next(
        (path for path in sorted(root.joinpath("tocomplete").iterdir())
         if path.suffix.lower() in {".docx", ".pdf"}),
        None,
    )
    if source is None:
        raise ValueError("No DOCX or PDF template found")
    settings = Settings(
        root_dir=root,
        context_dir=root / "context",
        tocomplete_dir=root / "tocomplete",
        output_dir=root / "output",
    )
    session = Session(uuid4().hex, root, source, settings, parse_target_document(source))
    SESSIONS[session.session_id] = session
    return session


def create_app() -> FastAPI:
    app = FastAPI(title="DocuWriter Reader")
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def reader() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.post("/api/sessions")
    async def create_session(
        target_file: UploadFile,
        context_files: list[UploadFile] | None = None,
    ) -> dict[str, Any]:
        root = Path(tempfile.mkdtemp(prefix="docuwriter-session-"))
        input_dir = root / "tocomplete"
        input_dir.mkdir(parents=True)
        destination = input_dir / (target_file.filename or "document.docx")
        if destination.suffix.lower() not in {".docx", ".pdf"}:
            raise HTTPException(status_code=415, detail="Only .docx and .pdf are supported")
        destination.write_bytes(await target_file.read())
        context_dir = root / "context"
        context_dir.mkdir()
        for context_file in context_files or []:
            if context_file.filename and Path(context_file.filename).suffix.lower() in {".docx", ".pdf"}:
                (context_dir / Path(context_file.filename).name).write_bytes(await context_file.read())
        return _session_payload(_create_session(root))

    @app.post("/api/sessions/demo")
    def create_demo_session() -> dict[str, Any]:
        root = Path(tempfile.mkdtemp(prefix="docuwriter-demo-"))
        build_demo_workspace(root)
        return _session_payload(_create_session(root))

    @app.post("/api/sessions/{session_id}/regenerate-marker")
    def regenerate_marker(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = _get_session(session_id)
        marker = payload.get("marker")
        if not isinstance(marker, dict):
            raise HTTPException(status_code=400, detail="marker is required")
        placeholder = next(
            (item for item in session.placeholders
             if item.placeholder_id == marker.get("placeholder_id")),
            None,
        )
        if placeholder is None:
            raise HTTPException(status_code=404, detail="Unknown marker")
        settings = session.settings
        provider_name = payload.get("provider", settings.llm_provider)
        model = payload.get("model")
        if provider_name == "ollama" and model:
            settings = settings.__class__(**{**asdict(settings), "llm_provider": provider_name, "ollama_model": model})
        elif provider_name == "openai" and model:
            settings = settings.__class__(**{**asdict(settings), "llm_provider": provider_name, "openai_model": model})
        retriever = BM25ContextRetriever(load_context_chunks(settings.context_dir, settings.chunk_size_chars))
        pairs, _ = create_provider(settings).complete_batch(
            retriever.retrieve_for_batch([placeholder], settings.max_context_chars), [placeholder]
        )
        if not pairs:
            raise HTTPException(status_code=502, detail="Provider returned no replacement")
        return asdict(pairs[0])

    @app.post("/api/sessions/{session_id}/markers")
    def add_marker(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = _get_session(session_id)
        marker_id = payload.get("placeholder_id", uuid4().hex)
        placeholder = Placeholder(
            marker_id, payload.get("section_path", ""), payload.get("original_hint", ""),
            payload.get("raw_tag", ""), payload.get("location_type", "pdf"),
            page_number=payload.get("page_number"),
            bbox=tuple(payload["bbox"]) if payload.get("bbox") else None,
            mode=payload.get("mode", "replace"),
        )
        session.placeholders.append(placeholder)
        return _marker(placeholder)

    @app.post("/api/sessions/{session_id}/export-final")
    def export_final(session_id: str, payload: dict[str, Any]) -> dict[str, str]:
        session = _get_session(session_id)
        markers = payload.get("markers", [])
        marker_map = {item.placeholder_id: item for item in session.placeholders}
        placeholders = [
            marker_map[item.get("placeholder_id")]
            for item in markers
            if item.get("placeholder_id") in marker_map
        ] or session.placeholders
        pairs = [_pair(item, marker_map[item["placeholder_id"]]) for item in payload.get("replacements", [])
                 if item.get("placeholder_id") in marker_map]
        output_dir = session.settings.output_dir
        output_document = output_dir / f"completed_{session.source.name}"
        apply_replacements_to_document(
            session.source, output_document, placeholders, pairs, payload.get("highlight", True)
        )
        report = CompletionReport(
            0.0, len(placeholders), len(pairs), 0, 0, 1.0, pairs
        )
        output_json = output_dir / "completed_document.json"
        export_report_json(report, output_json)
        return {
            "document_url": f"/api/sessions/{session_id}/download/{output_document.name}",
            "docx_url": f"/api/sessions/{session_id}/download/{output_document.name}",
            "report_url": f"/api/sessions/{session_id}/download/{output_json.name}",
        }

    @app.post("/api/sessions/{session_id}/export-template")
    def export_template(session_id: str, payload: dict[str, Any]) -> dict[str, str]:
        session = _get_session(session_id)
        if session.source.suffix.lower() != ".pdf":
            raise HTTPException(status_code=415, detail="Template export is currently for PDF")
        markers = [
            InteractiveMarker(
                item.get("placeholder_id", uuid4().hex),
                item.get("section_path", ""),
                item.get("user_instruction", item.get("original_hint", "")),
                item.get("raw_tag", ""),
                item.get("location_type", "pdf"),
                item.get("page_number"),
                tuple(item["bbox"]) if item.get("bbox") else None,
                item.get("has_existing_tags", False),
                item.get("mode", "replace"),
            )
            for item in payload.get("markers", [])
        ]
        output = session.settings.output_dir / f"tagged_{session.source.name}"
        export_tagged_template_document(session.source, output, markers)
        return {"document_url": f"/api/sessions/{session_id}/download/{output.name}"}

    @app.get("/api/sessions/{session_id}/download/{filename}")
    def download(session_id: str, filename: str) -> FileResponse:
        session = _get_session(session_id)
        path = session.settings.output_dir / filename
        if not path.is_file() or path.parent != session.settings.output_dir:
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(path)

    @app.post("/api/sessions/{session_id}/generate")
    def generate(session_id: str) -> dict[str, Any]:
        session = _get_session(session_id)
        retriever = BM25ContextRetriever(load_context_chunks(
            session.settings.context_dir, session.settings.chunk_size_chars
        ))
        provider = create_provider(session.settings)
        pairs: list[ReplacementPair] = []
        for start in range(0, len(session.placeholders), session.settings.batch_size):
            batch = session.placeholders[start:start + session.settings.batch_size]
            batch_pairs, _ = provider.complete_batch(
                retriever.retrieve_for_batch(batch, session.settings.max_context_chars), batch
            )
            pairs.extend(batch_pairs)
        report = CompletionReport(0.0, len(session.placeholders), len(pairs), 1, 0, 1.0, pairs)
        return {"replacements": [asdict(pair) for pair in pairs], "report": asdict(report)}

    @app.post("/api/sessions/{session_id}/generate-stream")
    async def generate_stream(session_id: str) -> StreamingResponse:
        session = _get_session(session_id)

        async def events() -> AsyncIterator[str]:
            retriever = BM25ContextRetriever(load_context_chunks(
                session.settings.context_dir, session.settings.chunk_size_chars
            ))
            provider = create_provider(session.settings)
            batches = [
                session.placeholders[start:start + session.settings.batch_size]
                for start in range(0, len(session.placeholders), session.settings.batch_size)
            ]
            yield f"data: {json.dumps({'type': 'started', 'total_batches': len(batches), 'total_markers': len(session.placeholders)})}\n\n"
            all_pairs: list[ReplacementPair] = []
            for index, batch in enumerate(batches, 1):
                try:
                    pairs, _ = provider.complete_batch(
                        retriever.retrieve_for_batch(batch, session.settings.max_context_chars), batch
                    )
                    all_pairs.extend(pairs)
                    event = {"type": "batch_completed", "batch_index": index,
                             "total_batches": len(batches), "replacements": [asdict(pair) for pair in pairs]}
                except RuntimeError as exc:
                    event = {"type": "batch_failed", "batch_index": index, "error": str(exc)}
                yield f"data: {json.dumps(event)}\n\n"
            report = CompletionReport(0.0, len(session.placeholders), len(all_pairs), len(batches), 0, 1.0, all_pairs)
            yield f"data: {json.dumps({'type': 'done', 'report': asdict(report)})}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    return app


app = create_app()
