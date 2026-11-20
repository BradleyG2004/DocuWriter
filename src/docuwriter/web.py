"""FastAPI application for the interactive reader."""

from dataclasses import asdict, dataclass, field, replace
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
from .llm_client import (
    build_document_context_with_ai,
    create_provider,
    detect_zones_with_ai,
)
from .models import (
    CompletionReport,
    ContextDocumentState,
    InteractiveMarker,
    Placeholder,
    ReplacementPair,
    TargetDocumentState,
)
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
    context_docs: list[ContextDocumentState] = field(default_factory=list)
    target_docs: list[TargetDocumentState] = field(default_factory=list)
    validated_docs: list[TargetDocumentState] = field(default_factory=list)

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
    markers = []
    for placeholder in session.placeholders:
        marker = _marker(placeholder)
        marker.update({
            "placeholder_id": placeholder.placeholder_id,
            "user_instruction": placeholder.original_hint,
            "has_existing_tags": bool(placeholder.raw_tag),
        })
        markers.append(marker)
    payload.update({
        "session_id": session.session_id,
        "filename": session.source.name,
        "markers": markers,
        "target_docs": [asdict(item) for item in session.target_docs],
        "context_docs": [asdict(item) for item in session.context_docs],
        "validated_docs": [asdict(item) for item in session.validated_docs],
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
    settings = Settings.from_env(root)
    session = Session(uuid4().hex, root, source, settings, parse_target_document(source))
    payload = serialize_document_for_reader(source)
    session.target_docs.append(TargetDocumentState(
        uuid4().hex, source.name, source.suffix.lower().lstrip("."),
        blocks=payload["blocks"],
        markers=[InteractiveMarker(
            item.placeholder_id, item.section_path, item.original_hint,
            item.raw_tag, item.location_type, item.page_number, item.bbox,
            bool(item.raw_tag), item.mode, item.paragraph_index,
            item.start_offset, item.end_offset, item.table_coords,
        ) for item in session.placeholders],
        source_path=str(source),
    ))
    SESSIONS[session.session_id] = session
    return session


def create_app() -> FastAPI:
    app = FastAPI(title="DocuWriter Reader")
    static_dir = Path(__file__).parent / "static"
    assets_dir = Path(__file__).parent / "assets"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/")
    def reader() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.post("/api/sessions/init")
    def init_session() -> dict[str, Any]:
        root = Path(tempfile.mkdtemp(prefix="docuwriter-multi-"))
        (root / "context").mkdir()
        (root / "tocomplete").mkdir()
        (root / "output").mkdir()
        session = Session(uuid4().hex, root, root / "tocomplete" / "empty.docx",
                          Settings.from_env(root), [])
        SESSIONS[session.session_id] = session
        return {
            "session_id": session.session_id,
            "context_docs": [],
            "target_docs": [],
            "validated_docs": [],
        }

    def _multi_payload(session: Session) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "context_docs": [asdict(item) for item in session.context_docs],
            "target_docs": [asdict(item) for item in session.target_docs],
            "validated_docs": [asdict(item) for item in session.validated_docs],
        }

    @app.post("/api/sessions/{session_id}/context-files")
    async def upload_context_files(session_id: str, files: list[UploadFile]) -> dict[str, Any]:
        session = _get_session(session_id)
        for upload in files:
            suffix = Path(upload.filename or "").suffix.lower()
            if suffix not in {".docx", ".pdf"}:
                raise HTTPException(status_code=415, detail="Only .docx and .pdf are supported")
            path = session.root / "context" / Path(upload.filename or "context" + suffix).name
            path.write_bytes(await upload.read())
            serialized = serialize_document_for_reader(path)
            chunks = load_context_chunks(session.root / "context", session.settings.chunk_size_chars)
            excerpt = "\n".join(chunk.text for chunk in chunks if chunk.source_file == path.name)
            session.context_docs.append(ContextDocumentState(
                uuid4().hex, path.name, suffix.lstrip("."),
                sum(1 for chunk in chunks if chunk.source_file == path.name),
                excerpt[:1000], serialized.get("blocks", []), str(path),
            ))
        return _multi_payload(session)

    @app.post("/api/sessions/{session_id}/target-files")
    async def upload_target_files(session_id: str, files: list[UploadFile]) -> dict[str, Any]:
        session = _get_session(session_id)
        for upload in files:
            suffix = Path(upload.filename or "").suffix.lower()
            if suffix not in {".docx", ".pdf"}:
                raise HTTPException(status_code=415, detail="Only .docx and .pdf are supported")
            path = session.root / "tocomplete" / Path(upload.filename or "target" + suffix).name
            path.write_bytes(await upload.read())
            serialized = serialize_document_for_reader(path)
            markers = detect_zones_with_ai(path)
            state = TargetDocumentState(
                uuid4().hex, path.name, suffix.lstrip("."),
                blocks=serialized.get("blocks", []), markers=markers, source_path=str(path),
            )
            session.target_docs.append(state)
            session.source = path
            session.placeholders = [
                Placeholder(
                    marker.placeholder_id, marker.section_path, marker.user_instruction,
                    marker.raw_tag, marker.location_type, marker.paragraph_index,
                    marker.table_coords, marker.page_number, marker.bbox, marker.mode,
                    marker.start_offset, marker.end_offset,
                )
                for marker in markers
            ]
        return _multi_payload(session)

    def _find_target(session: Session, doc_id: str) -> TargetDocumentState:
        target = next((item for item in session.target_docs if item.doc_id == doc_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Unknown target document")
        return target

    @app.post("/api/sessions/{session_id}/targets/{doc_id}/markers")
    def add_target_marker(session_id: str, doc_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = _get_session(session_id)
        target = _find_target(session, doc_id)
        marker_id = payload.get("marker_id", payload.get("placeholder_id", uuid4().hex))
        coords = tuple(payload["table_coords"]) if payload.get("table_coords") else None
        marker = InteractiveMarker(
            marker_id, payload.get("section_path", ""), payload.get("user_instruction", ""),
            payload.get("raw_tag", ""), payload.get("location_type", "paragraph"),
            payload.get("page_number"), tuple(payload["bbox"]) if payload.get("bbox") else None,
            False, payload.get("mode", "selection"), payload.get("paragraph_index"),
            payload.get("start_offset"), payload.get("end_offset"), coords,
            payload.get("color", "#FDE047"), payload.get("selected_text", ""),
        )
        target.markers.append(marker)
        return asdict(marker) | {"marker_id": marker.marker_id}

    @app.patch("/api/sessions/{session_id}/targets/{doc_id}/markers/{marker_id}")
    def patch_target_marker(session_id: str, doc_id: str, marker_id: str,
                            payload: dict[str, Any]) -> dict[str, Any]:
        target = _find_target(_get_session(session_id), doc_id)
        index = next((i for i, item in enumerate(target.markers)
                      if item.marker_id == marker_id), None)
        if index is None:
            raise HTTPException(status_code=404, detail="Unknown marker")
        marker = target.markers[index]
        comments = marker.review_comments
        if payload.get("review_comment"):
            comments = [*comments, str(payload["review_comment"])]
        target.markers[index] = replace(
            marker,
            user_instruction=str(payload.get("user_instruction", marker.user_instruction)),
            color=str(payload.get("color", marker.color)),
            review_comments=comments,
        )
        return asdict(target.markers[index]) | {"marker_id": marker_id}

    @app.delete("/api/sessions/{session_id}/targets/{doc_id}/markers/{marker_id}")
    def delete_target_marker(session_id: str, doc_id: str, marker_id: str) -> dict[str, bool]:
        target = _find_target(_get_session(session_id), doc_id)
        before = len(target.markers)
        target.markers = [item for item in target.markers if item.marker_id != marker_id]
        if len(target.markers) == before:
            raise HTTPException(status_code=404, detail="Unknown marker")
        return {"deleted": True}

    def _fill_target(session: Session, target: TargetDocumentState,
                    only_commented: bool = False) -> list[ReplacementPair]:
        context = "\n".join(item.preview_excerpt for item in session.context_docs)
        target.generated_context_summary = build_document_context_with_ai(target.blocks, context)
        markers = [
            marker for marker in target.markers
            if not only_commented or marker.review_comments
        ]
        placeholders = [
            Placeholder(marker.marker_id, marker.section_path, marker.user_instruction,
                        marker.raw_tag, marker.location_type, marker.paragraph_index,
                        marker.table_coords, marker.page_number, marker.bbox, marker.mode,
                        marker.start_offset, marker.end_offset)
            for marker in markers
        ]
        retriever = BM25ContextRetriever(load_context_chunks(
            session.root / "context", session.settings.chunk_size_chars
        ))
        pairs: list[ReplacementPair] = []
        if placeholders:
            pairs, _ = create_provider(session.settings).complete_batch(
                target.generated_context_summary + "\n" +
                retriever.retrieve_for_batch(placeholders, session.settings.max_context_chars),
                placeholders,
            )
        for pair in pairs:
            for index, marker in enumerate(target.markers):
                if marker.marker_id == pair.placeholder_id:
                    target.markers[index] = replace(
                        marker, proposed_replacement=pair.proposed_replacement,
                    )
        target.status = "in_validation"
        target.iteration_count += 1
        return pairs

    @app.post("/api/sessions/{session_id}/targets/{doc_id}/fill")
    def fill_target(session_id: str, doc_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        session = _get_session(session_id)
        target = _find_target(session, doc_id)
        pairs = _fill_target(session, target, bool((payload or {}).get("only_commented")))
        return {"status": target.status, "iteration_count": target.iteration_count,
                "generated_context_summary": target.generated_context_summary,
                "replacements": [asdict(pair) for pair in pairs]}

    @app.post("/api/sessions/{session_id}/targets/{doc_id}/fill-stream")
    async def fill_target_stream(session_id: str, doc_id: str,
                                 payload: dict[str, Any] | None = None) -> StreamingResponse:
        session = _get_session(session_id)
        target = _find_target(session, doc_id)

        async def events() -> AsyncIterator[str]:
            yield f"data: {json.dumps({'type': 'started', 'total_markers': len(target.markers)})}\n\n"
            pairs = _fill_target(session, target, bool((payload or {}).get("only_commented")))
            yield f"data: {json.dumps({'type': 'batch_completed', 'replacements': [asdict(pair) for pair in pairs]})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'status': target.status, 'iteration_count': target.iteration_count})}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/api/sessions/{session_id}/targets/{doc_id}/validate")
    def validate_target(session_id: str, doc_id: str) -> dict[str, Any]:
        session = _get_session(session_id)
        target = _find_target(session, doc_id)
        if target.status != "in_validation":
            raise HTTPException(status_code=409, detail="Target must be filled before validation")
        source = Path(target.source_path)
        placeholders = [
            Placeholder(marker.marker_id, marker.section_path, marker.user_instruction,
                        marker.raw_tag, marker.location_type, marker.paragraph_index,
                        marker.table_coords, marker.page_number, marker.bbox, marker.mode,
                        marker.start_offset, marker.end_offset)
            for marker in target.markers
        ]
        pairs = [ReplacementPair(marker.marker_id, marker.section_path, marker.location_type,
                                 marker.raw_tag, marker.proposed_replacement)
                 for marker in target.markers if marker.proposed_replacement]
        output = session.settings.output_dir / f"completed_{target.filename}"
        apply_replacements_to_document(source, output, placeholders, pairs, True)
        target.status = "validated"
        target.output_path = str(output)
        session.validated_docs.append(target)
        return {"status": target.status, "download_url":
                f"/api/sessions/{session_id}/targets/{doc_id}/download"}

    @app.post("/api/sessions/{session_id}/targets/{doc_id}/reopen")
    def reopen_target(session_id: str, doc_id: str) -> dict[str, str]:
        target = _find_target(_get_session(session_id), doc_id)
        target.status = "in_validation"
        return {"status": target.status}

    @app.get("/api/sessions/{session_id}/targets/{doc_id}/download")
    def download_validated(session_id: str, doc_id: str) -> FileResponse:
        target = _find_target(_get_session(session_id), doc_id)
        if target.status != "validated":
            raise HTTPException(status_code=403, detail="Document is not validated")
        return FileResponse(target.output_path, filename=f"completed_{target.filename}")

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
        table_coords = tuple(payload["table_coords"]) if payload.get("table_coords") else None
        page_number = payload.get("page_number")
        bbox = tuple(payload["bbox"]) if payload.get("bbox") else None
        if session.source.suffix.lower() == ".pdf" and payload.get("raw_tag"):
            import fitz
            with fitz.open(session.source) as document:
                for candidate_page, page in enumerate(document, 1):
                    matches = page.search_for(str(payload["raw_tag"]))
                    if matches:
                        page_number = candidate_page
                        rect = matches[0]
                        bbox = (rect.x0, rect.y0, rect.x1, rect.y1)
                        break
        placeholder = Placeholder(
            marker_id, payload.get("section_path", ""), payload.get("user_instruction", payload.get("original_hint", "")),
            payload.get("raw_tag", ""), payload.get("location_type",
                "paragraph" if session.source.suffix.lower() == ".docx" else "pdf"),
            page_number=page_number,
            bbox=bbox,
            mode=payload.get("mode", "replace"),
            paragraph_index=payload.get("paragraph_index"),
            start_offset=payload.get("start_offset"),
            end_offset=payload.get("end_offset"),
            table_coords=table_coords,
        )
        session.placeholders.append(placeholder)
        marker = _marker(placeholder)
        marker["original_hint"] = placeholder.original_hint
        marker["user_instruction"] = payload.get("user_instruction", placeholder.original_hint)
        marker["has_existing_tags"] = False
        return marker

    @app.patch("/api/sessions/{session_id}/markers/{marker_id}")
    def patch_marker(session_id: str, marker_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = _get_session(session_id)
        index = next(
            (index for index, item in enumerate(session.placeholders)
             if item.placeholder_id == marker_id),
            None,
        )
        if index is None:
            raise HTTPException(status_code=404, detail="Unknown marker")
        instruction = payload.get("user_instruction", payload.get("original_hint"))
        placeholder = session.placeholders[index]
        session.placeholders[index] = replace(
            placeholder,
            original_hint=str(instruction) if instruction is not None else placeholder.original_hint,
        )
        marker = _marker(session.placeholders[index])
        marker["original_hint"] = session.placeholders[index].original_hint
        marker["user_instruction"] = session.placeholders[index].original_hint
        return marker

    @app.delete("/api/sessions/{session_id}/markers/{marker_id}")
    def delete_marker(session_id: str, marker_id: str) -> dict[str, bool]:
        session = _get_session(session_id)
        before = len(session.placeholders)
        session.placeholders = [
            item for item in session.placeholders
            if item.placeholder_id != marker_id
        ]
        if len(session.placeholders) == before:
            raise HTTPException(status_code=404, detail="Unknown marker")
        return {"deleted": True}

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
        if session.source.suffix.lower() == ".docx":
            from .writer import apply_interactive_replacements_to_docx
            apply_interactive_replacements_to_docx(
                session.source, output_document, placeholders, pairs, payload.get("highlight", True)
            )
        else:
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
        markers = [
            InteractiveMarker(
                item.get("placeholder_id", uuid4().hex),
                item.get("section_path", ""),
                item.get("user_instruction", item.get("original_hint", "")),
                item.get("raw_tag", ""),
                item.get("location_type", "paragraph"),
                item.get("page_number"),
                tuple(item["bbox"]) if item.get("bbox") else None,
                item.get("has_existing_tags", False),
                item.get("mode", "replace"),
                item.get("paragraph_index"),
                item.get("start_offset"),
                item.get("end_offset"),
                tuple(item["table_coords"]) if item.get("table_coords") else None,
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
