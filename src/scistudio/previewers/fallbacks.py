"""Core fallback previewer providers (ADR-048 FR-012 .. FR-019).

Each provider is a :data:`scistudio.previewers.models.PreviewProvider` callable
mapping a :class:`PreviewRequest` to a :class:`PreviewEnvelope`. They read only
through the bounded :class:`PreviewDataAccess` on the request (FR-010) and embed
typed error envelopes instead of raising for routine failures (FR-028).

Providers (and their core :class:`PreviewerSpec` ids):

* ``core.dataframe.basic`` — :func:`dataframe_previewer`
* ``core.array.basic`` — :func:`array_previewer` (GENERIC numeric only;
  NO image-domain LUT/OME/channel/label semantics, FR-013/FR-014)
* ``core.series.basic`` — :func:`series_previewer` (chart + table, FR-015)
* ``core.text.basic`` — :func:`text_previewer` (FR-016)
* ``core.artifact.basic`` — :func:`artifact_previewer`
* ``core.composite.basic`` — :func:`composite_previewer` (slot inventory, FR-017)
* ``core.collection.basic`` — :func:`collection_previewer` (FR-009, tier-7 fallback)
* ``core.plot.basic`` — :func:`plot_previewer` (PNG/JPEG/SVG/PDF, FR-018/FR-019)
* ``core.base.fallback`` — :func:`base_fallback_previewer` (tier-8 universal)

The collection and base fallbacks declare the sentinel ``target_type`` values
``"Collection"`` / ``"DataObject"`` that :class:`PreviewRouter` matches for the
core catch-all tiers.
"""

from __future__ import annotations

import logging

from scistudio.core.storage.ref import StorageReference
from scistudio.previewers.helpers import sanitize_svg
from scistudio.previewers.models import (
    EnvelopeKind,
    OwnerKind,
    PreviewEnvelope,
    PreviewerSpec,
    PreviewMetadata,
    PreviewRequest,
    PreviewResource,
)

# Back-compat re-export: ``sanitize_svg`` moved to the public
# ``scistudio.previewers.helpers`` home in #1823 (ADR-052 §8). It is re-exported
# here (and intentionally kept out of ``__all__``) so an out-of-tree package that
# still imports ``from scistudio.previewers.fallbacks import sanitize_svg`` does
# not hard-break before it migrates.
# TODO(#1817): drop this re-export once scistudio-blocks-spectroscopy imports
#   sanitize_svg from scistudio.previewers.helpers.
#   Followup: https://github.com/jiazhenz026/SciStudio/issues/1817

logger = logging.getLogger(__name__)

_PLOT_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
}


def _ref_for(request: PreviewRequest) -> StorageReference:
    """Return the runtime-resolved StorageReference for the target (FR-009, ADR-052 §8.5).

    The sanctioned path is :attr:`PreviewRequest.storage`, which the
    :class:`~scistudio.previewers.session.PreviewSessionManager` populates so
    providers need no catalog access — this is what a package previewer reads.
    The legacy ``query["_storage"]`` rebuild is kept only as a defensive
    fallback for a request constructed outside the session manager.
    """
    if request.storage is not None:
        return request.storage
    storage = request.query.get("_storage") or {}
    return StorageReference(
        backend=str(storage.get("backend", "filesystem")),
        path=str(storage.get("path", request.target.ref)),
        format=storage.get("format"),
        metadata=storage.get("metadata"),
    )


def _record_metadata(request: PreviewRequest) -> dict[str, object]:
    """Return the recorded data-record metadata (ADR-052 §8.5).

    Prefers the typed :attr:`PreviewRequest.record_metadata`; falls back to the
    legacy ``query["_record_metadata"]`` for requests built outside the session
    manager.
    """
    if request.record_metadata:
        return request.record_metadata
    md = request.query.get("_record_metadata")
    return md if isinstance(md, dict) else {}


def _error_envelope(request: PreviewRequest, code: object, message: str) -> PreviewEnvelope:
    from scistudio.previewers.models import PreviewErrorCode, PreviewErrorInfo

    err_code = code if isinstance(code, PreviewErrorCode) else PreviewErrorCode.PROVIDER_EXCEPTION
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.ERROR,
        metadata=PreviewMetadata(complete=False, failed=True),
        error=PreviewErrorInfo(code=err_code, message=message),
    )


# ---------------------------------------------------------------------------
# DataFrame
# ---------------------------------------------------------------------------


def dataframe_previewer(request: PreviewRequest) -> PreviewEnvelope:
    """Paginated DataFrame preview (FR-009 acceptance scenario 1)."""
    ref = _ref_for(request)
    q = request.query
    page = _coerce_int(q.get("page"), 1)
    page_size = _coerce_int(q.get("page_size"), 50)
    sort_by = q.get("sort_by")
    sort_dir = str(q.get("sort_dir") or "asc")
    try:
        result = request.data_access.dataframe_page(
            ref,
            page=page,
            page_size=page_size,
            sort_by=str(sort_by) if sort_by else None,
            sort_dir=sort_dir,
        )
    except Exception as exc:
        logger.debug("dataframe preview failed for %s", ref.path, exc_info=True)
        return _error_envelope(request, None, f"dataframe preview failed: {exc}")
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.DATAFRAME,
        payload={
            "columns": result.columns,
            "rows": result.rows,
            "total_rows": result.total_rows,
            "page": result.page,
            "page_size": result.page_size,
            "total_pages": result.total_pages,
            "sort_by": result.sort_by,
            "sort_dir": result.sort_dir,
        },
        metadata=PreviewMetadata(
            truncated=result.truncated,
            complete=not result.truncated,
            extra={"total_rows": result.total_rows},
        ),
    )


# ---------------------------------------------------------------------------
# Array (GENERIC numeric only — FR-013 / FR-014)
# ---------------------------------------------------------------------------


def array_previewer(request: PreviewRequest) -> PreviewEnvelope:
    """Generic numeric array preview: shape/dtype/axes + one bounded 2-D plane.

    The displayed plane is surfaced as the actual numeric ``matrix`` plus its
    finite ``vmin`` / ``vmax`` so the frontend renders a value-readable numeric
    heatmap table with a diverging/sequential colormap and a min..max legend
    (PyCharm-style) — no lossy grayscale PNG and no negative clipping. Every
    non-displayed axis is independently navigable via ``slice_axes`` and the
    per-axis ``axis_indices`` query field.

    Strictly generic per FR-013/FR-014: no image-domain LUT/OME/channel/label
    semantics. Rich image controls belong to ``scistudio-blocks-imaging``.
    """
    ref = _ref_for(request)
    slice_index = _coerce_int(request.query.get("slice_index"), 0)
    axis_indices = _coerce_axis_indices(request.query.get("axis_indices"))
    try:
        plane = request.data_access.array_plane(ref, slice_index=slice_index, axis_indices=axis_indices)
    except Exception as exc:
        logger.debug("array preview failed for %s; degrading to artifact", ref.path, exc_info=True)
        return _degrade_to_artifact(request, ref, reason=f"array decode failed: {exc}")

    slice_axes = [{"axis": ax.axis, "name": ax.name, "size": ax.size, "index": ax.index} for ax in plane.slice_axes]
    # The numeric heatmap table (matrix + vmin/vmax) is the primary view; the
    # core ArrayViewer ignores ``src``. The grayscale PNG ``src`` is retained as
    # the raster fallback that the imaging package's Image previewer reuses when
    # its packaged viewer module fails to load (FR-026).
    src = request.data_access.png_data_uri(plane.matrix)
    resources = (
        PreviewResource(
            resource_id="tile",
            kind="tile",
            media_type="application/json",
            description="bounded array tile read",
            params={"slice_index": plane.slice_index or 0},
        ),
    )
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.ARRAY,
        payload={
            "shape": plane.shape,
            "dtype": plane.dtype,
            "axes": plane.axes,
            "ndim": plane.ndim,
            "slice_axis_name": plane.slice_axis_name,
            "slice_axis_size": plane.slice_axis_size,
            "slice_index": plane.slice_index,
            "slice_axes": slice_axes,
            "matrix": plane.matrix,
            # ``thumbnail`` kept as an alias of the numeric matrix so the
            # scalar/1-D code paths and any older readers keep working.
            "thumbnail": plane.matrix,
            "vmin": plane.vmin,
            "vmax": plane.vmax,
            # Raster fallback for package viewers; NOT used by the numeric viewer.
            "src": src,
        },
        resources=resources,
        metadata=PreviewMetadata(
            sampled=plane.truncated,
            truncated=plane.truncated,
            complete=not plane.truncated,
            extra={"shape": plane.shape, "dtype": plane.dtype, "axes": plane.axes},
        ),
    )


def _coerce_axis_indices(value: object) -> dict[int, int]:
    """Coerce a JSON-ish ``{axis: index}`` mapping to ``dict[int, int]``.

    The session query carries per-axis selections as a plain dict (string or
    int keys after a JSON round-trip). Non-numeric / malformed entries are
    dropped rather than raising so a bad client patch degrades to slice 0.
    """
    if not isinstance(value, dict):
        return {}
    result: dict[int, int] = {}
    for key, idx in value.items():
        try:
            result[int(key)] = int(idx)
        except (TypeError, ValueError):
            continue
    return result


def _degrade_to_artifact(request: PreviewRequest, ref: StorageReference, *, reason: str) -> PreviewEnvelope:
    info = request.data_access.artifact_metadata(ref)
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.ARTIFACT,
        payload={"path": info.path, "mime_type": info.mime_type, "size_bytes": info.size_bytes},
        diagnostics=(reason,),
        metadata=PreviewMetadata(complete=False, derived=True),
    )


# ---------------------------------------------------------------------------
# Series (FR-015)
# ---------------------------------------------------------------------------


def series_previewer(request: PreviewRequest) -> PreviewEnvelope:
    """Series preview with complete chart points and a table view (FR-015)."""
    ref = _ref_for(request)
    metadata = _record_metadata(request)
    try:
        result = request.data_access.series_points(ref, metadata)
    except Exception as exc:
        logger.debug("series preview failed for %s", ref.path, exc_info=True)
        return _error_envelope(request, None, f"series preview failed: {exc}")
    diagnostics: list[str] = []
    if result.nonnumeric:
        diagnostics.append(f"skipped {result.nonnumeric} nonnumeric row(s)")
    table_rows = [{"index": p["x"], "value": p["y"]} for p in result.points]
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.SERIES,
        payload={
            "points": result.points,
            "table": {"columns": ["index", "value"], "rows": table_rows},
            "total": result.total,
        },
        diagnostics=tuple(diagnostics),
        metadata=PreviewMetadata(
            sampled=False,
            truncated=False,
            complete=result.nonnumeric == 0,
            extra={"total": result.total, "shown": len(result.points), "nonnumeric_rows": result.nonnumeric},
        ),
    )


# ---------------------------------------------------------------------------
# Text (FR-016)
# ---------------------------------------------------------------------------


def text_previewer(request: PreviewRequest) -> PreviewEnvelope:
    """Bounded plain-text preview with truncation marker + editor handoff (FR-016)."""
    ref = _ref_for(request)
    try:
        chunk = request.data_access.text_chunk(ref)
    except Exception as exc:
        return _error_envelope(request, None, f"text preview failed: {exc}")
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.TEXT,
        payload={
            "content": chunk.content,
            "language": chunk.language,
            "truncated": chunk.truncated,
            # Editor handoff metadata: the frontend can open the full file in
            # the embedded editor for long text instead of inlining megabytes.
            "editor_handoff": {
                "ref": request.target.ref,
                "total_bytes": chunk.total_bytes,
                "shown_bytes": len(chunk.content.encode("utf-8")),
            },
        },
        metadata=PreviewMetadata(
            truncated=chunk.truncated,
            complete=not chunk.truncated,
            extra={"total_bytes": chunk.total_bytes},
        ),
    )


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------


def artifact_previewer(request: PreviewRequest) -> PreviewEnvelope:
    """Opaque artifact preview: path + mime + size (bounded)."""
    ref = _ref_for(request)
    info = request.data_access.artifact_metadata(ref)
    payload: dict[str, object] = {"path": info.path, "mime_type": info.mime_type, "size_bytes": info.size_bytes}
    if info.data_uri is not None:
        payload["src"] = info.data_uri
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.ARTIFACT,
        payload=payload,
        metadata=PreviewMetadata(extra={"size_bytes": info.size_bytes}),
    )


# ---------------------------------------------------------------------------
# Composite (FR-017)
# ---------------------------------------------------------------------------


def composite_previewer(request: PreviewRequest) -> PreviewEnvelope:
    """Composite preview: slot inventory first; child routed only on select (FR-017)."""
    metadata = _record_metadata(request)
    slots = request.data_access.composite_slots(metadata)
    selected_slot = request.query.get("slot")
    payload: dict[str, object] = {"slots": slots.slots}
    resources = tuple(
        PreviewResource(
            resource_id=f"slot:{name}",
            kind="child",
            description=f"child preview for slot '{name}' ({type_name})",
            params={"slot": name, "slot_type": type_name},
        )
        for name, type_name in slots.slots.items()
    )
    if selected_slot:
        payload["selected_slot"] = str(selected_slot)
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.COMPOSITE,
        payload=payload,
        resources=resources,
        metadata=PreviewMetadata(extra={"slot_count": len(slots.slots)}),
    )


# ---------------------------------------------------------------------------
# Collection (FR-009 — core tier-7 fallback)
# ---------------------------------------------------------------------------


def collection_previewer(request: PreviewRequest) -> PreviewEnvelope:
    """Collection fallback: count + item types + bounded sampled refs (FR-009)."""
    q = request.query
    raw_items = q.get("_collection_items")
    items = raw_items if isinstance(raw_items, list) else []
    count = _coerce_int(q.get("_collection_count"), len(items))
    item_type = q.get("_collection_item_type") or request.target.collection_item_type
    sample = request.data_access.collection_sample(
        count=count,
        item_type=str(item_type) if item_type else None,
        items=[i for i in items if isinstance(i, dict)],
    )
    resources = tuple(
        PreviewResource(
            resource_id=f"item:{idx}",
            kind="child",
            description="child preview for a collection item",
            params={"index": idx, "item": item},
        )
        for idx, item in enumerate(sample.items)
    )
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.COLLECTION,
        payload={
            "count": sample.count,
            "item_type": sample.item_type,
            "items": sample.items,
        },
        resources=resources,
        metadata=PreviewMetadata(
            sampled=sample.sampled,
            complete=not sample.sampled,
            extra={"count": sample.count, "item_type": sample.item_type},
        ),
    )


# ---------------------------------------------------------------------------
# Plot (FR-018 / FR-019)
# ---------------------------------------------------------------------------


def plot_previewer(request: PreviewRequest) -> PreviewEnvelope:
    """Static plot artifact viewer for PNG / JPEG / SVG / PDF (FR-018).

    SVG is sanitized so script execution and external-resource loading do not
    run in the app context (FR-019). Each supported format exposes a
    save/export resource descriptor.
    """
    from pathlib import Path

    ref = _ref_for(request)
    path = Path(ref.path)
    suffix = path.suffix.lower()
    mime = _PLOT_MIME.get(suffix)
    if mime is None:
        return _error_envelope(request, None, f"unsupported plot artifact format: {suffix or '<none>'}")

    payload: dict[str, object] = {"format": suffix.lstrip("."), "mime_type": mime, "path": ref.path}
    diagnostics: list[str] = []

    if suffix == ".svg":
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return _error_envelope(request, None, f"svg read failed: {exc}")
        sanitized, removed = sanitize_svg(raw)
        payload["svg"] = sanitized
        payload["sandboxed"] = True
        if removed:
            diagnostics.append("sanitized SVG: removed script/handler/external-resource content")
    else:
        info = request.data_access.artifact_metadata(ref, mime_type=mime)
        if info.data_uri is not None:
            payload["src"] = info.data_uri
        payload["size_bytes"] = info.size_bytes

    # Save/export resource per supported format.
    resources = (
        PreviewResource(
            resource_id="export",
            kind="asset",
            media_type=mime,
            description=f"download/export this plot as {suffix.lstrip('.')}",
            params={"format": suffix.lstrip(".")},
        ),
    )
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.PLOT,
        payload=payload,
        resources=resources,
        diagnostics=tuple(diagnostics),
        metadata=PreviewMetadata(extra={"format": suffix.lstrip(".")}),
    )


# ---------------------------------------------------------------------------
# Universal base fallback (tier-8 catch-all)
# ---------------------------------------------------------------------------


def base_fallback_previewer(request: PreviewRequest) -> PreviewEnvelope:
    """Tier-8 universal fallback: treat anything unknown as an artifact."""
    return artifact_previewer(request)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_int(value: object, default: int) -> int:
    """Coerce *value* to int, returning *default* on failure/None."""
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


# ---------------------------------------------------------------------------
# Core spec registration
# ---------------------------------------------------------------------------


def core_previewer_specs() -> list[PreviewerSpec]:
    """Return the core fallback :class:`PreviewerSpec` list (FR-012).

    These are registered unconditionally by :meth:`PreviewerRegistry.load_core`.
    The collection and base specs use the sentinel ``target_type`` values the
    router matches for the core catch-all tiers (``"Collection"`` / ``"DataObject"``).
    """
    return [
        PreviewerSpec(
            previewer_id="core.dataframe.basic",
            owner_kind=OwnerKind.CORE,
            owner_name="scistudio",
            target_type="DataFrame",
            capabilities=("table", "page", "sort"),
            backend_provider=dataframe_previewer,
        ),
        PreviewerSpec(
            previewer_id="core.array.basic",
            owner_kind=OwnerKind.CORE,
            owner_name="scistudio",
            target_type="Array",
            capabilities=("shape", "slice", "matrix", "colormap"),
            backend_provider=array_previewer,
        ),
        PreviewerSpec(
            previewer_id="core.series.basic",
            owner_kind=OwnerKind.CORE,
            owner_name="scistudio",
            target_type="Series",
            capabilities=("chart", "table"),
            backend_provider=series_previewer,
        ),
        PreviewerSpec(
            previewer_id="core.text.basic",
            owner_kind=OwnerKind.CORE,
            owner_name="scistudio",
            target_type="Text",
            capabilities=("text", "truncate", "editor_handoff"),
            backend_provider=text_previewer,
        ),
        PreviewerSpec(
            previewer_id="core.artifact.basic",
            owner_kind=OwnerKind.CORE,
            owner_name="scistudio",
            target_type="Artifact",
            capabilities=("download",),
            backend_provider=artifact_previewer,
        ),
        PreviewerSpec(
            previewer_id="core.composite.basic",
            owner_kind=OwnerKind.CORE,
            owner_name="scistudio",
            target_type="CompositeData",
            capabilities=("slots", "child_routing"),
            backend_provider=composite_previewer,
        ),
        PreviewerSpec(
            previewer_id="core.collection.basic",
            owner_kind=OwnerKind.CORE,
            owner_name="scistudio",
            target_type="Collection",
            supports_collection=True,
            capabilities=("count", "sample", "child_routing"),
            backend_provider=collection_previewer,
        ),
        PreviewerSpec(
            previewer_id="core.plot.basic",
            owner_kind=OwnerKind.CORE,
            owner_name="scistudio",
            target_type="PlotArtifact",
            capabilities=("png", "jpeg", "svg", "pdf", "export"),
            backend_provider=plot_previewer,
        ),
        PreviewerSpec(
            previewer_id="core.base.fallback",
            owner_kind=OwnerKind.CORE,
            owner_name="scistudio",
            target_type="DataObject",
            priority=-100,
            capabilities=("download",),
            backend_provider=base_fallback_previewer,
        ),
    ]


__all__ = [
    "array_previewer",
    "artifact_previewer",
    "base_fallback_previewer",
    "collection_previewer",
    "composite_previewer",
    "core_previewer_specs",
    "dataframe_previewer",
    "plot_previewer",
    "series_previewer",
    "text_previewer",
]
