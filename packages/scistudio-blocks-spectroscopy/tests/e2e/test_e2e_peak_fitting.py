"""End-to-end workflow tests for FitPeak (US10, FR-113..FR-120).

FitPeak fits gaussian/lorentzian/voigt models WITHOUT modifying the inputs and
emits ``fit_curves``, ``residuals``, and a ``parameters`` table (NOT
``fit_diagnostics``). Tests assert recovered center/amplitude/FWHM/area against
analytic ground truth, verify ``residual == input - fit_curve``, and that a fit
failure records a non-success status with no misleading params.
"""

from __future__ import annotations

import fixtures as fx
import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks.peak_fitting import FitPeak
from scistudio_blocks_spectroscopy.types import Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio.testing import BlockTestHarness


def _cfg(**params: object) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _coll(*spectra: Spectrum) -> Collection:
    return Collection(list(spectra), item_type=Spectrum)


def test_block_validates() -> None:
    assert not BlockTestHarness(FitPeak).validate_block()


def test_fit_peak_emits_three_ports_gaussian() -> None:
    pytest.importorskip("scipy")
    peak = fx.PeakSpec("gaussian", amplitude=5.0, center=500.0, sigma=8.0)
    spec, _ = fx.make_peak_spectrum(spectrum_id="g1", peaks=(peak,))
    out = FitPeak().run({"spectra": _coll(spec)}, _cfg(model="gaussian"))

    assert set(out) == {"fit_curves", "residuals", "parameters"}
    assert isinstance(next(iter(out["parameters"])), DataFrame)
    params = _support.dataframe_pandas(next(iter(out["parameters"])))
    row = params.iloc[0]
    assert row["status"] == "ok"
    assert row["model"] == "gaussian"
    assert row["spectrum_id"] == "g1"
    # Analytic recovery within tolerance.
    assert abs(float(row["center"]) - 500.0) < 1e-3
    assert abs(float(row["amplitude"]) - 5.0) < 1e-3
    assert abs(float(row["sigma"]) - 8.0) < 1e-3
    assert abs(float(row["fwhm"]) - peak.fwhm) < 1e-2
    assert abs(float(row["area"]) - peak.area) < 0.5


def test_fit_peak_residual_equals_input_minus_fit() -> None:
    pytest.importorskip("scipy")
    spec, _ = fx.make_peak_spectrum(spectrum_id="g2", peaks=(fx.PeakSpec("gaussian", 5.0, 500.0, 8.0),))
    lam, inten = _support.spectrum_arrays(spec)
    out = FitPeak().run({"spectra": _coll(spec)}, _cfg(model="gaussian"))
    _, fit = _support.spectrum_arrays(next(iter(out["fit_curves"])))
    rlam, residual = _support.spectrum_arrays(next(iter(out["residuals"])))
    # FR-117/FR-118: residual is exactly input - fit on the input grid.
    assert np.allclose(residual, inten - fit)
    assert np.allclose(rlam, lam)
    # Clean gaussian -> residual is ~0 everywhere.
    assert float(np.max(np.abs(residual))) < 1e-6
    # spectrum_id preserved on both spectrum outputs.
    assert next(iter(out["fit_curves"])).spectrum_id == "g2"
    assert next(iter(out["residuals"])).spectrum_id == "g2"


def test_fit_peak_does_not_modify_input() -> None:
    pytest.importorskip("scipy")
    spec, _ = fx.make_peak_spectrum(spectrum_id="g3", peaks=(fx.PeakSpec("gaussian", 5.0, 500.0, 8.0),))
    lam0, inten0 = _support.spectrum_arrays(spec)
    FitPeak().run({"spectra": _coll(spec)}, _cfg(model="gaussian"))
    lam1, inten1 = _support.spectrum_arrays(spec)
    assert np.allclose(lam0, lam1) and np.allclose(inten0, inten1)


def test_fit_peak_lorentzian_recovers_params() -> None:
    pytest.importorskip("scipy")
    peak = fx.PeakSpec("lorentzian", amplitude=4.0, center=510.0, gamma=6.0)
    spec, _ = fx.make_peak_spectrum(spectrum_id="l1", peaks=(peak,))
    out = FitPeak().run({"spectra": _coll(spec)}, _cfg(model="lorentzian"))
    row = _support.dataframe_pandas(next(iter(out["parameters"]))).iloc[0]
    assert row["status"] == "ok"
    assert abs(float(row["center"]) - 510.0) < 1e-2
    assert abs(float(row["amplitude"]) - 4.0) < 1e-2
    assert abs(float(row["gamma"]) - 6.0) < 1e-2
    assert abs(float(row["fwhm"]) - peak.fwhm) < 1e-1


def test_fit_peak_voigt_runs_and_reports() -> None:
    pytest.importorskip("scipy")
    peak = fx.PeakSpec("voigt", amplitude=5.0, center=500.0, sigma=5.0, gamma=4.0)
    spec, _ = fx.make_peak_spectrum(spectrum_id="v1", peaks=(peak,))
    out = FitPeak().run({"spectra": _coll(spec)}, _cfg(model="voigt"))
    row = _support.dataframe_pandas(next(iter(out["parameters"]))).iloc[0]
    assert row["status"] == "ok"
    assert abs(float(row["center"]) - 500.0) < 0.5
    # Voigt FWHM via the pseudo-Voigt approximation should be in the right ballpark.
    assert abs(float(row["fwhm"]) - peak.fwhm) < 2.0


def test_fit_peak_failure_records_status_no_misleading_params() -> None:
    pytest.importorskip("scipy")
    # Too few points to fit -> non-success status, all params None (FR-119).
    spec = _support.build_spectrum([400.0, 401.0], [1.0, 1.0], spectrum_id="bad")
    out = FitPeak().run({"spectra": _coll(spec)}, _cfg(model="gaussian"))
    row = _support.dataframe_pandas(next(iter(out["parameters"]))).iloc[0]
    assert row["status"] != "ok"
    assert row["center"] is None and row["amplitude"] is None and row["fwhm"] is None
    # Fit curve is zeroed; residual == input on failure.
    _, fit = _support.spectrum_arrays(next(iter(out["fit_curves"])))
    _, residual = _support.spectrum_arrays(next(iter(out["residuals"])))
    assert np.allclose(fit, 0.0)
    assert np.allclose(residual, [1.0, 1.0])


def test_fit_peak_within_range_only() -> None:
    pytest.importorskip("scipy")
    spec, _ = fx.make_peak_spectrum(spectrum_id="g4", peaks=(fx.PeakSpec("gaussian", 5.0, 500.0, 8.0),))
    out = FitPeak().run({"spectra": _coll(spec)}, _cfg(model="gaussian", lambda_min=470.0, lambda_max=530.0))
    row = _support.dataframe_pandas(next(iter(out["parameters"]))).iloc[0]
    assert row["status"] == "ok"
    assert abs(float(row["center"]) - 500.0) < 1e-2


def test_fit_peak_multiple_spectra_one_row_each() -> None:
    pytest.importorskip("scipy")
    specs, _ = fx.make_collection(n=3, noise_sigma=0.0)
    out = FitPeak().run({"spectra": _support.spectra_collection(specs)}, _cfg(model="gaussian"))
    params = _support.dataframe_pandas(next(iter(out["parameters"])))
    assert len(params) == 3
    assert list(params["spectrum_id"]) == ["spec_0", "spec_1", "spec_2"]
    assert len(list(out["fit_curves"])) == 3
    assert len(list(out["residuals"])) == 3
