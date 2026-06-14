"""Provider-behavior smoke tests for the spectroscopy previewers (ADR-048).

These exercise the two package providers against a *real* bounded
``PreviewDataAccess`` reading real on-disk parquet payloads, plus the pure
diagnostics helper in isolation. They assert envelope kind, payload shape,
export resources, honest sampling/diagnostic metadata, the error-envelope path,
and FR-027 dataset health detection (duplicate / orphan / missing coverage /
unit inconsistency / misaligned heatmap grids).

Registration shape (``get_previewers`` returns 2 PACKAGE specs) is covered by
``test_previewer_registration.py``; this file covers provider execution.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from scistudio_blocks_spectroscopy.previewers import (
    SPECTRAL_DATASET_PREVIEWER_ID,
    SPECTRUM_PREVIEWER_ID,
    get_previewers,
)
from scistudio_blocks_spectroscopy.previewers.providers import (
    compute_dataset_diagnostics,
    spectral_dataset_provider,
    spectrum_provider,
)

from scistudio.previewers.data_access import PreviewDataAccess
from scistudio.previewers.models import (
    EnvelopeKind,
    PreviewerSpec,
    PreviewLimits,
    PreviewRequest,
    PreviewTarget,
    TargetKind,
)

_SPECTRUM_CHAIN = ("DataObject", "Series", "Spectrum")
_DATASET_CHAIN = ("DataObject", "CompositeData", "SpectralDataset")


def _spec(previewer_id: str) -> PreviewerSpec:
    return {s.previewer_id: s for s in get_previewers()}[previewer_id]


def _request(
    previewer_id: str,
    chain: tuple[str, ...],
    *,
    storage: dict,
    record_md: dict | None = None,
) -> PreviewRequest:
    query: dict = {"_storage": storage}
    if record_md is not None:
        query["_record_metadata"] = record_md
    return PreviewRequest(
        target=PreviewTarget(
            kind=TargetKind.DATA_REF,
            ref=storage.get("path", "r"),
            recorded_type=chain[-1],
            type_chain=chain,
        ),
        spec=_spec(previewer_id),
        query=query,
        data_access=PreviewDataAccess(),
        limits=PreviewLimits(),
        session_id=None,
    )


def _write_parquet(path: Path, columns: dict) -> Path:
    pq.write_table(pa.table(columns), path)
    return path


# ---------------------------------------------------------------------------
# Spectrum provider
# ---------------------------------------------------------------------------


def test_spectrum_provider_builds_series_envelope_with_xy_points(tmp_path: Path) -> None:
    path = _write_parquet(
        tmp_path / "spectrum.parquet",
        {"lambda": [400.0, 401.0, 402.0, 403.0], "intensity": [0.1, 0.5, 0.3, 0.9]},
    )
    request = _request(
        SPECTRUM_PREVIEWER_ID,
        _SPECTRUM_CHAIN,
        storage={"backend": "filesystem", "path": str(path), "format": "parquet"},
        record_md={"lambda_unit": "nm", "intensity_unit": "a.u.", "lambda_kind": "wavelength"},
    )

    env = spectrum_provider(request)

    assert env.previewer_id == SPECTRUM_PREVIEWER_ID
    assert env.kind is EnvelopeKind.SERIES
    assert env.error is None
    # Both columns are read -> true (x, y) points, not first-column-only.
    assert env.payload["points"] == [
        {"x": 400.0, "y": 0.1},
        {"x": 401.0, "y": 0.5},
        {"x": 402.0, "y": 0.3},
        {"x": 403.0, "y": 0.9},
    ]
    assert env.payload["table"]["columns"] == ["lambda", "intensity"]
    assert env.payload["total"] == 4
    # FR-019 unit display: axis labels carry the units.
    assert env.payload["axes"]["x"]["unit"] == "nm"
    assert env.payload["axes"]["y"]["label"] == "intensity (a.u.)"
    # All six metadata flags present + bool; honest complete flag.
    md = env.metadata.to_dict()
    for flag in ("sampled", "truncated", "cached", "derived", "complete", "failed"):
        assert flag in md and isinstance(md[flag], bool)
    assert env.metadata.complete is True
    # FR-021 export resources: figure (svg/png/pdf) + visible-points CSV.
    res_ids = {r.resource_id for r in env.resources}
    assert {"export_figure_svg", "export_figure_png", "export_figure_pdf", "export_points_csv"} <= res_ids


def test_spectrum_provider_reports_missing_unit_diagnostic(tmp_path: Path) -> None:
    """US1 acceptance #3: missing units still render but emit a diagnostic."""
    path = _write_parquet(
        tmp_path / "nounits.parquet",
        {"lambda": [1.0, 2.0], "intensity": [10.0, 20.0]},
    )
    request = _request(
        SPECTRUM_PREVIEWER_ID,
        _SPECTRUM_CHAIN,
        storage={"backend": "filesystem", "path": str(path), "format": "parquet"},
        record_md={},
    )
    env = spectrum_provider(request)
    assert env.kind is EnvelopeKind.SERIES
    assert env.payload["points"]  # still renders
    assert any("missing unit metadata" in d for d in env.diagnostics)


def test_spectrum_provider_error_envelope_on_bad_input() -> None:
    request = _request(
        SPECTRUM_PREVIEWER_ID,
        _SPECTRUM_CHAIN,
        storage={"backend": "filesystem", "path": "/does/not/exist.parquet", "format": "parquet"},
        record_md={},
    )
    env = spectrum_provider(request)
    assert env.kind is EnvelopeKind.ERROR
    assert env.metadata.failed is True
    assert env.metadata.complete is False
    assert "frontend_manifest" not in env.metadata.extra
    assert env.frontend_manifest is None


# ---------------------------------------------------------------------------
# SpectralDataset provider
# ---------------------------------------------------------------------------


def _dataset_dir(tmp_path: Path, index_cols: dict, spectra_cols: dict) -> Path:
    root = tmp_path / "dataset"
    root.mkdir()
    _write_parquet(root / "index.parquet", index_cols)
    _write_parquet(root / "spectra.parquet", spectra_cols)
    return root


def test_spectral_dataset_provider_builds_composite_envelope(tmp_path: Path) -> None:
    root = _dataset_dir(
        tmp_path,
        index_cols={"spectrum_id": ["a", "b"], "label": ["x", "y"]},
        spectra_cols={
            "spectrum_id": ["a", "a", "b", "b"],
            "lambda": [1.0, 2.0, 1.0, 2.0],
            "intensity": [10.0, 11.0, 20.0, 21.0],
        },
    )
    request = _request(
        SPECTRAL_DATASET_PREVIEWER_ID,
        _DATASET_CHAIN,
        storage={"backend": "filesystem", "path": str(root), "format": "parquet"},
        record_md={"slots": {"index": "DataFrame", "spectra": "DataFrame"}, "dataset_name": "demo"},
    )
    env = spectral_dataset_provider(request)

    assert env.previewer_id == SPECTRAL_DATASET_PREVIEWER_ID
    assert env.kind is EnvelopeKind.COMPOSITE
    assert env.error is None
    # Slot inventory + paginated index table (FR-023).
    assert env.payload["slots"] == {"index": "DataFrame", "spectra": "DataFrame"}
    assert env.payload["index_table"]["available"] is True
    assert env.payload["index_table"]["columns"] == ["spectrum_id", "label"]
    assert env.payload["index_table"]["total_rows"] == 2
    # Capabilities + plot modes exposed (FR-024/FR-025).
    assert env.payload["capabilities"] == ["table", "filter", "group", "plot", "diagnostics", "export"]
    assert env.payload["plot_modes"] == ["overlay", "selected", "group_mean", "group_band", "heatmap"]
    # Healthy dataset -> diagnostics present and ok.
    assert env.payload["diagnostics"]["ok"] is True
    # Child slot resources + figure/rows/group export (FR-029).
    res_ids = {r.resource_id for r in env.resources}
    assert {"slot:index", "slot:spectra"} <= res_ids
    assert {"export_figure_svg", "export_selected_rows_csv", "export_grouped_summary_csv"} <= res_ids


def test_spectral_dataset_provider_detects_health_issues(tmp_path: Path) -> None:
    """Deliberate duplicate id, orphan, and missing-coverage rows (FR-027)."""
    root = _dataset_dir(
        tmp_path,
        # 'a' duplicated; 'c' present in index but has no spectra rows.
        index_cols={"spectrum_id": ["a", "a", "c"]},
        spectra_cols={
            # 'z' is an orphan (not in index); 'c' has no rows -> missing coverage.
            "spectrum_id": ["a", "z"],
            "lambda": [1.0, 1.0],
            "intensity": [5.0, 6.0],
        },
    )
    request = _request(
        SPECTRAL_DATASET_PREVIEWER_ID,
        _DATASET_CHAIN,
        storage={"backend": "filesystem", "path": str(root), "format": "parquet"},
        record_md={"slots": {"index": "DataFrame", "spectra": "DataFrame"}},
    )
    env = spectral_dataset_provider(request)
    codes = {issue["code"] for issue in env.payload["diagnostics"]["issues"]}
    assert "duplicate_ids" in codes
    assert "orphan_spectra" in codes
    assert "missing_spectra_coverage" in codes


def test_spectral_dataset_provider_degrades_to_slot_inventory(tmp_path: Path) -> None:
    """No readable slot files -> still a valid COMPOSITE envelope (inventory)."""
    request = _request(
        SPECTRAL_DATASET_PREVIEWER_ID,
        _DATASET_CHAIN,
        storage={"backend": "filesystem", "path": str(tmp_path / "empty"), "format": "zarr"},
        record_md={"slots": {"index": "DataFrame", "spectra": "DataFrame"}},
    )
    env = spectral_dataset_provider(request)
    assert env.kind is EnvelopeKind.COMPOSITE
    assert env.payload["slots"] == {"index": "DataFrame", "spectra": "DataFrame"}
    assert env.payload["index_table"]["available"] is False


# ---------------------------------------------------------------------------
# Pure diagnostics helper (FR-027) — unit-testable in isolation
# ---------------------------------------------------------------------------


def test_compute_dataset_diagnostics_clean() -> None:
    diag = compute_dataset_diagnostics(
        index_rows=[{"spectrum_id": "a"}, {"spectrum_id": "b"}],
        spectra_rows=[
            {"spectrum_id": "a", "lambda": 1.0, "intensity": 2.0},
            {"spectrum_id": "b", "lambda": 1.0, "intensity": 3.0},
        ],
    )
    assert diag["ok"] is True
    assert diag["issues"] == []
    assert diag["heatmap_aligned"] is True


def test_compute_dataset_diagnostics_flags_unit_and_alignment() -> None:
    diag = compute_dataset_diagnostics(
        index_rows=[
            {"spectrum_id": "a", "lambda_unit": "nm"},
            {"spectrum_id": "b", "lambda_unit": "cm-1"},
        ],
        spectra_rows=[
            {"spectrum_id": "a", "lambda": 1.0, "intensity": 2.0},
            {"spectrum_id": "a", "lambda": 2.0, "intensity": 2.5},
            {"spectrum_id": "b", "lambda": 1.0, "intensity": 3.0},  # shorter grid
        ],
    )
    codes = {i["code"] for i in diag["issues"]}
    assert "unit_inconsistency" in codes
    assert "heatmap_alignment" in codes
    assert diag["heatmap_aligned"] is False


def test_compute_dataset_diagnostics_flags_nonnumeric_and_missing_columns() -> None:
    diag = compute_dataset_diagnostics(
        index_rows=[{"label": "x"}],  # no spectrum_id column
        spectra_rows=[{"spectrum_id": "a", "lambda": "bad", "intensity": None}],
    )
    codes = {i["code"] for i in diag["issues"]}
    assert "missing_required_columns" in codes
    assert "nonnumeric_coordinates" in codes
    assert "nonnumeric_intensities" in codes
