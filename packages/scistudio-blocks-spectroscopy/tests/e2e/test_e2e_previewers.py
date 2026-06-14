"""End-to-end preview tests: produce -> persist -> preview (US1..US4, FR-018..FR-030).

Builds real ``Spectrum`` / ``SpectralDataset`` payloads from the pseudo-spectra
generators, persists their two-column / two-slot tables to parquet, and drives
the two package providers against a real bounded ``PreviewDataAccess`` to verify
the preview envelope reflects the generated data (true (x,y) points, index
table, capabilities, plot modes, and FR-027 health diagnostics including the
non-aligned-grid heatmap warning).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import fixtures as fx
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from scistudio_blocks_spectroscopy import _support
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
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

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


def _spec_for(previewer_id: str) -> PreviewerSpec:
    return cast(PreviewerSpec, {s.previewer_id: s for s in get_previewers()}[previewer_id])


def _request(
    previewer_id: str, chain: tuple[str, ...], *, storage: dict, record_md: dict | None = None
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
        spec=_spec_for(previewer_id),
        query=query,
        data_access=PreviewDataAccess(),
        limits=PreviewLimits(),
        session_id=None,
    )


def _persist_spectrum(spectrum: Spectrum, path: Path) -> Path:
    lam, inten = _support.spectrum_arrays(spectrum)
    pq.write_table(pa.table({"lambda": lam, "intensity": inten}), path)
    return path


def _persist_dataset(dataset: SpectralDataset, root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    index_tbl, spectra_tbl = _support.dataset_frames(dataset)
    pq.write_table(index_tbl, root / "index.parquet")
    pq.write_table(spectra_tbl, root / "spectra.parquet")
    return root


# ---------------------------------------------------------------------------
# Spectrum previewer (US1)
# ---------------------------------------------------------------------------


def test_generated_spectrum_previews_as_xy_series(tmp_path: Path) -> None:
    spec, _ = fx.make_peak_spectrum(spectrum_id="prev1", peaks=(fx.PeakSpec("gaussian", 5.0, 500.0, 8.0),))
    path = _persist_spectrum(spec, tmp_path / "spectrum.parquet")
    env = spectrum_provider(
        _request(
            SPECTRUM_PREVIEWER_ID,
            _SPECTRUM_CHAIN,
            storage={"backend": "filesystem", "path": str(path), "format": "parquet"},
            record_md={"lambda_unit": "nm", "intensity_unit": "au", "lambda_kind": "wavelength"},
        )
    )
    assert env.kind is EnvelopeKind.SERIES
    assert env.error is None
    points = env.payload["points"]
    assert len(points) > 0
    # The previewed peak maximum lands at the true center (500 nm).
    peak_point = max(points, key=lambda p: p["y"])
    assert abs(peak_point["x"] - 500.0) < 1.0
    assert env.payload["axes"]["x"]["unit"] == "nm"
    res_ids = {r.resource_id for r in env.resources}
    assert {"export_figure_svg", "export_points_csv"} <= res_ids


def test_generated_spectrum_missing_units_diagnostic(tmp_path: Path) -> None:
    spec, _ = fx.make_peak_spectrum(spectrum_id="prev2")
    path = _persist_spectrum(spec, tmp_path / "nounits.parquet")
    env = spectrum_provider(
        _request(
            SPECTRUM_PREVIEWER_ID,
            _SPECTRUM_CHAIN,
            storage={"backend": "filesystem", "path": str(path), "format": "parquet"},
            record_md={},
        )
    )
    assert env.kind is EnvelopeKind.SERIES
    assert env.payload["points"]  # still renders
    assert any("missing unit metadata" in d for d in env.diagnostics)


# ---------------------------------------------------------------------------
# SpectralDataset previewer (US2/US3)
# ---------------------------------------------------------------------------


def test_generated_library_dataset_previews_with_index_and_capabilities(tmp_path: Path) -> None:
    # Small grid so the whole spectra slot fits in one bounded preview page and
    # the health scan is complete (not a partial bounded read).
    small_grid = np.linspace(400.0, 420.0, 21)
    dataset, truth = fx.make_library_dataset(grid=small_grid)
    root = _persist_dataset(dataset, tmp_path / "lib")
    env = spectral_dataset_provider(
        _request(
            SPECTRAL_DATASET_PREVIEWER_ID,
            _DATASET_CHAIN,
            storage={"backend": "filesystem", "path": str(root), "format": "parquet"},
            record_md={
                "slots": {"index": "DataFrame", "spectra": "DataFrame"},
                "dataset_role": "library",
            },
        )
    )
    assert env.kind is EnvelopeKind.COMPOSITE
    assert env.error is None
    # Index table reflects the generated library entries + metadata columns (US3).
    assert env.payload["index_table"]["available"] is True
    assert "spectrum_id" in env.payload["index_table"]["columns"]
    assert "citation" in env.payload["index_table"]["columns"]
    assert env.payload["index_table"]["total_rows"] == len(truth)
    # Explorer capabilities + plot modes exposed (FR-024/FR-025).
    assert "plot" in env.payload["capabilities"]
    assert "heatmap" in env.payload["plot_modes"]
    # Library is well-formed -> diagnostics clean.
    assert env.payload["diagnostics"]["ok"] is True


def test_large_dataset_preview_reports_partial_bounded_scan(tmp_path: Path) -> None:
    # A dataset whose spectra slot exceeds the bounded preview page (401 pts x 3
    # spectra) is scanned only partially; the previewer reports that honestly via
    # diagnostics.partial rather than claiming a complete clean dataset (FR-028).
    dataset, _ = fx.make_library_dataset()  # 401-point grid -> 1203 spectra rows
    root = _persist_dataset(dataset, tmp_path / "big")
    env = spectral_dataset_provider(
        _request(
            SPECTRAL_DATASET_PREVIEWER_ID,
            _DATASET_CHAIN,
            storage={"backend": "filesystem", "path": str(root), "format": "parquet"},
            record_md={"slots": {"index": "DataFrame", "spectra": "DataFrame"}},
        )
    )
    assert env.kind is EnvelopeKind.COMPOSITE
    assert env.payload["diagnostics"]["partial"] is True
    # The index table is still complete (small) even when the spectra scan is bounded.
    assert env.payload["index_table"]["total_rows"] == 3


def test_dataset_built_from_collection_previews_clean(tmp_path: Path) -> None:
    from scistudio_blocks_spectroscopy.blocks.utilities import SpectrumToSpectralDataset

    from scistudio.blocks.base.config import BlockConfig

    # Small grid -> the whole spectra slot fits in one bounded page (clean scan).
    specs, _ = fx.make_collection(n=3, grid=np.linspace(400.0, 420.0, 21))
    out = SpectrumToSpectralDataset().run({"spectra": _support.spectra_collection(specs)}, BlockConfig(params={}))
    dataset = next(iter(out["dataset"]))
    root = _persist_dataset(dataset, tmp_path / "ds")
    env = spectral_dataset_provider(
        _request(
            SPECTRAL_DATASET_PREVIEWER_ID,
            _DATASET_CHAIN,
            storage={"backend": "filesystem", "path": str(root), "format": "parquet"},
            record_md={"slots": {"index": "DataFrame", "spectra": "DataFrame"}},
        )
    )
    assert env.kind is EnvelopeKind.COMPOSITE
    assert env.payload["diagnostics"]["ok"] is True


# ---------------------------------------------------------------------------
# Non-aligned grid heatmap warning (FR-027 / US2 acceptance #4)
# ---------------------------------------------------------------------------


def test_non_aligned_grids_flag_heatmap(tmp_path: Path) -> None:
    # Two spectra on different-length lambda grids -> heatmap requires resampling.
    a, _ = fx.make_peak_spectrum(spectrum_id="a", grid=np.linspace(400, 600, 201))
    b, _ = fx.make_peak_spectrum(spectrum_id="b", grid=np.linspace(400, 600, 401))
    spectra_rows = []
    index_rows = []
    for sid, spec in (("a", a), ("b", b)):
        lam, inten = _support.spectrum_arrays(spec)
        index_rows.append({"spectrum_id": sid})
        for x, y in zip(lam.tolist(), inten.tolist(), strict=True):
            spectra_rows.append({"spectrum_id": sid, "lambda": x, "intensity": y})
    diag = compute_dataset_diagnostics(index_rows, spectra_rows)
    codes = {i["code"] for i in diag["issues"]}
    assert "heatmap_alignment" in codes
    assert diag["heatmap_aligned"] is False


def test_aligned_grids_no_heatmap_warning() -> None:
    specs, _ = fx.make_collection(n=3)  # all on DEFAULT_GRID
    index_rows = []
    spectra_rows = []
    for spec in specs:
        lam, inten = _support.spectrum_arrays(spec)
        index_rows.append({"spectrum_id": spec.spectrum_id})
        for x, y in zip(lam.tolist(), inten.tolist(), strict=True):
            spectra_rows.append({"spectrum_id": spec.spectrum_id, "lambda": x, "intensity": y})
    diag = compute_dataset_diagnostics(index_rows, spectra_rows)
    assert diag["heatmap_aligned"] is True
    assert "heatmap_alignment" not in {i["code"] for i in diag["issues"]}
