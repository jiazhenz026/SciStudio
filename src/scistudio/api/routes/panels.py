"""The panel API surface: one asset route, the catalogue, and editing (D-020).

ADR-054 spec 1, tasks T-004, the backend half of T-008, and T-010. Everything a
panel host needs from HTTP is here, and the shapes are D-020's:

============================================================  =====================================
``GET  /api/panels/assets/{panel_id}/{asset_path}``           The one merged asset route (FR-021)
``GET  /api/panels``                                          The catalogue and its diagnostics
``POST /api/panels/reload``                                   Rebuild the registry (FR-046)
``GET  /api/panels/choices``                                  Per-type, per-capability choices
``PUT  /api/panels/choices/{target_type}``                    Record a choice (FR-049)
``DEL  /api/panels/choices/{target_type}``                    Clear a choice (FR-049)
``GET  /api/panels/{panel_id}/source``                        Read a panel's source (FR-024)
``PUT  /api/panels/{panel_id}/source``                        Save an edit (FR-025 to FR-027)
``DEL  /api/panels/{panel_id}/override``                      Revert (FR-029)
============================================================  =====================================

**One asset route, four roots.** The route resolves a panel id to the directory
its tier put it in and hands that root to
:func:`scistudio.panels.assets.resolve_confined_asset` — one path-confinement
check and one suffix allowlist, differing only in the root (FR-021, SC-008).
The two routes FR-022 keeps for the migration
(``/api/previews/assets/...`` and ``/api/blocks/panels/...``) call the same
function rather than carrying copies of the check, because three copies of a
confinement check is the failure mode this spec exists to remove.

**It is the only route that answers cross-origin.** A panel runs in a frame
sandboxed to ``allow-scripts`` alone, so it is at an opaque origin and cannot
fetch from the application at all except where the application says so. Saying
so here, and nowhere else, is what keeps the asset route the only thing a panel
can reach without going through the host (FR-021, A-008). The headers are on
this route's own responses; no other route gains them.

**The backend names the fallback.** :func:`envelope_response` stamps the
descriptor of the panel that was chosen and the id of the panel to mount when
it fails, onto the response the host is already reading (FR-015, D-013). The
frontend therefore keeps no mapping from a response's kind to a component
(FR-036, SC-010): it mounts what it was told to mount, and on failure it mounts
what it was told to fall back to.

**Editing is copy-on-write over the tier ordering.** The mechanics are in
:mod:`scistudio.panels.editing`; these routes are the HTTP adapter over them,
and they translate its typed refusals into statuses rather than deciding
anything themselves.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from scistudio.api.deps import get_runtime
from scistudio.api.runtime import ApiRuntime
from scistudio.api.schemas import (
    PanelChoiceListResponse,
    PanelChoiceModel,
    PanelChoiceRequest,
    PanelDescriptorModel,
    PanelListResponse,
    PanelOverrideRevertResponse,
    PanelReloadResponse,
    PanelSourceResponse,
    PanelSourceSaveRequest,
    PanelSourceSaveResponse,
    PanelSpecModel,
    PreviewEnvelopeModel,
)
from scistudio.core.dropins import project_panel_root
from scistudio.core.panels import PanelCapability, PanelTier
from scistudio.panels.assets import (
    PanelAssetTooLargeError,
    is_safe_panel_id,
    resolve_confined_asset,
)
from scistudio.panels.choices import (
    clear_choice,
    load_choice_layers,
    project_choices_path,
    read_choice_layers,
    user_choices_path,
    write_choice,
)
from scistudio.panels.descriptor import PANEL_ASSET_ROUTE_PREFIX, panel_descriptor
from scistudio.panels.discovery import DiscoveredPanel, PanelDiscovery
from scistudio.panels.editing import (
    PanelEditError,
    PanelNotEditableError,
    PanelOverrideNotFoundError,
    read_panel_source,
    revert_panel_override,
    save_panel_source,
)
from scistudio.panels.models import MissingBundleError, OwnerKind, PreviewEnvelope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/panels", tags=["panels"])
RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]

#: The panel the backend names as the fallback (FR-015, D-013, D-015). It is
#: ``core.base.fallback`` because it is the panel that renders from the least
#: information: whatever the envelope carries, it can show it. Written once
#: here so the response and the built-in directory cannot disagree.
FALLBACK_PANEL_ID = "core.base.fallback"

#: The asset route's path below this router's prefix. Derived from
#: ``PANEL_ASSET_ROUTE_PREFIX`` rather than respelled, so the route and the
#: descriptor that builds URLs for it cannot disagree (D-020).
_ASSET_SUBPATH = PANEL_ASSET_ROUTE_PREFIX.removeprefix("/api/panels")

#: Headers the merged asset route answers with, and no other route does
#: (FR-021, A-008). ``*`` rather than an origin echo because the frame's origin
#: is opaque — it serialises as ``null`` — and because these responses are
#: read-only and carry no credentials: no ``Allow-Credentials``, no ``Vary``
#: on an origin nothing varies by. ``Cross-Origin-Resource-Policy`` is the
#: second half of the same permission, for the embedder-policy case.
PANEL_ASSET_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Cross-Origin-Resource-Policy": "cross-origin",
}

_USER_SCOPE = "user"
_PROJECT_SCOPE = "project"

#: Routing precedence for the listing, so the reader sees the specs in the order
#: the router would consider them (ADR-048 FR-003, FR-019).
_TIER_ORDER = {
    OwnerKind.PROJECT: 0,
    OwnerKind.USER: 1,
    OwnerKind.PACKAGE: 2,
    OwnerKind.CORE: 3,
}


# ---------------------------------------------------------------------------
# Shared lookups
# ---------------------------------------------------------------------------


def _discovery(runtime: ApiRuntime) -> PanelDiscovery:
    """Return the four-tier on-disk scan the runtime's service holds."""
    return runtime.get_preview_service().panels


def _active_project_dir(runtime: ApiRuntime) -> Path | None:
    project = getattr(runtime, "active_project", None)
    return Path(project.path) if project is not None else None


def _writable_project_panels_root(runtime: ApiRuntime) -> Path | None:
    """Return the open project's panels root, or ``None`` when none is open."""
    project_dir = _active_project_dir(runtime)
    return project_panel_root(project_dir) if project_dir is not None else None


def _require_panel(runtime: ApiRuntime, panel_id: str) -> DiscoveredPanel:
    """Return the on-disk panel *panel_id* resolved to, or 404/400.

    The id is validated before it is used to look anything up: it arrives as a
    path segment, and an id that is itself a traversal must be refused rather
    than carried into a join (SC-008).
    """
    if not is_safe_panel_id(panel_id):
        raise HTTPException(status_code=400, detail=f"panel id {panel_id!r} is not a usable panel id")
    panel = _discovery(runtime).get(panel_id)
    if panel is None:
        raise HTTPException(status_code=404, detail=f"no panel directory registered for {panel_id!r}")
    return panel


def _capability(value: str) -> PanelCapability:
    """Return the :class:`PanelCapability` *value* names, or 400."""
    try:
        return PanelCapability(value)
    except ValueError as exc:
        known = ", ".join(repr(member.value) for member in PanelCapability)
        raise HTTPException(status_code=400, detail=f"Unknown capability {value!r}. Known: {known}.") from exc


# ---------------------------------------------------------------------------
# T-004: the merged asset route (FR-021, FR-022, SC-008)
# ---------------------------------------------------------------------------


@router.get(f"{_ASSET_SUBPATH}/{{panel_id}}/{{asset_path:path}}")
async def serve_panel_asset(panel_id: str, asset_path: str, runtime: RuntimeDep) -> FileResponse:
    """Serve one panel asset from whichever tier the panel resolved from.

    The root differs by tier and nothing else does: the same confinement check
    and the same suffix allowlist answer a core panel, a package panel, a
    user-library panel and a project panel (FR-021, SC-008). An oversized asset
    is a load failure with a readable diagnostic rather than a truncated read
    the host then fails to parse.
    """
    panel = _require_panel(runtime, panel_id)
    try:
        served = resolve_confined_asset(panel.directory, asset_path, panel_id=panel_id)
    except PanelAssetTooLargeError as exc:
        raise HTTPException(status_code=413, detail=exc.message) from exc
    except MissingBundleError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    return FileResponse(
        path=served.path,
        media_type=served.media_type,
        headers=dict(PANEL_ASSET_CORS_HEADERS),
    )


# ---------------------------------------------------------------------------
# T-008 backend half: the descriptor and the named fallback (FR-015, D-013)
# ---------------------------------------------------------------------------


def panel_descriptor_model(
    panel: DiscoveredPanel,
    *,
    granted_capability: PanelCapability | None = None,
) -> PanelDescriptorModel:
    """Return the wire descriptor the frame host validates before it mounts.

    Built by :func:`scistudio.panels.descriptor.panel_descriptor`, which the API
    layer carries rather than rebuilds (D-020): it already answers
    ``accepted_api_version`` and ``read_limits``, and the host refuses to mount
    without either (D-016.3).
    """
    return PanelDescriptorModel(**panel_descriptor(panel, granted_capability=granted_capability).to_dict())


def envelope_response(runtime: ApiRuntime, envelope: PreviewEnvelope) -> PreviewEnvelopeModel:
    """Return *envelope* on the wire, with the panel and the fallback named.

    Two additions to the response the host is already reading (FR-015, D-013,
    D-020): the descriptor of the panel that was chosen, and the id of the panel
    to mount when that one fails. Together they are what lets the frontend
    delete its own mapping from a response's kind to a component (FR-036,
    SC-010) — it has been told what to mount and what to fall back to, so it
    needs no local table to work either out.

    The granted capability is displaying. This is the preview surface: a
    producing panel opened here renders read-only and is granted no outbound
    path (FR-011, FR-049).

    A panel with no directory — an unmigrated package previewer crossing the
    compatibility shim — yields ``panel: null``. The fallback is named either
    way, because the failure path is exactly the case that needs it.
    """
    data = envelope.to_dict()
    discovery = _discovery(runtime)
    chosen = discovery.get(envelope.previewer_id)
    fallback = discovery.get(FALLBACK_PANEL_ID)
    return PreviewEnvelopeModel(
        **data,
        panel=(
            panel_descriptor_model(chosen, granted_capability=PanelCapability.DISPLAYING)
            if chosen is not None
            else None
        ),
        fallback_panel_id=FALLBACK_PANEL_ID,
        fallback_panel=(
            panel_descriptor_model(fallback, granted_capability=PanelCapability.DISPLAYING)
            if fallback is not None
            else None
        ),
    )


# ---------------------------------------------------------------------------
# FR-023: the catalogue and the rebuild, under the panel naming
# ---------------------------------------------------------------------------


def _list_entry(
    spec: Any,
    panel: DiscoveredPanel | None,
    *,
    shadows: PanelTier | None,
) -> PanelSpecModel:
    """Adapt a registry spec and its on-disk panel, if any, to the wire shape."""
    data = spec.to_dict() if spec is not None else {}
    manifest = panel.manifest if panel is not None else None
    return PanelSpecModel(
        panel_id=data.get("previewer_id") or (manifest.panel_id if manifest else ""),
        display_name=(manifest.display_name if manifest else "") or data.get("previewer_id", ""),
        owner_kind=data.get("owner_kind") or (panel.tier.value if panel else ""),
        owner_name=data.get("owner_name") or (panel.owner_name if panel else ""),
        target_type=data.get("target_type", ""),
        target_types=list(data.get("target_types") or (manifest.target_types if manifest else ())),
        supports_collection=bool(data.get("supports_collection", manifest.supports_collection if manifest else False)),
        priority=int(data.get("priority", manifest.priority if manifest else 0)),
        features=list(data.get("features") or (manifest.features if manifest else ())),
        capability=str(data.get("capability") or (manifest.capability.value if manifest else "")),
        backend_provider=data.get("backend_provider"),
        frontend_manifest=data.get("frontend_manifest"),
        api_version=str(data.get("api_version") or (manifest.api_version if manifest else "")),
        tier=panel.tier.value if panel is not None else None,
        shadows=shadows.value if shadows is not None else None,
        descriptor=panel_descriptor_model(panel) if panel is not None else None,
    )


@router.get("", response_model=PanelListResponse)
async def list_panels(runtime: RuntimeDep, target_type: str | None = None) -> PanelListResponse:
    """List registered panels, with the tier each was discovered from (FR-023).

    Behaviour is the endpoint this replaces, carried over: ``target_type``
    filters to specs claiming exactly that type name — an exact match, not the
    router's specificity walk, because a caller asking "what claims
    ``Spectrum``" wants the panels written for ``Spectrum`` — and the registry
    diagnostics ride along because nothing else surfaces them.

    What is new is the union. A panel addressed by the block that opens it
    declares no target type (FR-017), so it never enters the type registry, and
    a catalogue that showed only registry specs would be missing exactly the
    panels a producing mount has to look up. Every discovered panel is listed,
    with the descriptor the host mounts it from.
    """
    service = runtime.get_preview_service()
    registry = service.registry
    discovery = service.panels

    shadowed_tiers: dict[str, PanelTier] = {}
    for entry in discovery.shadowed:
        current = shadowed_tiers.get(entry.panel_id)
        if current is None or entry.tier.shadow_rank < current.shadow_rank:
            shadowed_tiers[entry.panel_id] = entry.tier

    specs = registry.all_specs()
    if target_type is not None:
        specs = [spec for spec in specs if spec.target_type == target_type]
    specs = sorted(specs, key=lambda s: (_TIER_ORDER.get(s.owner_kind, 99), -s.priority, s.previewer_id))

    entries = [
        _list_entry(spec, discovery.get(spec.previewer_id), shadows=shadowed_tiers.get(spec.previewer_id))
        for spec in specs
    ]
    if target_type is None:
        listed = {spec.previewer_id for spec in specs}
        entries.extend(
            _list_entry(None, panel, shadows=shadowed_tiers.get(panel.panel_id))
            for panel in sorted(discovery.all_panels(), key=lambda p: p.panel_id)
            if panel.panel_id not in listed
        )

    return PanelListResponse(panels=entries, diagnostics=list(registry.diagnostics))


@router.post("/reload", response_model=PanelReloadResponse)
async def reload_panels(runtime: RuntimeDep) -> PanelReloadResponse:
    """Rebuild the registry, and broadcast that it happened (FR-023, FR-046).

    The one way a panel directory added, changed or removed takes effect
    (FR-046). Behaviour carried over unchanged from the endpoint this replaces:
    it is a second surface onto one implementation, not a second reload —
    ``refresh_all_registries()`` rebuilds the panel registry alongside types and
    blocks, and the block and type reload endpoints reach the same code.

    The broadcast stays ``blocks.reloaded`` for the reason it always did: it is
    already in the websocket outbound allow-list, every client already reads it
    as "the registries were rebuilt, re-read your catalogues", and the block
    registry really was rebuilt.
    """
    service = runtime.get_preview_service()
    before = {spec.previewer_id for spec in service.registry.all_specs()}
    blocks_before = set(runtime.block_registry.all_specs().keys())

    runtime.refresh_all_registries()

    service = runtime.get_preview_service()
    registry = service.registry
    after = {spec.previewer_id for spec in registry.all_specs()}
    blocks_after = set(runtime.block_registry.all_specs().keys())
    added = sorted(after - before)
    removed = sorted(before - after)
    logger.info("POST /api/panels/reload: added=%s removed=%s", added, removed)

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
                        "source": "panels",
                    },
                )
            )
        except Exception:
            logger.exception("POST /api/panels/reload: blocks.reloaded broadcast failed")

    return PanelReloadResponse(
        reloaded=len(after),
        added=added,
        removed=removed,
        diagnostics=list(registry.diagnostics),
    )


# ---------------------------------------------------------------------------
# FR-049: the per-type, per-capability choice
# ---------------------------------------------------------------------------


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
    """Build the effective-choices response, every capability at once.

    A plain function rather than the route handler, so the write routes can
    return the resulting state without calling a decorated endpoint.

    Both capabilities are returned rather than one per request because they are
    two preferences about two situations (FR-049), and a caller that had to ask
    twice would be the one deciding they are related.
    """
    project_dir = _active_project_dir(runtime)
    project_layers = read_choice_layers(project_choices_path(project_dir)) if project_dir is not None else {}
    effective = load_choice_layers(project_dir)
    registry = runtime.get_preview_service().registry

    choices: list[PanelChoiceModel] = []
    for capability in PanelCapability:
        layer = effective.get(capability.value, {})
        project_layer = project_layers.get(capability.value, {})
        choices.extend(
            PanelChoiceModel(
                target_type=target_type,
                panel_id=panel_id,
                capability=capability.value,
                scope=_PROJECT_SCOPE if target_type in project_layer else _USER_SCOPE,
                available=registry.get(panel_id) is not None,
            )
            for target_type, panel_id in sorted(layer.items())
        )
    return PanelChoiceListResponse(choices=choices)


@router.get("/choices", response_model=PanelChoiceListResponse)
async def list_panel_choices(runtime: RuntimeDep) -> PanelChoiceListResponse:
    """Return the effective per-type, per-capability panel choices (FR-049).

    ``scope`` reports which layer each effective choice came from, so a reader
    can tell a project-only preference from a global one without diffing two
    files. ``available`` reports whether the chosen panel is registered right
    now: a choice outlives the package that provided it, and a stale one should
    read as stale rather than as missing.
    """
    return _effective_choices(runtime)


@router.put("/choices/{target_type}", response_model=PanelChoiceListResponse)
async def set_panel_choice(
    target_type: str, payload: PanelChoiceRequest, runtime: RuntimeDep
) -> PanelChoiceListResponse:
    """Record *target_type* -> ``panel_id`` for one capability at one scope.

    The panel must be registered. Routing tolerates a choice whose panel has
    since disappeared — that is the realistic case, an uninstall — but accepting
    one that never existed would store a preference that can never apply and
    give no clue why.

    Whether the panel can actually render this type is decided at routing time
    against the target's type chain, not here.
    """
    capability = _capability(payload.capability)
    path = _choices_path_for_scope(runtime, payload.scope)
    registry = runtime.get_preview_service().registry
    if registry.get(payload.panel_id) is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown panel {payload.panel_id!r}. See GET /api/panels.",
        )

    write_choice(path, target_type, payload.panel_id, capability)
    logger.info("PUT /api/panels/choices/%s: scope=%s capability=%s", target_type, payload.scope, capability.value)
    runtime.refresh_all_registries()
    return _effective_choices(runtime)


@router.delete("/choices/{target_type}", response_model=PanelChoiceListResponse)
async def clear_panel_choice(
    target_type: str,
    runtime: RuntimeDep,
    scope: str = _USER_SCOPE,
    capability: str = PanelCapability.DISPLAYING.value,
) -> PanelChoiceListResponse:
    """Remove the choice for *target_type* at *scope*, for one capability.

    Clearing a type that was never chosen succeeds: the caller's intent — no
    choice for this type here — already holds, and reporting a failure would
    only push every caller into checking first.
    """
    resolved = _capability(capability)
    path = _choices_path_for_scope(runtime, scope)
    clear_choice(path, target_type, resolved)
    logger.info("DELETE /api/panels/choices/%s: scope=%s capability=%s", target_type, scope, resolved.value)
    runtime.refresh_all_registries()
    return _effective_choices(runtime)


# ---------------------------------------------------------------------------
# T-010: reading, writing, copy-on-write, and revert (FR-024 to FR-030)
# ---------------------------------------------------------------------------


@router.get("/{panel_id}/source", response_model=PanelSourceResponse)
async def read_panel_source_route(panel_id: str, runtime: RuntimeDep) -> PanelSourceResponse:
    """Read the source of any resolved panel, whichever tier it came from (FR-024).

    ``editable`` says whether a save writes in place or copies the panel into
    the project first. It is reported rather than asked about: FR-025 says the
    system does not ask the person where to save, and this field exists so the
    interface can *say* what a save will do, not so it can offer a choice.
    """
    panel = _require_panel(runtime, panel_id)
    try:
        source = read_panel_source(panel, _discovery(runtime))
    except PanelEditError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return PanelSourceResponse(
        panel_id=source.panel_id,
        tier=source.tier.value,
        entry=source.entry,
        source=source.source,
        declaration=source.declaration,
        editable=source.editable,
        shadows=source.shadows.value if source.shadows is not None else None,
        descriptor=panel_descriptor_model(panel),
    )


@router.put("/{panel_id}/source", response_model=PanelSourceSaveResponse)
async def save_panel_source_route(
    panel_id: str, payload: PanelSourceSaveRequest, runtime: RuntimeDep
) -> PanelSourceSaveResponse:
    """Save an edit, to the tier the panel resolved from (FR-025 to FR-027).

    Nobody is asked where it goes. A project or user-library panel is written
    back in place with no second copy made; a core or package panel is copied
    into the open project under the same id, and the read-only original is not
    written. Keeping the id is what makes the copy take effect: the FR-019 tier
    ordering then shadows the original, which is the mechanism the tiers already
    had rather than a new one.

    The registry is rebuilt before the response returns, so the panel the caller
    remounts is the one that was just written (FR-030 — the host does the
    remount; this makes it possible).
    """
    panel = _require_panel(runtime, panel_id)
    try:
        saved = save_panel_source(
            panel,
            payload.source,
            project_panels_root=_writable_project_panels_root(runtime),
            declaration=payload.declaration,
        )
    except PanelNotEditableError as exc:
        raise HTTPException(status_code=409, detail=exc.message) from exc
    except PanelEditError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"panel {panel_id!r} could not be written ({exc})") from exc

    runtime.refresh_all_registries()
    reloaded = _discovery(runtime).get(panel_id)
    return PanelSourceSaveResponse(
        panel_id=saved.panel_id,
        tier=saved.tier.value,
        copied=saved.copied,
        descriptor=panel_descriptor_model(reloaded) if reloaded is not None else None,
    )


@router.delete("/{panel_id}/override", response_model=PanelOverrideRevertResponse)
async def revert_panel_override_route(panel_id: str, runtime: RuntimeDep) -> PanelOverrideRevertResponse:
    """Revert by deleting the shadowing copy (FR-029).

    Restores whichever panel the copy was shadowing. A panel that shadows
    nothing is refused rather than deleted: without an original behind it this
    would be a delete, which is a different request nobody made.
    """
    panel = _require_panel(runtime, panel_id)
    try:
        reverted = revert_panel_override(panel, _discovery(runtime))
    except PanelOverrideNotFoundError as exc:
        raise HTTPException(status_code=409, detail=exc.message) from exc
    except PanelEditError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"panel {panel_id!r} could not be removed ({exc})") from exc

    runtime.refresh_all_registries()
    restored = _discovery(runtime).get(panel_id)
    return PanelOverrideRevertResponse(
        panel_id=reverted.panel_id,
        removed_tier=reverted.removed_tier.value,
        restored_tier=reverted.restored_tier.value,
        descriptor=panel_descriptor_model(restored) if restored is not None else None,
    )


__all__ = [
    "FALLBACK_PANEL_ID",
    "PANEL_ASSET_CORS_HEADERS",
    "envelope_response",
    "panel_descriptor_model",
    "router",
]
