"""End-to-end multi-block pipelines (whole-workflow assertions, #1661).

Each test wires several real blocks into a pipeline and asserts the end-to-end
result against analytic ground truth:

- preprocessing chain: Load -> Crop -> Baseline -> Smooth -> Normalize ->
  ExtractIntensity -> AttachFeaturesToSpectralDataset;
- dataset round-trip: SpectrumToSpectralDataset -> FilterSpectralDataset ->
  SpectralDatasetToSpectrum (id/metadata round-trip);
- unmixing: build references -> SpectralUnmixing (recovered coefficients);
- library: build library -> MatchSpectralLibrary (correct top-1);
- fitting: FitPeak -> residual == input - fit_curve and FWHM/area vs analytic.
"""

from __future__ import annotations

from pathlib import Path

import fixtures as fx
import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks.feature_extraction import ExtractIntensity
from scistudio_blocks_spectroscopy.blocks.library_matching import MatchSpectralLibrary
from scistudio_blocks_spectroscopy.blocks.peak_fitting import FitPeak
from scistudio_blocks_spectroscopy.blocks.preprocessing import (
    BaselineCorrection,
    CropSpectrumRange,
    NormalizeSpectrum,
    SmoothSpectrum,
)
from scistudio_blocks_spectroscopy.blocks.unmixing import SpectralUnmixing
from scistudio_blocks_spectroscopy.blocks.utilities import (
    AttachFeaturesToSpectralDataset,
    FilterSpectralDataset,
    LoadSpectrum,
    SaveSpectrum,
    SpectralDatasetToSpectrum,
    SpectrumToSpectralDataset,
)
from scistudio_blocks_spectroscopy.types import Spectrum

from scistudio.blocks.base.config import BlockConfig


def _cfg(**params: object) -> BlockConfig:
    return BlockConfig(params=dict(params))


# ---------------------------------------------------------------------------
# Full preprocessing -> feature -> attach pipeline
# ---------------------------------------------------------------------------


def test_preprocess_to_feature_to_dataset_pipeline(tmp_path: Path) -> None:
    pytest.importorskip("scipy")
    # Build a noisy spectrum with a known peak on a baseline, save to disk.
    peak = fx.PeakSpec("gaussian", amplitude=6.0, center=500.0, sigma=8.0)
    spec, _ground = fx.make_peak_spectrum(
        spectrum_id="pipe1", peaks=(peak,), baseline_coeffs=(1.0, 2.0), noise_sigma=0.05, seed=42
    )
    src = tmp_path / "in.spectrum.json"
    fx.write_spectrum_json(spec, src)

    # Load -> Crop -> Baseline -> Smooth -> Normalize.
    loaded = LoadSpectrum().load(_cfg(path=str(src)))
    cropped = CropSpectrumRange().run({"spectra": loaded}, _cfg(lambda_min=440.0, lambda_max=560.0))["cropped"]
    based = BaselineCorrection().run({"spectra": cropped}, _cfg(method="polynomial", poly_order=1))["corrected"]
    smoothed = SmoothSpectrum().run({"spectra": based}, _cfg(method="savitzky_golay", window=11, polyorder=2))[
        "smoothed"
    ]
    normalized = NormalizeSpectrum().run({"spectra": smoothed}, _cfg(method="max"))["normalized"]

    # Normalised peak height == 1 at the true center.
    norm_spec = next(iter(normalized))
    lam, inten = _support.spectrum_arrays(norm_spec)
    assert abs(float(np.max(inten)) - 1.0) < 1e-9
    assert abs(lam[int(np.argmax(inten))] - 500.0) < 2.0
    # spectrum_id survives the whole chain (FR-055).
    assert norm_spec.spectrum_id == next(iter(loaded)).spectrum_id

    # ExtractIntensity -> attach features back to a dataset.
    features = ExtractIntensity().run({"spectra": normalized}, _cfg(target_coordinate=500.0))["features"]
    dataset = next(iter(SpectrumToSpectralDataset().run({"spectra": normalized}, _cfg())["dataset"]))
    attached = AttachFeaturesToSpectralDataset().run(
        {"dataset": dataset, "features": next(iter(features))},
        _cfg(conflict_policy="error"),
    )
    index_tbl, _ = _support.dataset_frames(next(iter(attached["dataset"])))
    assert "intensity" in index_tbl.column_names
    pdf = index_tbl.to_pandas()
    assert abs(float(pdf.iloc[0]["intensity"]) - 1.0) < 1e-6  # measured normalized peak


# ---------------------------------------------------------------------------
# Dataset round-trip: build -> filter -> split
# ---------------------------------------------------------------------------


def test_dataset_build_filter_split_round_trip() -> None:
    specs, _ = fx.make_collection(n=4)
    dataset = next(
        iter(SpectrumToSpectralDataset().run({"spectra": _support.spectra_collection(specs)}, _cfg())["dataset"])
    )
    filtered = next(
        iter(FilterSpectralDataset().run({"dataset": dataset}, _cfg(predicates={"material": "polymerA"}))["dataset"])
    )
    back = list(SpectralDatasetToSpectrum().run({"dataset": filtered}, _cfg())["spectra"])
    # Only polymerA samples survive (spec_0, spec_2) and their ids + metadata round-trip.
    assert [s.spectrum_id for s in back] == ["spec_0", "spec_2"]
    for spec in back:
        assert isinstance(spec.meta, Spectrum.Meta)
        assert spec.meta.lambda_unit == "nm"
        assert spec.user is not None and spec.user.get("material") == "polymerA"


# ---------------------------------------------------------------------------
# Build references -> unmix
# ---------------------------------------------------------------------------


def test_build_references_then_unmix_recovers_mix() -> None:
    refs = fx.make_reference_spectra(labels=("compA", "compB", "compC"))
    coeffs = [0.15, 0.35, 0.5]
    mixture = fx.make_mixture(refs, coeffs, spectrum_id="mix1")
    out = SpectralUnmixing().run(
        {"spectra": _support.spectra_collection([mixture]), "references": _support.spectra_collection(refs)},
        _cfg(method="least_squares"),
    )
    coefficients = _support.dataframe_pandas(next(iter(out["coefficients"])))
    cols = [c for c in coefficients.columns if c not in ("spectrum_id", "method")]
    recovered = [float(coefficients.iloc[0][c]) for c in cols]
    assert np.allclose(recovered, coeffs, atol=1e-6)


# ---------------------------------------------------------------------------
# Build library -> match
# ---------------------------------------------------------------------------


def test_build_library_then_match_top1() -> None:
    library, truth = fx.make_library_dataset()
    # Query is a near-copy of ref_500 with tiny seeded noise.
    noisy = truth["ref_500"] + fx.gaussian_noise(truth["ref_500"].size, 0.01, seed=5)
    query = _support.build_spectrum(fx.DEFAULT_GRID, noisy, spectrum_id="q1")
    out = MatchSpectralLibrary().run(
        {"spectra": _support.spectra_collection([query]), "library": library},
        _cfg(method="cosine_similarity", top_k=1),
    )
    df = _support.dataframe_pandas(next(iter(out["matches"])))
    assert df.iloc[0]["library_spectrum_id"] == "ref_500"
    assert df.iloc[0]["status"] == "success"


# ---------------------------------------------------------------------------
# Fit -> residual + analytic params
# ---------------------------------------------------------------------------


def test_fit_peak_residual_and_analytic_params() -> None:
    pytest.importorskip("scipy")
    peak = fx.PeakSpec("gaussian", amplitude=5.0, center=500.0, sigma=8.0)
    spec, _ = fx.make_peak_spectrum(spectrum_id="fit1", peaks=(peak,))
    _lam, inten = _support.spectrum_arrays(spec)
    out = FitPeak().run({"spectra": _support.spectra_collection([spec])}, _cfg(model="gaussian"))

    _, fit = _support.spectrum_arrays(next(iter(out["fit_curves"])))
    _, residual = _support.spectrum_arrays(next(iter(out["residuals"])))
    # End-to-end: residual == input - fit_curve.
    assert np.allclose(residual, inten - fit)
    row = _support.dataframe_pandas(next(iter(out["parameters"]))).iloc[0]
    assert abs(float(row["fwhm"]) - peak.fwhm) < 1e-2
    assert abs(float(row["area"]) - peak.area) < 0.5


# ---------------------------------------------------------------------------
# Save -> reload preserves a processed result
# ---------------------------------------------------------------------------


def test_processed_spectrum_saves_and_reloads(tmp_path: Path) -> None:
    spec, _ = fx.make_peak_spectrum(spectrum_id="save1", peaks=(fx.PeakSpec("gaussian", 5.0, 500.0, 8.0),))
    normalized = NormalizeSpectrum().run({"spectra": _support.spectra_collection([spec])}, _cfg(method="max"))[
        "normalized"
    ]
    out_path = tmp_path / "processed.spectrum.json"
    SaveSpectrum().save(normalized, _cfg(path=str(out_path)))
    reloaded = LoadSpectrum().load(_cfg(path=str(out_path)))
    _, inten = _support.spectrum_arrays(next(iter(reloaded)))
    assert abs(float(np.max(inten)) - 1.0) < 1e-9
    # Lossless json keeps the id through save/reload.
    assert next(iter(reloaded)).spectrum_id == "save1"
