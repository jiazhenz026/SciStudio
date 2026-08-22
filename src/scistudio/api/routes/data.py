"""Data upload, metadata, and preview endpoints.

ADR-048 SPEC 1 (no-compat, #1604): previews are served exclusively through the
routed previewer *session* API (``/api/previews/...``), delegating to the
``scistudio.previewers`` subsystem owned by the runtime. The legacy one-shot
``GET /api/data/{data_ref}/preview`` adapter (FR-008) was removed under #1604;
the frontend ``TableViewer`` paginates/sorts through the session PATCH like the
``ArrayViewer`` slice selector.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from scistudio.api.deps import get_runtime
from scistudio.api.routes.filesystem import _resolve_safe_path
from scistudio.api.runtime import ApiRuntime
from scistudio.api.schemas import (
    DataMetadataResponse,
    DataUploadResponse,
    PreviewEnvelopeModel,
    PreviewerChoiceListResponse,
    PreviewerChoiceModel,
    PreviewerChoiceRequest,
    PreviewResourceResponse,
    PreviewResourceSaveRequest,
    PreviewResourceSaveResponse,
    PreviewSessionCreate,
    PreviewSessionPatch,
)
from scistudio.previewers import (
    PreviewSource,
    PreviewTarget,
    TargetKind,
    UnknownPreviewerError,
    UnknownTargetError,
)
from scistudio.previewers.assets import resolve_asset, validate_manifest
from scistudio.previewers.choices import (
    clear_choice,
    load_choices,
    project_choices_path,
    read_choice_layer,
    user_choices_path,
    write_choice,
)
from scistudio.previewers.models import MissingBundleError, PreviewError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data", tags=["data"])
previews_router = APIRouter(prefix="/api/previews", tags=["previews"])
UploadFileParam = Annotated[UploadFile, File(...)]
RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]


MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MiB read granularity


@router.post("/upload", response_model=DataUploadResponse)
async def upload_data(
    file: UploadFileParam,
    runtime: RuntimeDep,
) -> DataUploadResponse:
    """Upload a data file and register it in the active project.

    #1526: stream the request body in fixed-size chunks while tracking a
    running byte counter and abort with 413 as soon as the cap is exceeded.
    Previously the whole body was buffered via ``await file.read()`` *before*
    the size check, so an oversized upload (accidental or hostile) could
    exhaust process memory before the 413 ever fired.
    """
    destination, staged_path = runtime.stage_upload_file(file.filename or "upload.bin")
    total = 0
    try:
        with staged_path.open("wb") as staged:
            while True:
                chunk = await file.read(_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail="File too large (max 2 GB)")
                staged.write(chunk)
        payload = runtime.finish_staged_upload(destination, staged_path)
    except Exception:
        runtime.discard_staged_upload(staged_path)
        raise
    return DataUploadResponse(**payload)


@router.get("/{data_ref}", response_model=DataMetadataResponse)
@router.get("/{data_ref}/metadata", response_model=DataMetadataResponse, include_in_schema=False)
async def get_data_metadata(data_ref: str, runtime: RuntimeDep) -> DataMetadataResponse:
    """Return metadata for a stored data object."""
    try:
        record = runtime.get_data_record(data_ref)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DataMetadataResponse(ref=record.id, type_name=record.type_name, metadata=record.metadata)


# ---------------------------------------------------------------------------
# ADR-048 SPEC 1: routed previewer session API (additive).
# ---------------------------------------------------------------------------


_TARGET_KINDS = {k.value: k for k in TargetKind}
_RESOURCE_PARAMS_MAX_BYTES = 8 * 1024
_RESOURCE_PARAMS_MAX_DEPTH = 8
_RESOURCE_PARAMS_MAX_ITEMS = 256
_RESOURCE_PARAM_STRING_MAX_BYTES = 4096


def _build_target(payload: PreviewSessionCreate) -> PreviewTarget:
    model = payload.target
    kind = _TARGET_KINDS.get(model.kind)
    if kind is None:
        raise HTTPException(status_code=422, detail=f"invalid target kind: {model.kind}")
    source = None
    if model.source:
        source = PreviewSource(
            workflow_id=model.source.get("workflow_id"),
            node_id=model.source.get("node_id"),
            output_port=model.source.get("output_port"),
        )
    return PreviewTarget(
        kind=kind,
        ref=model.ref,
        recorded_type=model.recorded_type,
        type_chain=tuple(model.type_chain),
        collection_item_type=model.collection_item_type,
        source=source,
    )


def _parse_resource_params(raw: str | None) -> dict[str, Any]:
    """Parse bounded JSON params for the session resource route.

    Resource descriptors may carry nested JSON values such as collection item
    descriptors. Keep the transport explicitly bounded before handing params to
    provider/session code.
    """
    if not raw:
        return {}
    if len(raw.encode("utf-8")) > _RESOURCE_PARAMS_MAX_BYTES:
        raise HTTPException(status_code=413, detail="resource params exceed the 8 KiB limit")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="resource params must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="resource params must be a JSON object")
    _validate_resource_param_value(parsed)
    return parsed


def _validate_resource_param_value(value: Any, *, depth: int = 0) -> int:
    if depth > _RESOURCE_PARAMS_MAX_DEPTH:
        raise HTTPException(status_code=422, detail="resource params are too deeply nested")
    if isinstance(value, dict):
        count = len(value)
        if count > _RESOURCE_PARAMS_MAX_ITEMS:
            raise HTTPException(status_code=422, detail="resource params contain too many entries")
        for key, child in value.items():
            if not isinstance(key, str):
                raise HTTPException(status_code=422, detail="resource param keys must be strings")
            if len(key.encode("utf-8")) > _RESOURCE_PARAM_STRING_MAX_BYTES:
                raise HTTPException(status_code=422, detail="resource param key is too large")
            count += _validate_resource_param_value(child, depth=depth + 1)
            if count > _RESOURCE_PARAMS_MAX_ITEMS:
                raise HTTPException(status_code=422, detail="resource params contain too many entries")
        return count
    if isinstance(value, list):
        count = len(value)
        if count > _RESOURCE_PARAMS_MAX_ITEMS:
            raise HTTPException(status_code=422, detail="resource params contain too many entries")
        for child in value:
            count += _validate_resource_param_value(child, depth=depth + 1)
            if count > _RESOURCE_PARAMS_MAX_ITEMS:
                raise HTTPException(status_code=422, detail="resource params contain too many entries")
        return count
    if isinstance(value, str):
        if len(value.encode("utf-8")) > _RESOURCE_PARAM_STRING_MAX_BYTES:
            raise HTTPException(status_code=422, detail="resource param string is too large")
        return 1
    if value is None or isinstance(value, bool):
        return 1
    if isinstance(value, int):
        return 1
    if isinstance(value, float):
        if not math.isfinite(value):
            raise HTTPException(status_code=422, detail="resource param numbers must be finite")
        return 1
    raise HTTPException(status_code=422, detail="resource params must be JSON-compatible")


# ---------------------------------------------------------------------------
# #2049: the person's chosen previewer per type.
#
# ADR-048 FR-003 answers "which previewer is best" without asking the person
# looking at the data. These routes record what they asked for instead. Two
# layers -- this project, or every project -- with the project layer winning,
# and a choice that cannot be honoured falls back to the ladder rather than
# failing, because a preference must never stop a preview from rendering.
# ---------------------------------------------------------------------------

_USER_SCOPE = "user"
_PROJECT_SCOPE = "project"


def _active_project_dir(runtime: ApiRuntime) -> Path | None:
    project = getattr(runtime, "active_project", None)
    return Path(project.path) if project is not None else None


def _choices_path_for_scope(runtime: ApiRuntime, scope: str) -> Path:
    """Return the file a choice at *scope* is written to, or 400."""
    project_dir = _active_project_dir(runtime)
    if scope == _USER_SCOPE:
        # Resolved against the project so a tutorial project writes into the
        # tutorial-scoped library rather than the real one (ADR-053 FR-070).
        return user_choices_path(project_dir)
    if scope == _PROJECT_SCOPE:
        if project_dir is None:
            raise HTTPException(
                status_code=400, detail="No project is open, so a project-scoped choice has nowhere to live."
            )
        return project_choices_path(project_dir)
    raise HTTPException(
        status_code=400,
        detail=f"Unknown scope {scope!r}. Known: {_PROJECT_SCOPE!r}, {_USER_SCOPE!r}.",
    )


def _effective_choices(runtime: ApiRuntime) -> PreviewerChoiceListResponse:
    """Build the effective-choices response.

    A plain function rather than the route handler, so the write routes can
    return the resulting state without calling a decorated endpoint -- which
    also keeps their declared return type honest.
    """
    project_dir = _active_project_dir(runtime)
    project_layer = read_choice_layer(project_choices_path(project_dir)) if project_dir is not None else {}
    effective = load_choices(project_dir)
    registry = runtime.get_preview_service().registry

    return PreviewerChoiceListResponse(
        choices=[
            PreviewerChoiceModel(
                target_type=target_type,
                previewer_id=previewer_id,
                scope=_PROJECT_SCOPE if target_type in project_layer else _USER_SCOPE,
                available=registry.get(previewer_id) is not None,
            )
            for target_type, previewer_id in sorted(effective.items())
        ]
    )


@previews_router.get("/choices", response_model=PreviewerChoiceListResponse)
async def list_previewer_choices(runtime: RuntimeDep) -> PreviewerChoiceListResponse:
    """Return the effective per-type previewer choices, with their layer.

    ``scope`` reports where each effective choice came from, so a reader can
    tell a project-only preference from a global one without diffing two files.
    ``available`` reports whether the chosen previewer is registered right now:
    a choice outlives the package that provided it, and a stale one should read
    as stale rather than as missing.
    """
    return _effective_choices(runtime)


@previews_router.put("/choices/{target_type}", response_model=PreviewerChoiceListResponse)
async def set_previewer_choice(
    target_type: str, payload: PreviewerChoiceRequest, runtime: RuntimeDep
) -> PreviewerChoiceListResponse:
    """Record *target_type* -> ``previewer_id`` at the requested scope.

    The previewer must be registered. Routing tolerates a choice whose
    previewer has since disappeared -- that is the realistic case, an uninstall
    -- but accepting one that never existed would store a preference that can
    never apply and give no clue why.

    Whether the previewer can actually render this type is decided at routing
    time against the target's type chain, not here: this layer knows previewer
    specs, and the type hierarchy belongs to the type registry.
    """
    path = _choices_path_for_scope(runtime, payload.scope)
    registry = runtime.get_preview_service().registry
    if registry.get(payload.previewer_id) is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown previewer {payload.previewer_id!r}. See GET /api/previews/previewers.",
        )

    write_choice(path, target_type, payload.previewer_id)
    logger.info("PUT /api/previews/choices/%s: scope=%s", target_type, payload.scope)
    runtime.refresh_preview_service()
    return _effective_choices(runtime)


@previews_router.delete("/choices/{target_type}", response_model=PreviewerChoiceListResponse)
async def clear_previewer_choice(
    target_type: str, runtime: RuntimeDep, scope: str = _USER_SCOPE
) -> PreviewerChoiceListResponse:
    """Remove the choice for *target_type* at *scope*.

    Clearing a type that was never chosen succeeds: the caller's intent -- no
    choice for this type here -- already holds, and reporting a failure would
    only push every caller into checking first.
    """
    path = _choices_path_for_scope(runtime, scope)
    clear_choice(path, target_type)
    logger.info("DELETE /api/previews/choices/%s: scope=%s", target_type, scope)
    runtime.refresh_preview_service()
    return _effective_choices(runtime)


@previews_router.post("/sessions", response_model=PreviewEnvelopeModel)
async def create_preview_session(payload: PreviewSessionCreate, runtime: RuntimeDep) -> PreviewEnvelopeModel:
    """Create a routed preview session for a target and return the first envelope."""
    # ADR-048 / #1592: the frontend PreviewHost sends a minimal ``{kind, ref}``
    # target; the backend is the source of truth for its routed kind + type
    # chain, so rebuild it from the catalog when the ref is known.
    target = runtime.resolve_session_target(_build_target(payload))
    service = runtime.get_preview_service()
    query = runtime.enrich_preview_query(target.ref, payload.query)
    envelope = service.sessions.create_session(target, query)
    return PreviewEnvelopeModel(**envelope.to_dict())


@previews_router.get("/sessions/{session_id}", response_model=PreviewEnvelopeModel)
async def read_preview_session(session_id: str, runtime: RuntimeDep) -> PreviewEnvelopeModel:
    """Read the current envelope + provider metadata for a session."""
    service = runtime.get_preview_service()
    try:
        envelope = service.sessions.read_session(session_id)
    except UnknownPreviewerError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    return PreviewEnvelopeModel(**envelope.to_dict())


@previews_router.patch("/sessions/{session_id}", response_model=PreviewEnvelopeModel)
async def patch_preview_session(
    session_id: str, payload: PreviewSessionPatch, runtime: RuntimeDep
) -> PreviewEnvelopeModel:
    """Update query state (slice/page/sort/slot/item) and re-render the envelope."""
    service = runtime.get_preview_service()
    try:
        envelope = service.sessions.patch_session(session_id, payload.query)
    except UnknownPreviewerError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    return PreviewEnvelopeModel(**envelope.to_dict())


@previews_router.get("/sessions/{session_id}/resources/{resource_id}", response_model=PreviewResourceResponse)
async def read_preview_resource(
    session_id: str,
    resource_id: str,
    runtime: RuntimeDep,
    params: Annotated[
        str | None,
        Query(description="JSON object copied from the selected PreviewResource.params descriptor."),
    ] = None,
) -> PreviewResourceResponse:
    """Fetch a bounded provider resource (array tile or child preview)."""
    service = runtime.get_preview_service()
    try:
        data = service.sessions.read_resource(session_id, resource_id, _parse_resource_params(params))
    except UnknownPreviewerError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except (UnknownTargetError, PreviewError) as exc:
        raise HTTPException(status_code=400, detail=getattr(exc, "message", str(exc))) from exc
    return PreviewResourceResponse(resource_id=resource_id, data=data)


@previews_router.post(
    "/sessions/{session_id}/resources/{resource_id}/save",
    response_model=PreviewResourceSaveResponse,
)
async def save_preview_resource(
    session_id: str,
    resource_id: str,
    payload: PreviewResourceSaveRequest,
    runtime: RuntimeDep,
) -> PreviewResourceSaveResponse:
    """Save a bounded provider resource to a path selected by the native dialog."""
    _validate_resource_param_value(payload.params)
    if not Path(payload.destination_path).is_absolute():
        raise HTTPException(status_code=400, detail="save destination must be an absolute file path")
    try:
        destination = _resolve_safe_path(payload.destination_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if destination.exists() and destination.is_dir():
        raise HTTPException(status_code=400, detail="save destination must be a file path")
    if not destination.parent.is_dir():
        raise HTTPException(status_code=400, detail="save destination parent directory does not exist")

    service = runtime.get_preview_service()
    try:
        result = service.sessions.save_resource(session_id, resource_id, destination, payload.params)
    except UnknownPreviewerError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except (UnknownTargetError, PreviewError) as exc:
        raise HTTPException(status_code=400, detail=getattr(exc, "message", str(exc))) from exc
    return PreviewResourceSaveResponse(**result)


@previews_router.get("/assets/{previewer_id}/{asset_path:path}")
async def serve_preview_asset(previewer_id: str, asset_path: str, runtime: RuntimeDep) -> FileResponse:
    """Serve a validated, path-confined same-origin previewer asset (FR-022/FR-024).

    Only previewers with a validated frontend manifest and a declared
    ``asset_root`` may serve assets; remote URLs and out-of-root paths are
    rejected with a 404 so the server never leaks arbitrary filesystem reads.
    """
    service = runtime.get_preview_service()
    spec = service.registry.get(previewer_id)
    if spec is None or spec.frontend_manifest is None:
        raise HTTPException(status_code=404, detail=f"no servable manifest for previewer {previewer_id!r}")
    validation = validate_manifest(spec.frontend_manifest)
    if not validation.valid:
        raise HTTPException(status_code=404, detail="; ".join(validation.diagnostics) or "invalid manifest")
    try:
        served = resolve_asset(spec.frontend_manifest, asset_path)
    except MissingBundleError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    return FileResponse(path=Path(served.path), media_type=served.media_type)
