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
    PreviewerListResponse,
    PreviewerReloadResponse,
    PreviewerSpecModel,
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
from scistudio.previewers.models import MissingBundleError, OwnerKind, PreviewError

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
# #2095: previewer discovery + reload.
#
# The previewer tier gained a project and a user tier in #2017/#2044 but not the
# surface blocks and types already had around theirs. These two routes close
# that: one answers which previewers exist and where each came from, the other
# lets the previewer surface trigger a registry rebuild without reaching for the
# block endpoint to do it.
# ---------------------------------------------------------------------------

#: Routing precedence, used to order the listing so the reader sees the specs in
#: the order the router would consider them (ADR-048 FR-003).
_TIER_ORDER = {
    OwnerKind.PROJECT: 0,
    OwnerKind.USER: 1,
    OwnerKind.PACKAGE: 2,
    OwnerKind.CORE: 3,
}


def _spec_model(spec: Any) -> PreviewerSpecModel:
    """Adapt a :class:`PreviewerSpec` to its wire shape."""
    data = spec.to_dict()
    # ``to_dict`` also carries ``resource_provider``, which the wire model does
    # not declare; naming the fields explicitly keeps the two from drifting
    # silently if either side gains a key.
    return PreviewerSpecModel(
        previewer_id=data["previewer_id"],
        owner_kind=data["owner_kind"],
        owner_name=data["owner_name"],
        target_type=data["target_type"],
        supports_collection=data["supports_collection"],
        priority=data["priority"],
        capabilities=data["capabilities"],
        backend_provider=data["backend_provider"],
        frontend_manifest=data["frontend_manifest"],
        api_version=data["api_version"],
    )


@previews_router.get("/previewers", response_model=PreviewerListResponse)
async def list_previewers(
    runtime: RuntimeDep,
    target_type: str | None = None,
) -> PreviewerListResponse:
    """List registered previewers, with the tier each was discovered from.

    ``target_type`` filters to specs claiming exactly that type name. It is an
    exact match, not the router's specificity walk: a caller asking "what claims
    ``Spectrum``" wants the previewers written for ``Spectrum``, not every
    ancestor previewer that would also render one. Resolving what would actually
    be picked for a concrete target is the router's job, reached through a
    preview session.

    Registry diagnostics ride along because nothing else surfaces them. A
    drop-in refused for a module-name collision, a duplicate previewer id, a
    broken entry point -- all were recorded and then only logged, so from the
    product they looked like a previewer that simply never appeared.
    """
    service = runtime.get_preview_service()
    registry = service.registry
    specs = registry.all_specs()
    if target_type is not None:
        specs = [s for s in specs if s.target_type == target_type]
    specs = sorted(specs, key=lambda s: (_TIER_ORDER.get(s.owner_kind, 99), -s.priority, s.previewer_id))
    return PreviewerListResponse(
        previewers=[_spec_model(s) for s in specs],
        diagnostics=list(registry.diagnostics),
    )


@previews_router.post("/reload", response_model=PreviewerReloadResponse)
async def reload_previewers(runtime: RuntimeDep) -> PreviewerReloadResponse:
    """Re-scan the drop-in previewer directories and broadcast the change.

    This is a second surface onto one implementation, not a second reload.
    ``refresh_all_registries()`` has rebuilt the previewer registry alongside
    types and blocks since #2021, and ``POST /api/blocks/reload`` and
    ``POST /api/types/reload`` both already reach it -- verified directly:
    editing a drop-in previewer and calling the *blocks* endpoint does pick the
    edit up.

    What was missing is the previewer surface's own way in. FR-027's argument on
    the type side applies unchanged here: a previewer view must not have to
    speak to the block endpoints to do its own job, while all three endpoints
    still rebuild the same world. Inventing a previewer-only rebuild instead
    would be the drift ADR-053 §10.3/§10.4 exists to remove.

    The broadcast is ``blocks.reloaded`` for the same reason ``reload_types``
    gives: it is already in the websocket outbound allow-list, every client
    already reads it as "the registries were rebuilt, re-read your catalogues",
    and the block registry really was rebuilt. A ``previewers.reloaded`` sibling
    would be a second event for one fact.
    """
    service = runtime.get_preview_service()
    before = {s.previewer_id for s in service.registry.all_specs()}
    blocks_before = set(runtime.block_registry.all_specs().keys())

    runtime.refresh_all_registries()

    service = runtime.get_preview_service()
    registry = service.registry
    after = {s.previewer_id for s in registry.all_specs()}
    blocks_after = set(runtime.block_registry.all_specs().keys())
    added = sorted(after - before)
    removed = sorted(before - after)
    logger.info("POST /api/previews/reload: added=%s removed=%s", added, removed)

    # Best-effort, exactly as on the block and type sides: a headless or test
    # runtime with no event bus skips the broadcast rather than failing.
    event_bus = getattr(runtime, "event_bus", None)
    if event_bus is not None:
        from scistudio.engine.events import EngineEvent

        try:
            await event_bus.emit(
                EngineEvent(
                    event_type="blocks.reloaded",
                    data={
                        "added": sorted(blocks_after - blocks_before),
                        "removed": sorted(blocks_before - blocks_after),
                        "reloaded": sorted(blocks_after),
                        "source": "previewers",
                    },
                )
            )
        except Exception:
            logger.exception("POST /api/previews/reload: blocks.reloaded broadcast failed")

    return PreviewerReloadResponse(
        reloaded=len(after),
        added=added,
        removed=removed,
        diagnostics=list(registry.diagnostics),
    )


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
