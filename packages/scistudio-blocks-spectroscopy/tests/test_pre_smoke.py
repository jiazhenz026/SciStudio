"""Smoke tests for the seven preprocessing blocks (FR-053..FR-081).

Each test builds synthetic spectra via ``_support``, runs the block through its
``run()`` method, and asserts the declared output ports, preserved item
count/order/``spectrum_id`` (FR-055), key numeric results, and ``status``
columns for the fitting/baseline blocks. scipy-using paths are guarded with
``pytest.importorskip("scipy")`` at function scope (scipy is lazy-imported
inside the blocks, so import-free paths run without it).
"""

from __future__ import annotations

from typing import Any

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
from scistudio_blocks_spectroscopy.types import Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio.testing import BlockTestHarness

_PREPROCESSING_BLOCKS = [
    CropSpectrumRange,
    ShiftSpectralAxis,
    BaselineCorrection,
    SmoothSpectrum,
    AlignAndResampleSpectra,
    NormalizeSpectrum,
    SubtractPeakComponent,
]


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _cfg(**params: object) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _peak(lam: np.ndarray, center: float, amplitude: float = 5.0, sigma: float = 4.0) -> np.ndarray:
    return amplitude * np.exp(-0.5 * ((lam - center) / sigma) ** 2)


@pytest.fixture
def lam() -> np.ndarray:
    return np.linspace(100.0, 200.0, 101)


@pytest.fixture
def spectra(lam: np.ndarray) -> Collection:
    # A gaussian peak at 150 plus a sloped baseline, two distinct spectra.
    base = _peak(lam, 150.0) + 0.01 * lam + 1.0
    s1 = _support.build_spectrum(lam, base, spectrum_id="sid-A")
    s2 = _support.build_spectrum(lam, base * 0.5 + 2.0, spectrum_id="sid-B")
    return _support.spectra_collection([s1, s2])


def _diagnostics_frame(outputs: dict[str, Collection], port: str = "fit_diagnostics") -> Any:
    collection = outputs[port]
    frame = next(iter(collection))
    assert isinstance(frame, DataFrame)
    return _support.dataframe_pandas(frame)


# ---------------------------------------------------------------------------
# Contract validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("block_cls", _PREPROCESSING_BLOCKS)
def test_block_passes_contract(block_cls: type) -> None:
    assert not BlockTestHarness(block_cls).validate_block()


# ---------------------------------------------------------------------------
# CropSpectrumRange (FR-057)
# ---------------------------------------------------------------------------


def test_crop_keeps_in_range_only(spectra: Collection, lam: np.ndarray) -> None:
    outputs = CropSpectrumRange().run({"spectra": spectra}, _cfg(lambda_min=120.0, lambda_max=180.0))
    cropped = list(outputs["cropped"])
    assert set(outputs) == {"cropped"}
    assert len(cropped) == 2
    assert [s.spectrum_id for s in cropped] == ["sid-A", "sid-B"]
    crop_lam, _ = _support.spectrum_arrays(cropped[0])
    assert crop_lam.min() >= 120.0
    assert crop_lam.max() <= 180.0
    # Kept intensities are unchanged from the original in-range points.
    orig_lam, orig_inten = _support.spectrum_arrays(next(iter(spectra)))
    _, crop_inten = _support.spectrum_arrays(cropped[0])
    in_range = (orig_lam >= 120.0) & (orig_lam <= 180.0)
    assert np.allclose(crop_inten, orig_inten[in_range])


def test_crop_rejects_inverted_range(spectra: Collection) -> None:
    with pytest.raises(ValueError):
        CropSpectrumRange().run({"spectra": spectra}, _cfg(lambda_min=180.0, lambda_max=120.0))


# ---------------------------------------------------------------------------
# ShiftSpectralAxis (FR-058)
# ---------------------------------------------------------------------------


def test_shift_axis_preserves_intensity(spectra: Collection, lam: np.ndarray) -> None:
    outputs = ShiftSpectralAxis().run({"spectra": spectra}, _cfg(shift=10.0))
    shifted = list(outputs["shifted"])
    assert len(shifted) == 2
    orig_lam, orig_inten = _support.spectrum_arrays(next(iter(spectra)))
    new_lam, new_inten = _support.spectrum_arrays(shifted[0])
    assert np.allclose(new_lam, orig_lam + 10.0)
    assert np.allclose(new_inten, orig_inten)
    assert shifted[0].spectrum_id == "sid-A"


# ---------------------------------------------------------------------------
# BaselineCorrection (FR-059..FR-064)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["polynomial", "asls", "arpls", "airpls"])
def test_baseline_emits_three_ports_per_method(spectra: Collection, lam: np.ndarray, method: str) -> None:
    pytest.importorskip("scipy")
    outputs = BaselineCorrection().run(
        {"spectra": spectra}, _cfg(method=method, poly_order=1, lam=1e5, p=0.01, max_iter=40)
    )
    assert set(outputs) == {"corrected", "baseline", "fit_diagnostics"}
    corrected = list(outputs["corrected"])
    baseline = list(outputs["baseline"])
    assert len(corrected) == 2
    assert len(baseline) == 2
    # corrected == input - baseline, on the same grid as the input (FR-063).
    in_lam, in_inten = _support.spectrum_arrays(next(iter(spectra)))
    b_lam, b_inten = _support.spectrum_arrays(baseline[0])
    c_lam, c_inten = _support.spectrum_arrays(corrected[0])
    assert np.allclose(b_lam, in_lam)
    assert np.allclose(c_lam, in_lam)
    assert np.allclose(c_inten, in_inten - b_inten)


def test_baseline_diagnostics_one_row_per_spectrum(spectra: Collection) -> None:
    pytest.importorskip("scipy")
    outputs = BaselineCorrection().run({"spectra": spectra}, _cfg(method="polynomial", poly_order=1))
    pdf = _diagnostics_frame(outputs)
    assert len(pdf) == 2
    assert list(pdf["spectrum_id"]) == ["sid-A", "sid-B"]
    required = {"spectrum_id", "method", "status", "parameters", "converged", "iterations", "rmse"}
    assert required.issubset(pdf.columns)
    assert list(pdf["status"]) == ["ok", "ok"]
    assert bool(pdf["converged"].iloc[0]) is True


def test_baseline_polynomial_recovers_linear_baseline() -> None:
    lam = np.linspace(0.0, 100.0, 201)
    baseline_true = 0.5 * lam + 3.0
    s = _support.build_spectrum(lam, baseline_true, spectrum_id="lin")
    outputs = BaselineCorrection().run(
        {"spectra": _support.spectra_collection([s])}, _cfg(method="polynomial", poly_order=1)
    )
    _, corrected = _support.spectrum_arrays(next(iter(outputs["corrected"])))
    # A pure linear signal corrected by a 1st-order polynomial baseline ~ 0.
    assert np.allclose(corrected, 0.0, atol=1e-6)


# ---------------------------------------------------------------------------
# SmoothSpectrum (FR-065, FR-066)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["savitzky_golay", "moving_average", "gaussian", "median"])
def test_smooth_preserves_grid(spectra: Collection, lam: np.ndarray, method: str) -> None:
    pytest.importorskip("scipy")
    outputs = SmoothSpectrum().run({"spectra": spectra}, _cfg(method=method, window=5, polyorder=2, sigma=1.0))
    smoothed = list(outputs["smoothed"])
    assert set(outputs) == {"smoothed"}
    assert len(smoothed) == 2
    new_lam, _ = _support.spectrum_arrays(smoothed[0])
    assert np.allclose(new_lam, lam)  # grid unchanged (FR-066)
    assert smoothed[0].spectrum_id == "sid-A"


def test_smooth_reduces_noise_variance(lam: np.ndarray) -> None:
    pytest.importorskip("scipy")
    rng = np.random.default_rng(0)
    clean = _peak(lam, 150.0)
    noisy = clean + rng.normal(0.0, 0.2, size=lam.shape)
    s = _support.build_spectrum(lam, noisy, spectrum_id="noisy")
    outputs = SmoothSpectrum().run(
        {"spectra": _support.spectra_collection([s])}, _cfg(method="moving_average", window=7)
    )
    _, smoothed = _support.spectrum_arrays(next(iter(outputs["smoothed"])))
    assert np.var(smoothed - clean) < np.var(noisy - clean)


# ---------------------------------------------------------------------------
# AlignAndResampleSpectra (FR-067..FR-073)
# ---------------------------------------------------------------------------


def test_align_emits_three_ports_no_fit(spectra: Collection, lam: np.ndarray) -> None:
    outputs = AlignAndResampleSpectra().run(
        {"spectra": spectra}, _cfg(alignment_method="none", target_grid_mode="first")
    )
    assert set(outputs) == {"aligned", "fit_curves", "fit_diagnostics"}
    aligned = list(outputs["aligned"])
    fit_curves = list(outputs["fit_curves"])
    assert len(aligned) == 2
    assert len(fit_curves) == 0  # empty when no fit (FR-072)
    a_lam, _ = _support.spectrum_arrays(aligned[0])
    assert np.allclose(a_lam, lam)
    pdf = _diagnostics_frame(outputs)
    assert len(pdf) == 2
    assert {"spectrum_id", "method", "status", "applied_shift", "fit_quality"}.issubset(pdf.columns)
    assert list(pdf["applied_shift"]) == [0.0, 0.0]


def test_align_peak_fit_populates_fit_curves() -> None:
    pytest.importorskip("scipy")
    lam = np.linspace(100.0, 200.0, 201)
    spec = _support.build_spectrum(lam, _peak(lam, 150.0), spectrum_id="s")
    ref = _support.build_spectrum(lam, _peak(lam, 155.0), spectrum_id="r")
    outputs = AlignAndResampleSpectra().run(
        {
            "spectra": _support.spectra_collection([spec]),
            "reference": _support.spectra_collection([ref]),
        },
        _cfg(alignment_method="peak_fit", target_grid_mode="reference"),
    )
    fit_curves = list(outputs["fit_curves"])
    assert len(fit_curves) == 1  # one fitted peak curve per input (FR-072)
    pdf = _diagnostics_frame(outputs)
    assert pdf["status"].iloc[0] == "ok"
    # Spectrum peak at 150 aligned to reference peak at 155 => +5 shift.
    assert float(pdf["applied_shift"].iloc[0]) == pytest.approx(5.0, abs=0.5)
    aligned = next(iter(outputs["aligned"]))
    a_lam, a_inten = _support.spectrum_arrays(aligned)
    assert float(a_lam[int(np.nanargmax(a_inten))]) == pytest.approx(155.0, abs=1.0)


def test_align_range_step_grid(spectra: Collection) -> None:
    outputs = AlignAndResampleSpectra().run(
        {"spectra": spectra},
        _cfg(
            alignment_method="none",
            target_grid_mode="range_step",
            lambda_min=110.0,
            lambda_max=190.0,
            step=2.0,
        ),
    )
    a_lam, _ = _support.spectrum_arrays(next(iter(outputs["aligned"])))
    assert a_lam.min() >= 110.0
    assert a_lam.max() <= 190.0
    assert np.allclose(np.diff(a_lam), 2.0)


def test_align_explicit_grid_requires_grid(spectra: Collection) -> None:
    with pytest.raises(ValueError):
        AlignAndResampleSpectra().run({"spectra": spectra}, _cfg(alignment_method="none", target_grid_mode="explicit"))


def test_align_cross_correlation_with_reference() -> None:
    pytest.importorskip("scipy")
    lam = np.linspace(100.0, 200.0, 201)
    spec = _support.build_spectrum(lam, _peak(lam, 150.0), spectrum_id="s")
    ref = _support.build_spectrum(lam, _peak(lam, 156.0), spectrum_id="r")
    outputs = AlignAndResampleSpectra().run(
        {
            "spectra": _support.spectra_collection([spec]),
            "reference": _support.spectra_collection([ref]),
        },
        _cfg(alignment_method="cross_correlation", target_grid_mode="reference"),
    )
    pdf = _diagnostics_frame(outputs)
    assert pdf["status"].iloc[0] == "ok"
    # Cross-correlation recovers a positive lag toward the reference peak.
    assert float(pdf["applied_shift"].iloc[0]) == pytest.approx(6.0, abs=1.0)


# ---------------------------------------------------------------------------
# NormalizeSpectrum (FR-074, FR-075)
# ---------------------------------------------------------------------------


def test_normalize_max_and_minmax(spectra: Collection) -> None:
    out_max = NormalizeSpectrum().run({"spectra": spectra}, _cfg(method="max"))
    normalized = list(out_max["normalized"])
    assert set(out_max) == {"normalized"}
    assert len(normalized) == 2
    _, inten = _support.spectrum_arrays(normalized[0])
    assert inten.max() == pytest.approx(1.0)

    out_mm = NormalizeSpectrum().run({"spectra": spectra}, _cfg(method="minmax"))
    _, inten_mm = _support.spectrum_arrays(next(iter(out_mm["normalized"])))
    assert inten_mm.min() == pytest.approx(0.0)
    assert inten_mm.max() == pytest.approx(1.0)


def test_normalize_constant_spectrum_passthrough() -> None:
    lam = np.linspace(0.0, 10.0, 11)
    s = _support.build_spectrum(lam, np.full_like(lam, 3.0), spectrum_id="flat")
    outputs = NormalizeSpectrum().run({"spectra": _support.spectra_collection([s])}, _cfg(method="minmax"))
    _, inten = _support.spectrum_arrays(next(iter(outputs["normalized"])))
    # Zero span => passthrough (no divide-by-zero).
    assert np.allclose(inten, 3.0)


def test_normalize_rejects_min_method(spectra: Collection) -> None:
    # FR-075: no 'min' method exists.
    with pytest.raises(ValueError):
        NormalizeSpectrum().run({"spectra": spectra}, _cfg(method="min"))


# ---------------------------------------------------------------------------
# SubtractPeakComponent (FR-076..FR-080)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model", ["gaussian", "lorentzian", "voigt"])
def test_subtract_peak_emits_three_ports(model: str) -> None:
    pytest.importorskip("scipy")
    lam = np.linspace(100.0, 200.0, 201)
    spec = _support.build_spectrum(lam, _peak(lam, 150.0) + 1.0, spectrum_id="sid-A")
    outputs = SubtractPeakComponent().run(
        {"spectra": _support.spectra_collection([spec])},
        _cfg(model=model, peak_center=150.0, window=30.0),
    )
    assert set(outputs) == {"corrected", "component", "fit_diagnostics"}
    component = list(outputs["component"])
    corrected = list(outputs["corrected"])
    assert len(component) == 1
    assert len(corrected) == 1
    # corrected == input - component, all on the same grid (FR-079).
    in_lam, in_inten = _support.spectrum_arrays(spec)
    comp_lam, comp_inten = _support.spectrum_arrays(component[0])
    corr_lam, corr_inten = _support.spectrum_arrays(corrected[0])
    assert np.allclose(comp_lam, in_lam)
    assert np.allclose(corr_lam, in_lam)
    assert np.allclose(corr_inten, in_inten - comp_inten)

    pdf = _diagnostics_frame(outputs)
    assert len(pdf) == 1
    required = {"spectrum_id", "model", "status", "center", "amplitude", "fwhm", "area", "rmse"}
    assert required.issubset(pdf.columns)
    assert pdf["status"].iloc[0] == "ok"
    assert float(pdf["center"].iloc[0]) == pytest.approx(150.0, abs=1.0)
    assert pdf["spectrum_id"].iloc[0] == "sid-A"


def test_subtract_peak_failure_records_status_and_passthrough() -> None:
    pytest.importorskip("scipy")
    lam = np.linspace(100.0, 200.0, 201)
    spec = _support.build_spectrum(lam, _peak(lam, 150.0), spectrum_id="far")
    # A fit window with no data points forces a per-spectrum failure.
    outputs = SubtractPeakComponent().run(
        {"spectra": _support.spectra_collection([spec])},
        _cfg(model="gaussian", peak_center=1000.0, window=5.0),
    )
    pdf = _diagnostics_frame(outputs)
    assert pdf["status"].iloc[0].startswith("error")
    # Component is zero, input passes through unchanged.
    _, comp = _support.spectrum_arrays(next(iter(outputs["component"])))
    _, in_inten = _support.spectrum_arrays(spec)
    _, corr = _support.spectrum_arrays(next(iter(outputs["corrected"])))
    assert np.allclose(comp, 0.0)
    assert np.allclose(corr, in_inten)


# ---------------------------------------------------------------------------
# FR-055 — item count / order / spectrum_id preserved across every block
# ---------------------------------------------------------------------------


def test_all_blocks_preserve_count_order_and_id(spectra: Collection) -> None:
    pytest.importorskip("scipy")
    expected_ids = [s.spectrum_id for s in spectra]
    cases: list[tuple[type, str, dict[str, object]]] = [
        (CropSpectrumRange, "cropped", {"lambda_min": 120.0, "lambda_max": 180.0}),
        (ShiftSpectralAxis, "shifted", {"shift": 5.0}),
        (BaselineCorrection, "corrected", {"method": "polynomial", "poly_order": 1}),
        (SmoothSpectrum, "smoothed", {"method": "moving_average", "window": 5}),
        (
            AlignAndResampleSpectra,
            "aligned",
            {"alignment_method": "none", "target_grid_mode": "first"},
        ),
        (NormalizeSpectrum, "normalized", {"method": "max"}),
    ]
    for block_cls, primary_port, params in cases:
        outputs = block_cls().run({"spectra": spectra}, _cfg(**params))
        items = list(outputs[primary_port])
        assert len(items) == len(expected_ids), block_cls.__name__
        assert [s.spectrum_id for s in items] == expected_ids, block_cls.__name__
        assert all(isinstance(s, Spectrum) for s in items), block_cls.__name__
