"""End-to-end workflow tests for the 7 preprocessing blocks (US6, FR-053..FR-081).

Each test drives a LOAD/build -> BLOCK -> SAVE/assert workflow against the real
block classes and asserts the saved/output result equals the analytic
expectation within tolerance, plus output port names/types/shapes/status. Inputs
are built by the seeded pseudo-spectra generators in :mod:`fixtures`.
"""

from __future__ import annotations

from pathlib import Path

import fixtures as fx
import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks.preprocessing import (
    AlignAndResampleSpectra,
    BaselineCorrection,
    CropSpectrumRange,
    NormalizeSpectrum,
    ShiftSpectralAxis,
    SmoothSpectrum,
    SubtractPeakComponent,
)
from scistudio_blocks_spectroscopy.blocks.utilities import LoadSpectrum, SaveSpectrum
from scistudio_blocks_spectroscopy.types import Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio.testing import BlockTestHarness


def _cfg(**params: object) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _coll(*spectra: Spectrum) -> Collection:
    return Collection(list(spectra), item_type=Spectrum)


# ---------------------------------------------------------------------------
# Contract validation for every preprocessing block
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "block_cls",
    [
        CropSpectrumRange,
        ShiftSpectralAxis,
        BaselineCorrection,
        SmoothSpectrum,
        AlignAndResampleSpectra,
        NormalizeSpectrum,
        SubtractPeakComponent,
    ],
)
def test_block_validates(block_cls: type) -> None:
    assert not BlockTestHarness(block_cls).validate_block()


# ---------------------------------------------------------------------------
# CropSpectrumRange (FR-057): LOAD -> CROP -> SAVE -> reload
# ---------------------------------------------------------------------------


def test_crop_load_block_save_roundtrip(tmp_path: Path) -> None:
    spec, _ = fx.make_peak_spectrum(spectrum_id="crop1")
    src = tmp_path / "crop_in.spectrum.json"
    fx.write_spectrum_json(spec, src)

    loaded = LoadSpectrum().load(_cfg(path=str(src)))
    out = CropSpectrumRange().run({"spectra": loaded}, _cfg(lambda_min=450.0, lambda_max=550.0))

    assert set(out) == {"cropped"}
    cropped = list(out["cropped"])
    assert len(cropped) == 1
    lam, _inten = _support.spectrum_arrays(cropped[0])
    assert lam.min() >= 450.0 and lam.max() <= 550.0
    # spectrum_id is preserved across crop (FR-055).
    assert cropped[0].spectrum_id == loaded[0].spectrum_id

    out_path = tmp_path / "crop_out.spectrum.json"
    SaveSpectrum().save(out["cropped"], _cfg(path=str(out_path)))
    reloaded = LoadSpectrum().load(_cfg(path=str(out_path)))
    rlam, _ = _support.spectrum_arrays(reloaded[0])
    assert np.allclose(rlam, lam)


def test_crop_lambda_min_greater_than_max_errors() -> None:
    spec, _ = fx.make_peak_spectrum()
    with pytest.raises(ValueError, match="lambda_min"):
        CropSpectrumRange().run({"spectra": _coll(spec)}, _cfg(lambda_min=600.0, lambda_max=400.0))


def test_crop_out_of_range_yields_empty_spectrum() -> None:
    spec, _ = fx.make_peak_spectrum()
    out = CropSpectrumRange().run({"spectra": _coll(spec)}, _cfg(lambda_min=2000.0, lambda_max=3000.0))
    cropped = next(iter(out["cropped"]))
    lam, inten = _support.spectrum_arrays(cropped)
    assert lam.size == 0 and inten.size == 0


def test_crop_empty_collection_raises() -> None:
    with pytest.raises(ValueError):
        CropSpectrumRange().run({"spectra": Collection([], item_type=Spectrum)}, _cfg())


# ---------------------------------------------------------------------------
# ShiftSpectralAxis (FR-058)
# ---------------------------------------------------------------------------


def test_shift_axis_translates_lambda_only() -> None:
    spec, _ground = fx.make_peak_spectrum(spectrum_id="shift1")
    lam0, inten0 = _support.spectrum_arrays(spec)
    out = ShiftSpectralAxis().run({"spectra": _coll(spec)}, _cfg(shift=12.5))
    shifted = next(iter(out["shifted"]))
    lam1, inten1 = _support.spectrum_arrays(shifted)
    assert np.allclose(lam1, lam0 + 12.5)
    assert np.allclose(inten1, inten0)  # intensities unchanged
    assert shifted.spectrum_id == spec.spectrum_id


def test_shift_zero_is_identity() -> None:
    spec, _ = fx.make_peak_spectrum()
    lam0, inten0 = _support.spectrum_arrays(spec)
    out = ShiftSpectralAxis().run({"spectra": _coll(spec)}, _cfg(shift=0.0))
    lam1, inten1 = _support.spectrum_arrays(next(iter(out["shifted"])))
    assert np.allclose(lam0, lam1) and np.allclose(inten0, inten1)


# ---------------------------------------------------------------------------
# BaselineCorrection (FR-059..FR-064): polynomial baseline recovery
# ---------------------------------------------------------------------------


def test_baseline_polynomial_recovers_known_baseline_on_baseline_only() -> None:
    # A baseline-only spectrum (no peak): polynomial baseline correction must
    # flatten it to ~0 and the estimated baseline must equal the true baseline.
    lam = fx.DEFAULT_GRID
    true_base = fx.polynomial_baseline(lam, (2.0, 3.0, -1.5))
    spec = _support.build_spectrum(lam, true_base, meta=Spectrum.Meta(lambda_unit="nm"), spectrum_id="b1")

    out = BaselineCorrection().run({"spectra": _coll(spec)}, _cfg(method="polynomial", poly_order=3))
    assert set(out) == {"corrected", "baseline", "fit_diagnostics"}

    corrected = next(iter(out["corrected"]))
    baseline = next(iter(out["baseline"]))
    _, ci = _support.spectrum_arrays(corrected)
    _, bi = _support.spectrum_arrays(baseline)
    assert np.allclose(ci, 0.0, atol=1e-6)  # baseline fully removed
    assert np.allclose(bi, true_base, atol=1e-6)  # estimated == true baseline

    # fit_diagnostics: one status row per spectrum keyed by spectrum_id (FR-081).
    diag = _support.dataframe_pandas(next(iter(out["fit_diagnostics"])))
    assert len(diag) == 1
    assert diag.iloc[0]["spectrum_id"] == "b1"
    assert diag.iloc[0]["status"] == "ok"
    assert bool(diag.iloc[0]["converged"])
    # baseline output port type/shape.
    assert isinstance(next(iter(out["fit_diagnostics"])), DataFrame)


def test_baseline_preserves_peak_position() -> None:
    # With a peak on a linear baseline, the corrected peak still centers at the
    # true center even though a global polyfit distorts amplitude.
    spec, _ground = fx.make_peak_spectrum(
        spectrum_id="b2",
        peaks=(fx.PeakSpec("gaussian", amplitude=5.0, center=500.0, sigma=8.0),),
        baseline_coeffs=(1.0, 2.0),
    )
    out = BaselineCorrection().run({"spectra": _coll(spec)}, _cfg(method="polynomial", poly_order=1))
    lam, ci = _support.spectrum_arrays(next(iter(out["corrected"])))
    assert abs(lam[int(np.argmax(ci))] - 500.0) <= 1.0


def test_baseline_asls_runs_and_reports(tmp_path: Path) -> None:
    pytest.importorskip("scipy")
    lam = fx.DEFAULT_GRID
    base = fx.asls_like_baseline(lam, high=5.0)
    peak = fx.gaussian(lam, 8.0, 500.0, 7.0)
    spec = _support.build_spectrum(lam, peak + base, meta=Spectrum.Meta(lambda_unit="nm"), spectrum_id="asls1")
    out = BaselineCorrection().run({"spectra": _coll(spec)}, _cfg(method="asls", lam=1e5, p=0.01, max_iter=50))
    _, ci = _support.spectrum_arrays(next(iter(out["corrected"])))
    # The corrected baseline regions (away from the peak) sit near zero.
    off_peak = (lam < 460.0) | (lam > 540.0)
    assert float(np.median(ci[off_peak])) < 1.0
    diag = _support.dataframe_pandas(next(iter(out["fit_diagnostics"])))
    assert diag.iloc[0]["method"] == "asls"


def test_baseline_short_spectrum_reports_status_not_crash() -> None:
    # 2-point spectrum: too short for baseline -> non-ok status row, no crash.
    spec = _support.build_spectrum([400.0, 401.0], [1.0, 2.0], meta=Spectrum.Meta(), spectrum_id="short")
    out = BaselineCorrection().run({"spectra": _coll(spec)}, _cfg(method="polynomial", poly_order=3))
    diag = _support.dataframe_pandas(next(iter(out["fit_diagnostics"])))
    assert diag.iloc[0]["status"].startswith("error")
    # Input passes through unchanged on failure.
    _, ci = _support.spectrum_arrays(next(iter(out["corrected"])))
    assert np.allclose(ci, [1.0, 2.0])


# ---------------------------------------------------------------------------
# SmoothSpectrum (FR-065, FR-066): grid unchanged, noise reduced
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["savitzky_golay", "moving_average", "gaussian", "median"])
def test_smooth_preserves_grid_and_reduces_noise(method: str) -> None:
    pytest.importorskip("scipy")
    spec, ground = fx.make_peak_spectrum(spectrum_id="sm1", noise_sigma=0.3, seed=11)
    lam0, inten0 = _support.spectrum_arrays(spec)
    out = SmoothSpectrum().run({"spectra": _coll(spec)}, _cfg(method=method, window=11, polyorder=2, sigma=2.0))
    assert set(out) == {"smoothed"}
    smoothed = next(iter(out["smoothed"]))
    lam1, inten1 = _support.spectrum_arrays(smoothed)
    assert np.allclose(lam0, lam1)  # lambda grid unchanged (FR-066)
    # Smoothed signal is closer to the noise-free pure+baseline than the noisy input.
    clean = ground.pure_peak + ground.baseline
    assert float(np.std(inten1 - clean)) < float(np.std(inten0 - clean))
    assert smoothed.spectrum_id == spec.spectrum_id


# ---------------------------------------------------------------------------
# AlignAndResampleSpectra (FR-067..FR-073)
# ---------------------------------------------------------------------------


def test_align_resample_to_first_grid_no_alignment() -> None:
    a, _ = fx.make_peak_spectrum(spectrum_id="a", grid=np.linspace(400, 600, 201))
    b, _ = fx.make_peak_spectrum(spectrum_id="b", grid=np.linspace(400, 600, 401))
    out = AlignAndResampleSpectra().run(
        {"spectra": _support.spectra_collection([a, b])},
        _cfg(alignment_method="none", target_grid_mode="first"),
    )
    assert set(out) == {"aligned", "fit_curves", "fit_diagnostics"}
    aligned = list(out["aligned"])
    la0, _ = _support.spectrum_arrays(aligned[0])
    la1, _ = _support.spectrum_arrays(aligned[1])
    assert la0.shape == (201,) and la1.shape == (201,)  # both on the first grid
    # No peak fit -> fit_curves empty, diagnostics report the non-fit method.
    assert len(list(out["fit_curves"])) == 0
    diag = _support.dataframe_pandas(next(iter(out["fit_diagnostics"])))
    assert (diag["method"] == "none").all()
    assert len(diag) == 2


def test_align_peak_fit_recovers_shift() -> None:
    pytest.importorskip("scipy")
    lam = np.linspace(400, 600, 401)
    reference = _support.build_spectrum(lam, fx.gaussian(lam, 5.0, 500.0, 8.0), spectrum_id="ref")
    # Sample peak is offset by +6 nm; peak_fit alignment should shift it back.
    sample = _support.build_spectrum(lam, fx.gaussian(lam, 5.0, 506.0, 8.0), spectrum_id="samp")
    out = AlignAndResampleSpectra().run(
        {"spectra": _support.spectra_collection([sample]), "reference": reference},
        _cfg(alignment_method="peak_fit", target_grid_mode="reference"),
    )
    aligned = next(iter(out["aligned"]))
    la, ia = _support.spectrum_arrays(aligned)
    assert np.allclose(la, lam)  # resampled to reference grid
    # Aligned peak now centers near the reference center (500).
    assert abs(la[int(np.nanargmax(ia))] - 500.0) <= 2.0
    # fit_curves present (one per input) when peak_fit.
    assert len(list(out["fit_curves"])) == 1
    diag = _support.dataframe_pandas(next(iter(out["fit_diagnostics"])))
    assert abs(float(diag.iloc[0]["applied_shift"]) - (-6.0)) <= 2.0


def test_align_range_step_grid() -> None:
    spec, _ = fx.make_peak_spectrum()
    out = AlignAndResampleSpectra().run(
        {"spectra": _coll(spec)},
        _cfg(alignment_method="none", target_grid_mode="range_step", lambda_min=450.0, lambda_max=550.0, step=2.0),
    )
    la, _ = _support.spectrum_arrays(next(iter(out["aligned"])))
    assert la.min() >= 450.0 and la.max() <= 550.0
    assert np.allclose(np.diff(la), 2.0)


# ---------------------------------------------------------------------------
# NormalizeSpectrum (FR-074, FR-075)
# ---------------------------------------------------------------------------


def test_normalize_max_scales_peak_to_one() -> None:
    spec, _ = fx.make_peak_spectrum(spectrum_id="n1", peaks=(fx.PeakSpec("gaussian", 5.0, 500.0, 8.0),))
    out = NormalizeSpectrum().run({"spectra": _coll(spec)}, _cfg(method="max"))
    _, inten = _support.spectrum_arrays(next(iter(out["normalized"])))
    assert abs(float(np.max(inten)) - 1.0) < 1e-9


def test_normalize_minmax_to_unit_interval() -> None:
    spec, _ = fx.make_peak_spectrum(spectrum_id="n2", baseline_coeffs=(2.0, 1.0))
    out = NormalizeSpectrum().run({"spectra": _coll(spec)}, _cfg(method="minmax"))
    _, inten = _support.spectrum_arrays(next(iter(out["normalized"])))
    assert abs(float(np.min(inten))) < 1e-9
    assert abs(float(np.max(inten)) - 1.0) < 1e-9


def test_normalize_flat_spectrum_passthrough_no_divzero() -> None:
    # All-zero spectrum: zero denominator -> pass through unchanged, no NaN.
    spec = _support.build_spectrum(fx.DEFAULT_GRID, np.zeros_like(fx.DEFAULT_GRID), spectrum_id="flat")
    out = NormalizeSpectrum().run({"spectra": _coll(spec)}, _cfg(method="max"))
    _, inten = _support.spectrum_arrays(next(iter(out["normalized"])))
    assert np.allclose(inten, 0.0) and np.isfinite(inten).all()


# ---------------------------------------------------------------------------
# SubtractPeakComponent (FR-076..FR-080)
# ---------------------------------------------------------------------------


def test_subtract_peak_component_removes_known_gaussian() -> None:
    pytest.importorskip("scipy")
    lam = fx.DEFAULT_GRID
    peak = fx.gaussian(lam, 6.0, 500.0, 7.0)
    spec = _support.build_spectrum(lam, peak, meta=Spectrum.Meta(lambda_unit="nm"), spectrum_id="sp1")
    out = SubtractPeakComponent().run(
        {"spectra": _coll(spec)},
        _cfg(model="gaussian", peak_center=500.0, window=60.0),
    )
    assert set(out) == {"corrected", "component", "fit_diagnostics"}
    _, corrected = _support.spectrum_arrays(next(iter(out["corrected"])))
    _, component = _support.spectrum_arrays(next(iter(out["component"])))
    assert np.allclose(component, peak, atol=1e-3)  # fitted component == true peak
    assert np.allclose(corrected, 0.0, atol=1e-3)  # corrected == input - component
    diag = _support.dataframe_pandas(next(iter(out["fit_diagnostics"])))
    row = diag.iloc[0]
    assert row["status"] == "ok"
    assert abs(float(row["center"]) - 500.0) < 1e-2
    assert abs(float(row["fwhm"]) - fx.PeakSpec("gaussian", 6.0, 500.0, 7.0).fwhm) < 1e-1


def test_subtract_peak_component_noise_window_reports_status() -> None:
    pytest.importorskip("scipy")
    # Noise-only window with too few points to fit -> non-ok status, no crash.
    spec = _support.build_spectrum([400.0, 401.0, 402.0], [0.1, -0.1, 0.05], spectrum_id="noise")
    out = SubtractPeakComponent().run({"spectra": _coll(spec)}, _cfg(model="gaussian"))
    diag = _support.dataframe_pandas(next(iter(out["fit_diagnostics"])))
    assert diag.iloc[0]["status"].startswith("error")
    # Component is zero and the input passes through.
    _, corrected = _support.spectrum_arrays(next(iter(out["corrected"])))
    assert np.allclose(corrected, [0.1, -0.1, 0.05])
