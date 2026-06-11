"""Package-owned Image/Label previewers (ADR-048 SPEC 1, FR-025 / FR-026).

This module migrates the *rich* image-domain preview behaviour
(``frontend/src/components/DataPreview.parts/ImageViewer.tsx``: LUT colormaps,
display range, single-axis slice slider, zoom/pan, OME/channel metadata) out of
core and into the ``scistudio-blocks-imaging`` package. Core keeps only the
*generic* numeric Array fallback (``core.array.basic``); the imaging package
owns the ``Image`` and ``Label`` target types (ADR-048 §4, §6).

What this module provides:

* :func:`get_previewers` — the ``scistudio.previewers`` factory returning a
  :class:`~scistudio.previewers.models.PreviewerSpec` for ``Image`` and
  ``Label``. It is re-exported from the package top-level ``__init__`` so the
  monorepo dev fallback (``PreviewerRegistry._scan_monorepo_packages``)
  discovers it, and wired as a ``scistudio.previewers`` entry point in
  ``pyproject.toml`` for installed-mode discovery.
* :func:`image_provider` / :func:`label_provider` — backend
  :data:`~scistudio.previewers.models.PreviewProvider` callables. They read
  bounded data through ``request.data_access`` (never materialising a full
  array — FR-010) and return a :class:`PreviewEnvelope`.

Manifest-delivery seam (FR-022/FR-024 + the verified frontend host contract):
the preview *session* envelope does not otherwise carry the spec's frontend
manifest. The frontend ``PreviewHost`` reads it from
``envelope.metadata.extra["frontend_manifest"]``. Therefore each provider here
embeds its :meth:`FrontendManifest.to_dict` (the wire shape WITHOUT
``asset_root``) into ``metadata.extra["frontend_manifest"]`` so the host can
locate and same-origin-import the packaged viewer module.

Fallback design (FR-026): the Image envelope uses ``kind=ARRAY`` and carries a
PNG ``src`` data-URI plus shape/axes/slice metadata in exactly the shape the
core Array viewer understands. If the dynamically-loaded packaged JS module
fails to load (remote-URL rejection, import error, version mismatch), the host
falls back to the core Array viewer for the same envelope with no extra round
trip.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from scistudio.core.storage.ref import StorageReference
from scistudio.previewers.models import (
    PREVIEWER_API_VERSION,
    EnvelopeKind,
    FrontendManifest,
    OwnerKind,
    PreviewEnvelope,
    PreviewerSpec,
    PreviewMetadata,
    PreviewRequest,
    PreviewResource,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Identity + manifest constants
# ---------------------------------------------------------------------------

#: Stable previewer ids. Project/package previewer ids are namespaced by owner.
IMAGE_PREVIEWER_ID = "imaging.image.viewer"
LABEL_PREVIEWER_ID = "imaging.label.viewer"

#: Owning package name (matches the distribution / monorepo dir).
OWNER_NAME = "scistudio-blocks-imaging"

#: Bundle version. Bumped when ``assets/viewer.js`` changes so the host can
#: cache-bust. Tracks the package version it ships with.
VIEWER_BUNDLE_VERSION = "0.1.0"

#: Backend-relative, same-origin module URL the host imports the ESM viewer
#: from. The API runtime serves it via ``/api/previews/assets/<id>/<file>``
#: after path-confinement under ``asset_root`` (FR-022/FR-024).
_VIEWER_FILE = "viewer.js"

#: Filesystem directory the package confines its frontend assets under. Never
#: serialised to the frontend; used only by the backend asset validator.
_ASSET_ROOT = str(Path(__file__).resolve().parent / "assets")


def _module_url(previewer_id: str) -> str:
    return f"/api/previews/assets/{previewer_id}/{_VIEWER_FILE}"


def _frontend_manifest(previewer_id: str) -> FrontendManifest:
    """Build the same-origin :class:`FrontendManifest` for *previewer_id*."""
    return FrontendManifest(
        previewer_id=previewer_id,
        module_url=_module_url(previewer_id),
        export_name="default",
        css=(),
        version=VIEWER_BUNDLE_VERSION,
        api_version=PREVIEWER_API_VERSION,
        asset_root=_ASSET_ROOT,
    )


# ---------------------------------------------------------------------------
# Request helpers (mirror scistudio.previewers.fallbacks conventions)
# ---------------------------------------------------------------------------


def _ref_for(request: PreviewRequest) -> StorageReference:
    """Build a ``StorageReference`` from the runtime-provided ``_storage`` dict.

    The session manager places the resolved storage descriptor on
    ``request.query['_storage']`` so providers never need catalog access — the
    exact convention the core fallbacks use.
    """
    storage = request.query.get("_storage") or {}
    return StorageReference(
        backend=str(storage.get("backend", "filesystem")),
        path=str(storage.get("path", request.target.ref)),
        format=storage.get("format"),
        metadata=storage.get("metadata"),
    )


def _record_metadata(request: PreviewRequest) -> dict[str, Any]:
    md = request.query.get("_record_metadata")
    return md if isinstance(md, dict) else {}


def _coerce_int(value: object, default: int) -> int:
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


def _image_metadata_panel(record_md: dict[str, Any]) -> dict[str, Any]:
    """Extract a bounded, JSON-safe OME/channel metadata panel.

    Surfaces only display-relevant scalar fields from the recorded ``Image``/
    ``Label`` metadata so the packaged viewer can render an info panel without
    ever materialising the full OME-XML model. Unknown shapes are skipped.
    """
    panel: dict[str, Any] = {}
    for key in (
        "pixel_size",
        "z_spacing",
        "time_interval",
        "objective",
        "instrument",
        "acquisition_date",
        "source_file",
        "wavelengths_nm",
        "n_objects",
    ):
        value = record_md.get(key)
        if value is not None and isinstance(value, (str, int, float, list)):
            panel[key] = value

    channels = record_md.get("channels")
    if isinstance(channels, list):
        bounded: list[dict[str, Any]] = []
        for ch in channels:
            if isinstance(ch, dict):
                name = ch.get("name")
                entry: dict[str, Any] = {}
                if isinstance(name, str):
                    entry["name"] = name
                exc = ch.get("excitation_nm")
                if isinstance(exc, (int, float)):
                    entry["excitation_nm"] = exc
                if entry:
                    bounded.append(entry)
            elif isinstance(ch, str):
                bounded.append({"name": ch})
        if bounded:
            panel["channels"] = bounded

    # OME is recorded but is a large model; expose only a presence flag.
    if record_md.get("ome") is not None:
        panel["has_ome"] = True
    return panel


def _embed_manifest(metadata_extra: dict[str, Any], previewer_id: str) -> dict[str, Any]:
    """Return ``metadata_extra`` with the wire frontend manifest embedded.

    The verified seam: the frontend host reads the manifest from
    ``envelope.metadata.extra['frontend_manifest']`` because the session
    envelope does not otherwise carry it.
    """
    enriched = dict(metadata_extra)
    enriched["frontend_manifest"] = _frontend_manifest(previewer_id).to_dict()
    return enriched


def _error_envelope(request: PreviewRequest, message: str) -> PreviewEnvelope:
    """Embed a typed error envelope (providers must not raise for routine
    failures — FR-028)."""
    from scistudio.previewers.models import PreviewErrorCode, PreviewErrorInfo

    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.ERROR,
        metadata=PreviewMetadata(
            complete=False,
            failed=True,
            extra=_embed_manifest({}, request.spec.previewer_id),
        ),
        error=PreviewErrorInfo(code=PreviewErrorCode.PROVIDER_EXCEPTION, message=message),
    )


# ---------------------------------------------------------------------------
# Image provider (rich image-domain preview; kind=ARRAY for core fallback)
# ---------------------------------------------------------------------------


def image_provider(request: PreviewRequest) -> PreviewEnvelope:
    """Render a rich Image preview envelope (ADR-048 FR-025).

    Reads one bounded, downsampled 2-D plane via ``request.data_access`` and
    encodes it as a grayscale PNG data-URI (the same payload the core Array
    viewer consumes). The packaged JS viewer adds LUT, display-range, slice
    slider, zoom/pan, and an OME/channel info panel on top. ``kind=ARRAY`` so a
    failed dynamic-module load degrades cleanly to the core Array viewer
    (FR-026).
    """
    ref = _ref_for(request)
    slice_index = _coerce_int(request.query.get("slice_index"), 0)
    try:
        plane = request.data_access.array_plane(ref, slice_index=slice_index)
    except Exception as exc:
        logger.debug("imaging image preview failed for %s", ref.path, exc_info=True)
        return _error_envelope(request, f"image preview failed: {exc}")

    src = request.data_access.png_data_uri(plane.matrix)
    record_md = _record_metadata(request)
    info_panel = _image_metadata_panel(record_md)

    resources = (
        PreviewResource(
            resource_id="tile",
            kind="tile",
            media_type="application/json",
            description="bounded image tile read",
            params={"slice_index": plane.slice_index or 0},
        ),
        PreviewResource(
            resource_id="export",
            kind="asset",
            media_type="image/png",
            description="export the displayed image plane as PNG",
            params={"format": "png", "slice_index": plane.slice_index or 0},
        ),
    )

    extra: dict[str, Any] = {
        "shape": plane.shape,
        "dtype": plane.dtype,
        "axes": plane.axes,
        "image_metadata": info_panel,
    }
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
            "thumbnail": plane.matrix,
            "src": src,
            "image_metadata": info_panel,
        },
        resources=resources,
        metadata=PreviewMetadata(
            sampled=plane.truncated,
            truncated=plane.truncated,
            complete=not plane.truncated,
            extra=_embed_manifest(extra, request.spec.previewer_id),
        ),
    )


# ---------------------------------------------------------------------------
# Label provider (composite: raster + polygon slot inventory)
# ---------------------------------------------------------------------------


def label_provider(request: PreviewRequest) -> PreviewEnvelope:
    """Render a Label preview envelope (ADR-048 FR-025).

    A ``Label`` is a ``CompositeData`` with ``raster`` and/or ``polygons``
    slots. This provider surfaces the slot inventory (no eager child render),
    a bounded raster plane (as a PNG data-URI) when a raster slot exists, and
    the OME/object-count metadata panel. ``kind=COMPOSITE`` so the host routes
    to the packaged label viewer (and to the core composite viewer if the
    dynamic module fails).
    """
    record_md = _record_metadata(request)
    slots = request.data_access.composite_slots(record_md)
    info_panel = _image_metadata_panel(record_md)

    payload: dict[str, Any] = {"slots": slots.slots, "image_metadata": info_panel}
    diagnostics: list[str] = []
    truncated = False

    # Bounded raster preview when a raster slot is present.
    ref = _ref_for(request)
    raster_plane = None
    if "raster" in slots.slots:
        try:
            raster_plane = request.data_access.composite_raster_slot(ref, slot_name="raster")
        except Exception as exc:  # pragma: no cover - defensive
            diagnostics.append(f"raster slot preview failed: {exc}")
    if raster_plane is not None:
        truncated = bool(raster_plane.truncated)
        payload["raster"] = {
            "shape": raster_plane.shape,
            "dtype": raster_plane.dtype,
            "axes": raster_plane.axes,
            "ndim": raster_plane.ndim,
            "slice_axis_name": raster_plane.slice_axis_name,
            "slice_axis_size": raster_plane.slice_axis_size,
            "slice_index": raster_plane.slice_index,
            "thumbnail": raster_plane.matrix,
            "src": request.data_access.png_data_uri(raster_plane.matrix),
        }

    resources = tuple(
        PreviewResource(
            resource_id=f"slot:{name}",
            kind="child",
            description=f"child preview for slot '{name}' ({type_name})",
            params={"slot": name, "slot_type": type_name},
        )
        for name, type_name in slots.slots.items()
    )

    extra: dict[str, Any] = {
        "slot_count": len(slots.slots),
        "image_metadata": info_panel,
    }
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.COMPOSITE,
        payload=payload,
        resources=resources,
        diagnostics=tuple(diagnostics),
        metadata=PreviewMetadata(
            sampled=truncated,
            truncated=truncated,
            complete=not truncated,
            extra=_embed_manifest(extra, request.spec.previewer_id),
        ),
    )


# ---------------------------------------------------------------------------
# Factory (entry point + monorepo discovery)
# ---------------------------------------------------------------------------


def get_previewers() -> list[PreviewerSpec]:
    """Return the imaging package's :class:`PreviewerSpec` list (FR-002/FR-025).

    Registered two ways:

    * installed mode — the ``scistudio.previewers`` entry point in
      ``pyproject.toml`` resolves
      ``scistudio_blocks_imaging.previewers:get_previewers``;
    * monorepo dev mode — re-exported from the package top-level ``__init__``,
      discovered by ``PreviewerRegistry._scan_monorepo_packages``.

    Both ``Image`` and ``Label`` specs declare ``owner_kind=PACKAGE`` with a
    positive ``priority`` so they win exact-type routing over the core
    fallbacks while still degrading to them when imaging is absent (FR-026).
    """
    return [
        PreviewerSpec(
            previewer_id=IMAGE_PREVIEWER_ID,
            owner_kind=OwnerKind.PACKAGE,
            owner_name=OWNER_NAME,
            target_type="Image",
            supports_collection=False,
            priority=100,
            capabilities=("slice", "lut", "range", "zoom", "metadata", "export"),
            backend_provider=image_provider,
            frontend_manifest=_frontend_manifest(IMAGE_PREVIEWER_ID),
        ),
        PreviewerSpec(
            previewer_id=LABEL_PREVIEWER_ID,
            owner_kind=OwnerKind.PACKAGE,
            owner_name=OWNER_NAME,
            target_type="Label",
            supports_collection=False,
            priority=100,
            capabilities=("slots", "raster", "metadata", "export"),
            backend_provider=label_provider,
            frontend_manifest=_frontend_manifest(LABEL_PREVIEWER_ID),
        ),
    ]


__all__ = [
    "IMAGE_PREVIEWER_ID",
    "LABEL_PREVIEWER_ID",
    "OWNER_NAME",
    "VIEWER_BUNDLE_VERSION",
    "get_previewers",
    "image_provider",
    "label_provider",
]
