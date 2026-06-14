"""Functional preview providers for Spectrum and SpectralDataset (ADR-048).

These providers are NOT stubs: they read payload through the bounded
``request.data_access`` surface, build a JSON-safe envelope, and return typed
error envelopes on failure (never raise). ``Spectrum`` degrades to the core
``SERIES`` renderer; ``SpectralDataset`` degrades to the core ``COMPOSITE``
renderer when the package viewer asset fails to load.
"""

from __future__ import annotations

import logging
from typing import Any

from scistudio.core.storage.ref import StorageReference
from scistudio.previewers.models import (
    EnvelopeKind,
    PreviewEnvelope,
    PreviewMetadata,
    PreviewRequest,
    PreviewResource,
)

logger = logging.getLogger(__name__)


def _ref_for(request: PreviewRequest) -> StorageReference:
    """Build the storage reference from the session-provided query hints."""
    storage = request.query.get("_storage") or {}
    return StorageReference(
        backend=str(storage.get("backend", "filesystem")),
        path=str(storage.get("path", request.target.ref)),
        format=storage.get("format"),
        metadata=storage.get("metadata"),
    )


def _record_metadata(request: PreviewRequest) -> dict[str, Any]:
    """Return the record metadata dict the session manager attached, if any."""
    md = request.query.get("_record_metadata")
    return md if isinstance(md, dict) else {}


def _error_envelope(request: PreviewRequest, message: str) -> PreviewEnvelope:
    """Return a typed error envelope (providers must not raise — ADR-048)."""
    from scistudio.previewers.models import PreviewErrorCode, PreviewErrorInfo

    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.ERROR,
        metadata=PreviewMetadata(complete=False, failed=True),
        error=PreviewErrorInfo(code=PreviewErrorCode.PROVIDER_EXCEPTION, message=message),
    )


def spectrum_provider(request: PreviewRequest) -> PreviewEnvelope:
    """Preview a single ``Spectrum`` as a decimated line series.

    A ``Spectrum`` is stored as a 2-column table (``lambda``, ``intensity``).
    We read both columns through a bounded ``dataframe_page`` so the preview
    carries true ``(x, y)`` points rather than only the first column. The
    envelope kind is ``SERIES`` so it degrades cleanly to the core series
    renderer if the package viewer asset is unavailable.
    """
    ref = _ref_for(request)
    record_md = _record_metadata(request)
    page_size = max(2, int(getattr(request.limits, "max_rows", 256) or 256))

    points: list[dict[str, float]] = []
    total = 0
    truncated = False
    try:
        page = request.data_access.dataframe_page(ref, page=1, page_size=page_size)
        columns = list(page.columns)
        rows = list(page.rows)
        total = int(getattr(page, "total_rows", len(rows)) or len(rows))
        truncated = bool(getattr(page, "truncated", total > len(rows)))
        x_name = "lambda" if "lambda" in columns else (columns[0] if columns else None)
        y_name = "intensity" if "intensity" in columns else (columns[1] if len(columns) > 1 else None)
        for row in rows:
            if x_name is None or y_name is None or not isinstance(row, dict):
                continue
            x_val = row.get(x_name)
            y_val = row.get(y_name)
            if x_val is None or y_val is None:
                continue
            try:
                points.append({"x": float(x_val), "y": float(y_val)})
            except (TypeError, ValueError):
                continue
    except Exception as exc:
        # Fallback: try the cheaper single-column series read so a Spectrum
        # without a readable second column still previews as a line.
        logger.debug("spectrum dataframe_page failed for %s", ref.path, exc_info=True)
        try:
            series = request.data_access.series_points(ref, record_md)
            points = [dict(p) for p in series.points]
            total = int(series.total)
            truncated = bool(series.truncated)
        except Exception as inner:
            logger.debug("spectrum series fallback failed for %s", ref.path, exc_info=True)
            return _error_envelope(request, f"spectrum preview failed: {exc}; fallback: {inner}")

    table_rows = [{"lambda": p["x"], "intensity": p["y"]} for p in points]
    resources = (
        PreviewResource(
            resource_id="export",
            kind="asset",
            media_type="image/svg+xml",
            description="export the displayed spectrum as SVG",
            params={"format": "svg"},
        ),
    )
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.SERIES,
        payload={
            "points": points,
            "table": {"columns": ["lambda", "intensity"], "rows": table_rows},
            "total": total,
        },
        resources=resources,
        metadata=PreviewMetadata(
            sampled=truncated,
            truncated=truncated,
            complete=not truncated,
            extra={"total": total, "shown": len(points)},
        ),
    )


def spectral_dataset_provider(request: PreviewRequest) -> PreviewEnvelope:
    """Preview a ``SpectralDataset`` as a composite slot inventory.

    Reads the slot inventory via ``composite_slots`` (no eager child render) and
    exposes one ``child`` resource per slot plus an export action. The envelope
    kind is ``COMPOSITE`` so it degrades to the core composite renderer.
    """
    record_md = _record_metadata(request)
    try:
        slots = request.data_access.composite_slots(record_md)
    except Exception as exc:
        logger.debug("spectral dataset composite_slots failed", exc_info=True)
        return _error_envelope(request, f"spectral dataset preview failed: {exc}")

    slot_map = dict(slots.slots)
    resources = (
        *(
            PreviewResource(
                resource_id=f"slot:{name}",
                kind="child",
                description=f"child preview for slot '{name}' ({type_name})",
                params={"slot": name, "slot_type": type_name},
            )
            for name, type_name in slot_map.items()
        ),
        PreviewResource(
            resource_id="export",
            kind="asset",
            media_type="text/csv",
            description="export the visible dataset view as CSV",
            params={"format": "csv"},
        ),
    )
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.COMPOSITE,
        payload={"slots": slot_map},
        resources=resources,
        metadata=PreviewMetadata(complete=True, extra={"slot_count": len(slot_map)}),
    )


__all__ = ["spectral_dataset_provider", "spectrum_provider"]
