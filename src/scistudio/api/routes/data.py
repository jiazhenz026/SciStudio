"""Data upload, metadata, and preview endpoints.

ADR-048 SPEC 1 (no-compat, #1604): previews are served exclusively through the
routed panel *session* API (``/api/previews/...``), delegating to the
``scistudio.previewers`` subsystem owned by the runtime. The legacy one-shot
``GET /api/data/{data_ref}/preview`` adapter (FR-008) was removed under #1604;
the frontend ``TableViewer`` paginates/sorts through the session PATCH like the
``ArrayViewer`` slice selector.
"""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from scistudio.api.deps import get_runtime
from scistudio.api.routes.filesystem import _resolve_safe_path
from scistudio.api.routes.types import _package_name, _type_origin, package_names_by_import_root
from scistudio.api.runtime import ApiRuntime
from scistudio.api.schemas import (
    DataMetadataResponse,
    DataOpenAsCandidate,
    DataOpenAsCandidatesResponse,
    DataOpenAsEntry,
    DataOpenAsListResponse,
    DataRegisterPathRequest,
    DataRegisterPathResponse,
    DataUploadResponse,
    PanelChoiceListResponse,
    PanelChoiceModel,
    PanelChoiceRequest,
    PanelListResponse,
    PanelReloadResponse,
    PanelSpecModel,
    PreviewEnvelopeModel,
    PreviewResourceResponse,
    PreviewResourceSaveRequest,
    PreviewResourceSaveResponse,
    PreviewSessionCreate,
    PreviewSessionPatch,
)
from scistudio.core.meta._display_name import resolve_display_name
from scistudio.core.origins import CUSTOM_ORIGIN, PACKAGE_ORIGIN, PROJECT_ORIGIN, USER_ORIGIN
from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.artifact import Artifact
from scistudio.panels import (
    PreviewSource,
    PreviewTarget,
    TargetKind,
    UnknownPanelError,
    UnknownTargetError,
)
from scistudio.panels.assets import resolve_asset, validate_manifest
from scistudio.panels.choices import (
    clear_choice,
    load_choices,
    project_choices_path,
    read_choice_layer,
    user_choices_path,
    write_choice,
)
from scistudio.panels.models import MissingBundleError, OwnerKind, PreviewError
from scistudio.panels.open_as import (
    clear_open_as,
    normalize_extension,
    read_open_as,
    write_open_as,
)

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


#: Picker order for open-as candidates (#2112): the tiers a person authored or
#: installed themselves come before the ones that ship with the app, so the
#: default is the most specific answer available rather than the most generic.
_OPEN_AS_TIER_ORDER: tuple[str, ...] = (PROJECT_ORIGIN, USER_ORIGIN, CUSTOM_ORIGIN, PACKAGE_ORIGIN, "core")


def _resolve_project(runtime: ApiRuntime, project_id: str | None) -> Any:
    """Return the project a data-path request applies to, or raise 400/404."""
    if project_id is not None:
        project = runtime.known_projects.get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return project
    project = runtime.active_project
    if project is None:
        raise HTTPException(status_code=400, detail="No project is open and no project_id was given.")
    return project


def _contained_target(project: Any, raw: str) -> Path:
    """Resolve *raw* inside *project*, or raise 403/404.

    ``exists`` rather than ``is_file``: directory-backed stores (``.zarr``) are
    registerable too.
    """
    project_root = Path(os.path.realpath(project.path))
    candidate = os.path.realpath(raw if os.path.isabs(raw) else os.path.join(str(project_root), raw))
    # CodeQL py/path-injection canonical sanitiser: realpath + commonpath
    # (same pattern as api/routes/projects.py::_resolve_project_file).
    try:
        if os.path.commonpath([str(project_root), candidate]) != str(project_root):
            raise HTTPException(status_code=403, detail="Path escapes project root")
    except ValueError as exc:
        # commonpath raises on different drives (Windows) — treat as escape.
        raise HTTPException(status_code=403, detail="Path escapes project root") from exc

    target = Path(candidate)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {raw}")
    return target


def _open_as_candidates(runtime: ApiRuntime, project: Any, extension: str) -> list[DataOpenAsCandidate]:
    """Return the types *extension* can be opened as, most specific tier first.

    #2112. The ADR-043 load capability table already records which type can
    read which extension, so the candidate set is a query against it rather
    than a second mapping to keep in step. ``Artifact`` is appended when no
    loader claims it, because "open it as a plain file" is always a real answer
    — the artifact panel reports any file — and a picker that could not
    offer it would strand every extension no type declares.
    """
    block_registry = runtime.block_registry
    type_registry = runtime.type_registry
    project_dir = Path(project.path)
    package_names = package_names_by_import_root(block_registry)

    try:
        capabilities = block_registry.list_format_capabilities(direction="load", extension=extension)
    except Exception:
        logger.debug("open-as candidates: capability lookup failed for %r", extension, exc_info=True)
        capabilities = []
    loadable = {capability.data_type.__name__ for capability in capabilities}
    names = sorted(loadable) + ([] if Artifact.__name__ in loadable else [Artifact.__name__])

    candidates: list[DataOpenAsCandidate] = []
    for name in names:
        try:
            spec = type_registry.resolve(name)
        except Exception:
            spec = None
        origin = _type_origin(spec, project_dir) if spec is not None else ""
        candidates.append(
            DataOpenAsCandidate(
                name=name,
                base_type=getattr(spec, "base_type", "") or "",
                description=getattr(spec, "description", "") or "",
                origin=origin,
                package_name=_package_name(spec, origin, package_names) if spec is not None else None,
                loadable=name in loadable,
            )
        )

    def sort_key(candidate: DataOpenAsCandidate) -> tuple[int, str]:
        try:
            tier = _OPEN_AS_TIER_ORDER.index(candidate.origin)
        except ValueError:
            tier = len(_OPEN_AS_TIER_ORDER)
        return (tier, candidate.name)

    return sorted(candidates, key=sort_key)


@router.get("/open-as", response_model=DataOpenAsListResponse)
async def list_open_as_types(runtime: RuntimeDep, project_id: str | None = None) -> DataOpenAsListResponse:
    """Return the project's remembered extension -> type choices (#2112).

    ``available`` reports whether the remembered type is still registered: a
    choice outlives the package that provided it, and a stale one should read
    as stale rather than silently resolve to something else.

    Declared ahead of ``GET /{data_ref}`` so the catch-all cannot swallow it.
    """
    project = _resolve_project(runtime, project_id)
    entries = read_open_as(project.path)
    known = set(runtime.type_registry.all_types())
    return DataOpenAsListResponse(
        entries=[
            DataOpenAsEntry(extension=extension, type_name=type_name, available=type_name in known)
            for extension, type_name in sorted(entries.items())
        ]
    )


@router.get("/open-as/candidates", response_model=DataOpenAsCandidatesResponse)
async def get_open_as_candidates(
    runtime: RuntimeDep, path: str, project_id: str | None = None
) -> DataOpenAsCandidatesResponse:
    """Return the types *path* could be opened as, and any remembered choice (#2112).

    The Data tree asks this before opening a preview. One candidate means there
    is nothing to ask about; more than one, with nothing remembered, is what
    raises the picker.
    """
    project = _resolve_project(runtime, project_id)
    target = _contained_target(project, path)
    extension = normalize_extension(target.suffix)
    remembered = read_open_as(project.path).get(extension)
    return DataOpenAsCandidatesResponse(
        path=path,
        extension=extension,
        candidates=_open_as_candidates(runtime, project, extension),
        remembered=remembered,
    )


@router.delete("/open-as/{extension}", response_model=DataOpenAsListResponse)
async def clear_open_as_type(
    extension: str, runtime: RuntimeDep, project_id: str | None = None
) -> DataOpenAsListResponse:
    """Forget the remembered type for *extension* (#2112).

    Clearing an extension that was never chosen succeeds: the caller's intent —
    no remembered type here — already holds, and reporting a failure would only
    push every caller into checking first.
    """
    project = _resolve_project(runtime, project_id)
    clear_open_as(project.path, extension)
    logger.info("DELETE /api/data/open-as/%s", extension)
    return await list_open_as_types(runtime, project_id=project_id)


@router.post("/register-path", response_model=DataRegisterPathResponse)
async def register_data_path(payload: DataRegisterPathRequest, runtime: RuntimeDep) -> DataRegisterPathResponse:
    """Register a file already inside a project into the data catalog.

    #2112: the data-preview tab needs a catalog ref for a file that already
    lives under the project (e.g. ``data/foo.parquet``) so it can flow through
    the standard routed preview session API (``POST /api/previews/sessions``).
    Registration goes through ``register_data_ref`` so ``describe_ref``
    metadata comes for free; the returned ``ref``/``recorded_type``/
    ``type_chain`` mirror the frontend ``PreviewTarget`` fields (kind is always
    ``"data_ref"``).

    Which type the file is recorded as, in precedence order: an explicit
    ``type_name``, the project's remembered choice for the extension, then the
    extension inference ``register_data_ref`` applies on its own. An explicit
    ``type_name`` must be one of the candidates
    ``GET /open-as/candidates`` offers, so a typo is a 400 rather than a
    catalog record that can never route.
    """
    project = _resolve_project(runtime, payload.project_id)
    target = _contained_target(project, payload.path)
    extension = normalize_extension(target.suffix)
    remembered = read_open_as(project.path)

    type_name = payload.type_name
    if type_name is not None:
        allowed = {candidate.name for candidate in _open_as_candidates(runtime, project, extension)}
        if type_name not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"{type_name!r} cannot open {extension or target.name!r}. Known: {sorted(allowed)}.",
            )
        if payload.remember:
            write_open_as(project.path, extension, type_name)
            remembered = read_open_as(project.path)
    elif extension in remembered:
        type_name = remembered[extension]

    ref = StorageReference(
        backend="filesystem",
        path=str(target),
        format=target.suffix.lower().lstrip(".") or None,
    )
    record = runtime.register_data_ref(ref, type_name=type_name)
    display_name = resolve_display_name(record.metadata, fallback=target.name)
    logger.info("POST /api/data/register-path: %s -> %s (%s)", target, record.id, record.type_name)
    return DataRegisterPathResponse(
        ref=record.id,
        recorded_type=record.type_name,
        type_chain=list(record.type_chain) or [record.type_name],
        display_name=display_name or None,
        extension=extension,
        remembered=remembered.get(extension) == record.type_name,
    )


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
# ADR-048 SPEC 1: routed panel session API (additive).
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
# #2095: panel discovery + reload.
#
# The panel tier gained a project and a user tier in #2017/#2044 but not the
# surface blocks and types already had around theirs. These two routes close
# that: one answers which panels exist and where each came from, the other
# lets the panel surface trigger a registry rebuild without reaching for the
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


def _spec_model(spec: Any) -> PanelSpecModel:
    """Adapt a :class:`PanelSpec` to its wire shape."""
    data = spec.to_dict()
    # ``to_dict`` also carries ``resource_provider``, which the wire model does
    # not declare; naming the fields explicitly keeps the two from drifting
    # silently if either side gains a key.
    return PanelSpecModel(
        previewer_id=data["previewer_id"],
        owner_kind=data["owner_kind"],
        owner_name=data["owner_name"],
        target_type=data["target_type"],
        supports_collection=data["supports_collection"],
        priority=data["priority"],
        features=data["features"],
        backend_provider=data["backend_provider"],
        frontend_manifest=data["frontend_manifest"],
        api_version=data["api_version"],
    )


@previews_router.get("/previewers", response_model=PanelListResponse)
async def list_panels(
    runtime: RuntimeDep,
    target_type: str | None = None,
) -> PanelListResponse:
    """List registered panels, with the tier each was discovered from.

    ``target_type`` filters to specs claiming exactly that type name. It is an
    exact match, not the router's specificity walk: a caller asking "what claims
    ``Spectrum``" wants the panels written for ``Spectrum``, not every
    ancestor panel that would also render one. To learn what would actually
    be picked for a concrete target, open a preview session and read the
    ``previewer_id`` the router returned.

    Registry diagnostics ride along because nothing else surfaces them. A
    drop-in refused for a module-name collision, a duplicate panel id, a
    broken entry point -- all were recorded and then only logged, so from the
    product they looked like a panel that simply never appeared.
    """
    service = runtime.get_preview_service()
    registry = service.registry
    specs = registry.all_specs()
    if target_type is not None:
        specs = [s for s in specs if s.target_type == target_type]
    specs = sorted(specs, key=lambda s: (_TIER_ORDER.get(s.owner_kind, 99), -s.priority, s.previewer_id))
    return PanelListResponse(
        previewers=[_spec_model(s) for s in specs],
        diagnostics=list(registry.diagnostics),
    )


@previews_router.post("/reload", response_model=PanelReloadResponse)
async def reload_panels(runtime: RuntimeDep) -> PanelReloadResponse:
    """Re-scan the drop-in panel directories and broadcast the change.

    This is a second surface onto one implementation, not a second reload.
    ``refresh_all_registries()`` has rebuilt the panel registry alongside
    types and blocks since #2021, and ``POST /api/blocks/reload`` and
    ``POST /api/types/reload`` both already reach it -- verified directly:
    editing a drop-in panel and calling the *blocks* endpoint does pick the
    edit up.

    What was missing is the panel surface's own way in. FR-027's argument on
    the type side applies unchanged here: a panel view must not have to
    speak to the block endpoints to do its own job, while all three endpoints
    still rebuild the same world. Inventing a panel-only rebuild instead
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

    return PanelReloadResponse(
        reloaded=len(after),
        added=added,
        removed=removed,
        diagnostics=list(registry.diagnostics),
    )


# ---------------------------------------------------------------------------
# #2049: the person's chosen panel per type.
#
# ADR-048 FR-003 answers "which panel is best" without asking the person
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


def _effective_choices(runtime: ApiRuntime) -> PanelChoiceListResponse:
    """Build the effective-choices response.

    A plain function rather than the route handler, so the write routes can
    return the resulting state without calling a decorated endpoint -- which
    also keeps their declared return type honest.
    """
    project_dir = _active_project_dir(runtime)
    project_layer = read_choice_layer(project_choices_path(project_dir)) if project_dir is not None else {}
    effective = load_choices(project_dir)
    registry = runtime.get_preview_service().registry

    return PanelChoiceListResponse(
        choices=[
            PanelChoiceModel(
                target_type=target_type,
                previewer_id=previewer_id,
                scope=_PROJECT_SCOPE if target_type in project_layer else _USER_SCOPE,
                available=registry.get(previewer_id) is not None,
            )
            for target_type, previewer_id in sorted(effective.items())
        ]
    )


@previews_router.get("/choices", response_model=PanelChoiceListResponse)
async def list_panel_choices(runtime: RuntimeDep) -> PanelChoiceListResponse:
    """Return the effective per-type panel choices, with their layer.

    ``scope`` reports where each effective choice came from, so a reader can
    tell a project-only preference from a global one without diffing two files.
    ``available`` reports whether the chosen panel is registered right now:
    a choice outlives the package that provided it, and a stale one should read
    as stale rather than as missing.
    """
    return _effective_choices(runtime)


@previews_router.put("/choices/{target_type}", response_model=PanelChoiceListResponse)
async def set_panel_choice(
    target_type: str, payload: PanelChoiceRequest, runtime: RuntimeDep
) -> PanelChoiceListResponse:
    """Record *target_type* -> ``previewer_id`` at the requested scope.

    The panel must be registered. Routing tolerates a choice whose
    panel has since disappeared -- that is the realistic case, an uninstall
    -- but accepting one that never existed would store a preference that can
    never apply and give no clue why.

    Whether the panel can actually render this type is decided at routing
    time against the target's type chain, not here: this layer knows panel
    specs, and the type hierarchy belongs to the type registry.
    """
    path = _choices_path_for_scope(runtime, payload.scope)
    registry = runtime.get_preview_service().registry
    if registry.get(payload.previewer_id) is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown panel {payload.previewer_id!r}. See GET /api/previews/previewers.",
        )

    write_choice(path, target_type, payload.previewer_id)
    logger.info("PUT /api/previews/choices/%s: scope=%s", target_type, payload.scope)
    runtime.refresh_all_registries()
    return _effective_choices(runtime)


@previews_router.delete("/choices/{target_type}", response_model=PanelChoiceListResponse)
async def clear_panel_choice(
    target_type: str, runtime: RuntimeDep, scope: str = _USER_SCOPE
) -> PanelChoiceListResponse:
    """Remove the choice for *target_type* at *scope*.

    Clearing a type that was never chosen succeeds: the caller's intent -- no
    choice for this type here -- already holds, and reporting a failure would
    only push every caller into checking first.
    """
    path = _choices_path_for_scope(runtime, scope)
    clear_choice(path, target_type)
    logger.info("DELETE /api/previews/choices/%s: scope=%s", target_type, scope)
    runtime.refresh_all_registries()
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
    except UnknownPanelError as exc:
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
    except UnknownPanelError as exc:
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
    except UnknownPanelError as exc:
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
    except UnknownPanelError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except (UnknownTargetError, PreviewError) as exc:
        raise HTTPException(status_code=400, detail=getattr(exc, "message", str(exc))) from exc
    return PreviewResourceSaveResponse(**result)


@previews_router.get("/assets/{previewer_id}/{asset_path:path}")
async def serve_preview_asset(previewer_id: str, asset_path: str, runtime: RuntimeDep) -> FileResponse:
    """Serve a validated, path-confined same-origin panel asset (FR-022/FR-024).

    Only panels with a validated frontend manifest and a declared
    ``asset_root`` may serve assets; remote URLs and out-of-root paths are
    rejected with a 404 so the server never leaks arbitrary filesystem reads.
    """
    service = runtime.get_preview_service()
    spec = service.registry.get(previewer_id)
    if spec is None or spec.frontend_manifest is None:
        raise HTTPException(status_code=404, detail=f"no servable manifest for panel {previewer_id!r}")
    validation = validate_manifest(spec.frontend_manifest)
    if not validation.valid:
        raise HTTPException(status_code=404, detail="; ".join(validation.diagnostics) or "invalid manifest")
    try:
        served = resolve_asset(spec.frontend_manifest, asset_path)
    except MissingBundleError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    return FileResponse(path=Path(served.path), media_type=served.media_type)
