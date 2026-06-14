"""Functional preview providers for Spectrum and SpectralDataset (ADR-048).

These providers are NOT stubs: they read payload through the bounded
``request.data_access`` surface, build a JSON-safe envelope, and return typed
error envelopes on failure (never raise). ``Spectrum`` degrades to the core
``SERIES`` renderer; ``SpectralDataset`` degrades to the core ``COMPOSITE``
renderer when the package viewer asset fails to load.

Spec coverage:

- ``spectrum_provider`` — FR-018/FR-019/FR-020/FR-021 + US1 acceptance #2/#3.
  A ``Spectrum`` is a two-column table (``lambda``, ``intensity``); both columns
  are read with a bounded ``dataframe_page`` so the preview carries true
  ``(x, y)`` points (``series_points`` would only read one column). Honest
  sampling/truncation flags come from the bounded read; a missing-unit / empty /
  nonnumeric diagnostic is reported but the plot still renders.
- ``spectral_dataset_provider`` — FR-022..FR-029. The ``index`` slot is read as
  a paginated table; the ``spectra`` slot is read (bounded) only for dataset
  health diagnostics (FR-027). Capabilities and plot-mode names are exposed so
  the explorer UI can offer them. Bounded reads only (FR-028).

FR-030: these providers perform NO scientific processing — only bounded reads,
shape inspection, and integrity (join/schema/unit/numeric/alignment) checks.
"""

from __future__ import annotations

import logging
from pathlib import Path
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

#: Canonical Spectrum / dataset column names (mirrors ``types`` constants but
#: kept local so this module never imports the block layer).
_LAMBDA = "lambda"
_INTENSITY = "intensity"
_SPECTRUM_ID = "spectrum_id"

#: Bounded plot modes the SpectralDataset explorer offers (FR-025).
_PLOT_MODES = ("overlay", "selected", "group_mean", "group_band", "heatmap")

#: Declared explorer capabilities (FR-024 / FR-025 / spec capability table).
_DATASET_CAPABILITIES = ("table", "filter", "group", "plot", "diagnostics", "export")
_SPECTRUM_CAPABILITIES = ("plot", "navigate", "diagnostics", "export")

#: Figure export formats exposed for both previewers (FR-021 / FR-029).
_FIGURE_FORMATS = ("svg", "png", "pdf")
_FIGURE_MEDIA = {"svg": "image/svg+xml", "png": "image/png", "pdf": "application/pdf"}


# ---------------------------------------------------------------------------
# Request helpers (mirror scistudio.previewers.fallbacks / imaging conventions)
# ---------------------------------------------------------------------------


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


def _page_size(request: PreviewRequest, default: int = 256) -> int:
    """Bounded page size: honor the session ``max_rows`` budget (FR-020/FR-028)."""
    limit = getattr(request.limits, "max_rows", None)
    try:
        return max(2, int(limit)) if limit else default
    except (TypeError, ValueError):
        return default


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


def _finite_float(value: Any) -> float | None:
    """Return a real, finite ``float`` for a numeric cell, else ``None``.

    ``bool`` is excluded (it is a numeric subtype we never want as data) and
    ``NaN`` / ``+-inf`` are rejected so the JSON payload stays plottable.
    """
    if isinstance(value, bool) or value is None or not isinstance(value, (int, float)):
        return None
    out = float(value)
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


# ---------------------------------------------------------------------------
# Spectrum provider (kind=SERIES -> degrades to core.series.basic)
# ---------------------------------------------------------------------------


def _spectrum_units(record_md: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    """Pull display units / kind / modality from recorded Spectrum metadata.

    Reads only scalar fields from ``_record_metadata`` (the worker-stamped
    catalog record); never materializes a typed ``Meta`` model.
    """

    def _scalar(key: str) -> str | None:
        value = record_md.get(key)
        return value if isinstance(value, str) and value else None

    return (
        _scalar("lambda_unit"),
        _scalar("intensity_unit"),
        _scalar("lambda_kind"),
        _scalar("modality"),
    )


def spectrum_provider(request: PreviewRequest) -> PreviewEnvelope:
    """Preview a single ``Spectrum`` as a decimated 2-D line series.

    A ``Spectrum`` is stored as a two-column table (``lambda``, ``intensity``).
    Both columns are read through a bounded ``dataframe_page`` so the preview
    carries true ``(x, y)`` points rather than only the first column. The
    envelope kind is ``SERIES`` so it degrades cleanly to the core series
    renderer when the package viewer asset is unavailable (FR-018/FR-026).
    """
    ref = _ref_for(request)
    record_md = _record_metadata(request)
    page_size = _page_size(request)
    lambda_unit, intensity_unit, lambda_kind, modality = _spectrum_units(record_md)

    points: list[dict[str, float]] = []
    total = 0
    truncated = False
    nonnumeric = 0
    diagnostics: list[str] = []

    try:
        page = request.data_access.dataframe_page(ref, page=1, page_size=page_size)
        columns = list(page.columns)
        rows = list(page.rows)
        total = int(getattr(page, "total_rows", len(rows)) or len(rows))
        truncated = bool(getattr(page, "truncated", total > len(rows)))
        x_name = _LAMBDA if _LAMBDA in columns else (columns[0] if columns else None)
        y_name = _INTENSITY if _INTENSITY in columns else (columns[1] if len(columns) > 1 else None)
        for row in rows:
            if x_name is None or y_name is None or not isinstance(row, dict):
                continue
            x_val = _finite_float(row.get(x_name))
            y_val = _finite_float(row.get(y_name))
            if x_val is not None and y_val is not None:
                points.append({"x": x_val, "y": y_val})
            else:
                nonnumeric += 1
    except Exception as exc:
        # Fallback: the cheaper single-column series read so a Spectrum without
        # a readable second column still previews as an indexed line. When the
        # fallback also recovers nothing the payload is genuinely unreadable, so
        # return a typed error envelope rather than a misleading empty plot.
        logger.debug("spectrum dataframe_page failed for %s", ref.path, exc_info=True)
        try:
            series = request.data_access.series_points(ref, record_md)
        except Exception as inner:
            logger.debug("spectrum series fallback failed for %s", ref.path, exc_info=True)
            return _error_envelope(request, f"spectrum preview failed: {exc}; fallback: {inner}")
        if not series.points:
            return _error_envelope(request, f"spectrum preview failed: {exc}")
        points = [{"x": float(p["x"]), "y": float(p["y"])} for p in series.points]
        total = int(series.total)
        truncated = bool(series.truncated)
        diagnostics.append("read both-column table failed; showing decimated single column")

    # Honest diagnostics (FR-019 unit display, US1 acceptance #3; FR-020 sampling).
    if lambda_unit is None or intensity_unit is None:
        missing = [
            name for name, val in (("lambda_unit", lambda_unit), ("intensity_unit", intensity_unit)) if val is None
        ]
        diagnostics.append(f"missing unit metadata: {', '.join(missing)}")
    if not points:
        diagnostics.append("empty data: no numeric (lambda, intensity) points to plot")
    if nonnumeric:
        diagnostics.append(f"skipped {nonnumeric} nonnumeric row(s)")
    if truncated:
        diagnostics.append(f"showing {len(points)} sampled point(s) of {total} (bounded read)")

    table_rows = [{_LAMBDA: p["x"], _INTENSITY: p["y"]} for p in points]
    x_label = f"{lambda_kind or _LAMBDA}" + (f" ({lambda_unit})" if lambda_unit else "")
    y_label = _INTENSITY + (f" ({intensity_unit})" if intensity_unit else "")

    resources = (
        *(
            PreviewResource(
                resource_id=f"export_figure_{fmt}",
                kind="asset",
                media_type=_FIGURE_MEDIA[fmt],
                description=f"export the displayed spectrum figure as {fmt.upper()}",
                params={"format": fmt, "target": "figure"},
            )
            for fmt in _FIGURE_FORMATS
        ),
        PreviewResource(
            resource_id="export_points_csv",
            kind="asset",
            media_type="text/csv",
            description="export the visible (decimated) spectrum points as CSV",
            params={"format": "csv", "target": "visible_points"},
        ),
    )

    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.SERIES,
        payload={
            "points": points,
            "table": {"columns": [_LAMBDA, _INTENSITY], "rows": table_rows},
            "total": total,
            "axes": {
                "x": {"name": _LAMBDA, "kind": lambda_kind, "unit": lambda_unit, "label": x_label},
                "y": {"name": _INTENSITY, "unit": intensity_unit, "label": y_label},
            },
            "modality": modality,
            "capabilities": list(_SPECTRUM_CAPABILITIES),
            "interactions": ["zoom", "pan", "box_zoom", "reset", "hover"],
        },
        resources=resources,
        diagnostics=tuple(diagnostics),
        metadata=PreviewMetadata(
            sampled=truncated,
            truncated=truncated,
            complete=not truncated and bool(points),
            extra={
                "total": total,
                "shown": len(points),
                "nonnumeric_rows": nonnumeric,
                "lambda_unit": lambda_unit,
                "intensity_unit": intensity_unit,
                "diagnostics": list(diagnostics),
            },
        ),
    )


# ---------------------------------------------------------------------------
# SpectralDataset diagnostics (pure helper — unit-testable in isolation, FR-027)
# ---------------------------------------------------------------------------


def compute_dataset_diagnostics(
    index_rows: list[dict[str, Any]],
    spectra_rows: list[dict[str, Any]],
    *,
    index_columns: list[str] | None = None,
    spectra_columns: list[str] | None = None,
    index_truncated: bool = False,
    spectra_truncated: bool = False,
) -> dict[str, Any]:
    """Compute SpectralDataset health diagnostics (FR-027) from bounded rows.

    Pure function over the already-read (bounded) ``index`` and ``spectra``
    rows. Performs NO scientific processing (FR-030) — only integrity checks:

    - duplicate ``spectrum_id`` in the index,
    - orphan spectra rows (id present in ``spectra`` but not in ``index``),
    - missing spectra coverage (index id with no ``spectra`` rows),
    - missing numeric coordinates / intensities in ``spectra``,
    - unit inconsistency (multiple distinct ``lambda_unit`` / ``intensity_unit``
      values across the index),
    - heatmap-alignment (non-aligned per-spectrum lambda grids).

    Returns a JSON-safe dict. When the inputs were truncated the issue lists are
    marked ``partial`` so the UI can report that the scan was bounded.
    """
    index_cols = index_columns if index_columns is not None else _columns_of(index_rows)
    spectra_cols = spectra_columns if spectra_columns is not None else _columns_of(spectra_rows)

    issues: list[dict[str, Any]] = []

    # --- schema: required columns ----------------------------------------
    missing_index_cols = [c for c in (_SPECTRUM_ID,) if c not in index_cols]
    missing_spectra_cols = [c for c in (_SPECTRUM_ID, _LAMBDA, _INTENSITY) if c not in spectra_cols]
    if missing_index_cols:
        issues.append({"code": "missing_required_columns", "slot": "index", "columns": missing_index_cols})
    if missing_spectra_cols:
        issues.append({"code": "missing_required_columns", "slot": "spectra", "columns": missing_spectra_cols})

    # --- index ids: duplicates -------------------------------------------
    index_ids: list[Any] = [r.get(_SPECTRUM_ID) for r in index_rows if isinstance(r, dict)]
    seen: set[Any] = set()
    duplicates: list[str] = []
    for sid in index_ids:
        if sid is None:
            continue
        if sid in seen and str(sid) not in duplicates:
            duplicates.append(str(sid))
        seen.add(sid)
    if duplicates:
        issues.append({"code": "duplicate_ids", "slot": "index", "ids": duplicates})
    index_id_set = {sid for sid in index_ids if sid is not None}

    # --- spectra rows: per-id presence + numeric checks ------------------
    spectra_id_set: set[Any] = set()
    nonnumeric_lambda = 0
    nonnumeric_intensity = 0
    grids: dict[Any, list[float]] = {}
    for row in spectra_rows:
        if not isinstance(row, dict):
            continue
        sid = row.get(_SPECTRUM_ID)
        if sid is not None:
            spectra_id_set.add(sid)
        lam = _finite_float(row.get(_LAMBDA))
        inten = _finite_float(row.get(_INTENSITY))
        if lam is None:
            nonnumeric_lambda += 1
        else:
            grids.setdefault(sid, []).append(lam)
        if inten is None:
            nonnumeric_intensity += 1

    orphans = sorted(str(sid) for sid in (spectra_id_set - index_id_set))
    missing_coverage = sorted(str(sid) for sid in (index_id_set - spectra_id_set))
    if orphans:
        issues.append({"code": "orphan_spectra", "slot": "spectra", "ids": orphans})
    if missing_coverage:
        issues.append({"code": "missing_spectra_coverage", "slot": "index", "ids": missing_coverage})
    if nonnumeric_lambda:
        issues.append({"code": "nonnumeric_coordinates", "slot": "spectra", "count": nonnumeric_lambda})
    if nonnumeric_intensity:
        issues.append({"code": "nonnumeric_intensities", "slot": "spectra", "count": nonnumeric_intensity})

    # --- unit inconsistency (index columns) ------------------------------
    for unit_col in ("lambda_unit", "intensity_unit"):
        values = {str(r.get(unit_col)) for r in index_rows if isinstance(r, dict) and r.get(unit_col) not in (None, "")}
        if len(values) > 1:
            issues.append({"code": "unit_inconsistency", "column": unit_col, "values": sorted(values)})

    # --- heatmap alignment: do per-spectrum lambda grids match? ----------
    grid_signatures = {_grid_signature(g) for g in grids.values() if g}
    aligned = len(grid_signatures) <= 1
    if not aligned:
        issues.append(
            {
                "code": "heatmap_alignment",
                "detail": "spectra do not share a common lambda grid; heatmap requires resampling",
                "distinct_grids": len(grid_signatures),
            }
        )

    return {
        "issues": issues,
        "ok": not issues,
        "partial": bool(index_truncated or spectra_truncated),
        "counts": {
            "index_rows": len(index_rows),
            "spectra_rows": len(spectra_rows),
            "unique_index_ids": len(index_id_set),
            "unique_spectra_ids": len(spectra_id_set),
            "duplicate_ids": len(duplicates),
            "orphan_spectra": len(orphans),
            "missing_coverage": len(missing_coverage),
        },
        "heatmap_aligned": aligned,
    }


def _columns_of(rows: list[dict[str, Any]]) -> list[str]:
    cols: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            for key in row:
                if key not in cols:
                    cols.append(key)
    return cols


def _grid_signature(grid: list[float]) -> tuple[int, float, float]:
    """A cheap, order-insensitive signature of a lambda grid (length + bounds)."""
    if not grid:
        return (0, 0.0, 0.0)
    return (len(grid), round(min(grid), 6), round(max(grid), 6))


# ---------------------------------------------------------------------------
# SpectralDataset provider (kind=COMPOSITE -> degrades to core.composite.basic)
# ---------------------------------------------------------------------------


def _slot_ref(parent: StorageReference, record_md: dict[str, Any], slot: str) -> StorageReference | None:
    """Resolve a bounded read ref for a dataset slot.

    Prefers an explicit path the worker recorded (``slot_paths[slot]`` or
    ``<slot>_path``); otherwise derives the conventional ``<parent>/<slot>``
    subpath (mirrors imaging ``composite_raster_slot``). Returns ``None`` when no
    readable candidate exists so the provider degrades gracefully.
    """
    slot_paths = record_md.get("slot_paths")
    candidate: str | None = None
    if isinstance(slot_paths, dict) and isinstance(slot_paths.get(slot), str):
        candidate = slot_paths[slot]
    elif isinstance(record_md.get(f"{slot}_path"), str):
        candidate = record_md[f"{slot}_path"]
    else:
        base = Path(parent.path)
        for name in (slot, f"{slot}.parquet", f"{slot}.csv"):
            probe = base / name
            if probe.exists():
                candidate = str(probe)
                break
        if candidate is None and base.suffix.lower() in {".parquet", ".csv"}:
            # Single-file dataset payloads are not slot-separable for a bounded
            # read; let the caller fall back to slot-inventory-only.
            return None
    if candidate is None:
        return None
    return StorageReference(backend=parent.backend, path=candidate, format=parent.format)


def _read_slot_page(
    request: PreviewRequest,
    ref: StorageReference | None,
    *,
    page: int = 1,
    page_size: int = 256,
    sort_by: str | None = None,
    sort_dir: str = "asc",
) -> tuple[list[str], list[dict[str, Any]], int, bool] | None:
    """Bounded read of one slot page; ``None`` on failure (never raises)."""
    if ref is None:
        return None
    try:
        page_obj = request.data_access.dataframe_page(
            ref, page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir
        )
    except Exception:
        logger.debug("dataset slot read failed for %s", ref.path, exc_info=True)
        return None
    rows = [r for r in page_obj.rows if isinstance(r, dict)]
    total = int(getattr(page_obj, "total_rows", len(rows)) or len(rows))
    truncated = bool(getattr(page_obj, "truncated", total > len(rows)))
    return list(page_obj.columns), rows, total, truncated


def spectral_dataset_provider(request: PreviewRequest) -> PreviewEnvelope:
    """Preview a ``SpectralDataset`` as a metadata-aware spectral explorer.

    Surfaces the slot inventory, a paginated ``index`` table (FR-023), the
    explorer capabilities + plot modes (FR-024/FR-025), and dataset health
    diagnostics (FR-027) computed from bounded reads of both slots (FR-028). The
    envelope kind is ``COMPOSITE`` so it degrades to the core composite renderer.
    """
    record_md = _record_metadata(request)
    try:
        slots = request.data_access.composite_slots(record_md)
    except Exception as exc:
        logger.debug("spectral dataset composite_slots failed", exc_info=True)
        return _error_envelope(request, f"spectral dataset preview failed: {exc}")

    slot_map = dict(slots.slots)
    parent = _ref_for(request)
    page = _page_from_query(request)
    page_size = _page_size(request)
    sort_by, sort_dir = _sort_from_query(request)
    diagnostics: list[str] = []
    truncated = False

    # --- paginated index table (FR-023) ----------------------------------
    index_ref = _slot_ref(parent, record_md, "index")
    index_read = _read_slot_page(request, index_ref, page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir)
    index_payload: dict[str, Any] = {
        "columns": [],
        "rows": [],
        "total_rows": 0,
        "page": page,
        "page_size": page_size,
        "available": index_read is not None,
    }
    index_rows: list[dict[str, Any]] = []
    index_columns: list[str] = []
    index_truncated = False
    if index_read is not None:
        index_columns, index_rows, index_total, index_truncated = index_read
        index_payload.update(
            columns=index_columns,
            rows=index_rows,
            total_rows=index_total,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        truncated = truncated or index_truncated
    else:
        diagnostics.append("index slot not readable as a bounded table; showing slot inventory only")

    # --- bounded spectra read for diagnostics (FR-027/FR-028) ------------
    spectra_ref = _slot_ref(parent, record_md, "spectra")
    spectra_read = _read_slot_page(request, spectra_ref, page=1, page_size=page_size)
    spectra_rows: list[dict[str, Any]] = []
    spectra_columns: list[str] = []
    spectra_truncated = False
    if spectra_read is not None:
        spectra_columns, spectra_rows, _spectra_total, spectra_truncated = spectra_read
        truncated = truncated or spectra_truncated
    else:
        diagnostics.append("spectra slot not readable for a bounded diagnostics scan")

    dataset_diagnostics = compute_dataset_diagnostics(
        index_rows,
        spectra_rows,
        index_columns=index_columns or None,
        spectra_columns=spectra_columns or None,
        index_truncated=index_truncated,
        spectra_truncated=spectra_truncated,
    )
    for issue in dataset_diagnostics["issues"]:
        diagnostics.append(f"{issue['code']}: {issue}")

    resources = _dataset_resources(slot_map)

    payload = {
        "slots": slot_map,
        "index_table": index_payload,
        "capabilities": list(_DATASET_CAPABILITIES),
        "plot_modes": list(_PLOT_MODES),
        "diagnostics": dataset_diagnostics,
        "dataset_metadata": _dataset_metadata_panel(record_md),
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
            extra={
                "slot_count": len(slot_map),
                "capabilities": list(_DATASET_CAPABILITIES),
                "plot_modes": list(_PLOT_MODES),
                "diagnostics": dataset_diagnostics,
            },
        ),
    )


def _dataset_resources(slot_map: dict[str, str]) -> tuple[PreviewResource, ...]:
    """Child-slot routing + figure/rows/group export actions (FR-029)."""
    child = tuple(
        PreviewResource(
            resource_id=f"slot:{name}",
            kind="child",
            description=f"child preview for slot '{name}' ({type_name})",
            params={"slot": name, "slot_type": type_name},
        )
        for name, type_name in slot_map.items()
    )
    figure = tuple(
        PreviewResource(
            resource_id=f"export_figure_{fmt}",
            kind="asset",
            media_type=_FIGURE_MEDIA[fmt],
            description=f"export the current dataset figure as {fmt.upper()}",
            params={"format": fmt, "target": "figure"},
        )
        for fmt in _FIGURE_FORMATS
    )
    tables = (
        PreviewResource(
            resource_id="export_visible_spectra_csv",
            kind="asset",
            media_type="text/csv",
            description="export the visible spectra rows as CSV",
            params={"format": "csv", "target": "visible_spectra"},
        ),
        PreviewResource(
            resource_id="export_selected_rows_csv",
            kind="asset",
            media_type="text/csv",
            description="export the selected index rows as CSV",
            params={"format": "csv", "target": "selected_rows"},
        ),
        PreviewResource(
            resource_id="export_grouped_summary_csv",
            kind="asset",
            media_type="text/csv",
            description="export the grouped summary table as CSV",
            params={"format": "csv", "target": "grouped_summary"},
        ),
    )
    return child + figure + tables


def _dataset_metadata_panel(record_md: dict[str, Any]) -> dict[str, Any]:
    """Bounded, JSON-safe dataset-level metadata panel for the explorer."""
    panel: dict[str, Any] = {}
    for key in (
        "dataset_name",
        "dataset_role",
        "lambda_unit",
        "intensity_unit",
        "modality",
        "schema_version",
    ):
        value = record_md.get(key)
        if isinstance(value, (str, int, float)):
            panel[key] = value
    return panel


def _page_from_query(request: PreviewRequest) -> int:
    raw = request.query.get("page")
    try:
        return max(1, int(raw)) if raw is not None else 1
    except (TypeError, ValueError):
        return 1


def _sort_from_query(request: PreviewRequest) -> tuple[str | None, str]:
    sort_by = request.query.get("sort_by")
    sort_dir = request.query.get("sort_dir")
    by = sort_by if isinstance(sort_by, str) and sort_by else None
    direction = sort_dir if sort_dir in {"asc", "desc"} else "asc"
    return by, direction


__all__ = [
    "compute_dataset_diagnostics",
    "spectral_dataset_provider",
    "spectrum_provider",
]
