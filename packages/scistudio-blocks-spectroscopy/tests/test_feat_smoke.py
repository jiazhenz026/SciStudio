"""Smoke tests for the feature-extraction and peak-fitting blocks.

One load -> block -> save-shape test per block: build synthetic spectra through
``_support``, run each block, and assert the output ports, item count, the key
numeric result, and the ``status`` column. scipy-using blocks (``FindPeaks``,
``FitPeak``) guard with ``pytest.importorskip("scipy")``.

Covers FR-082..FR-093 (feature extraction) and FR-113..FR-120 (peak fitting).
"""

from __future__ import annotations

import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support as support
from scistudio_blocks_spectroscopy.blocks.feature_extraction import (
    CalculateAUC,
    CalculateCentroid,
    CalculateRatio,
    ExtractIntensity,
    FindPeaks,
)
from scistudio_blocks_spectroscopy.blocks.peak_fitting import FitPeak
from scistudio_blocks_spectroscopy.types import Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio.testing import BlockTestHarness


def _gaussian(lam: np.ndarray, amplitude: float, center: float, sigma: float) -> np.ndarray:
    return amplitude * np.exp(-((lam - center) ** 2) / (2.0 * sigma**2))


def _config(**params: object) -> BlockConfig:
    config = BlockConfig()
    config.params = dict(params)
    return config


@pytest.fixture
def spectra() -> Collection:
    """Two synthetic spectra: a single peak and a double peak."""
    lam = np.linspace(400.0, 1400.0, 201)
    single = support.build_spectrum(lam, _gaussian(lam, 10.0, 900.0, 25.0), spectrum_id="A")
    double = support.build_spectrum(
        lam,
        _gaussian(lam, 5.0, 700.0, 40.0) + _gaussian(lam, 8.0, 1100.0, 20.0),
        spectrum_id="B",
    )
    collection: Collection = support.spectra_collection([single, double])
    return collection


def _feature_table(outputs: dict[str, Collection]) -> dict[str, list]:
    assert set(outputs) == {"features"}
    items = list(outputs["features"])
    assert len(items) == 1
    frame = items[0]
    assert isinstance(frame, DataFrame)
    table: dict[str, list] = support.dataframe_arrow(frame).to_pydict()
    return table


# ---------------------------------------------------------------------------
# Contract validation (all six blocks)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "block_cls",
    [ExtractIntensity, CalculateAUC, CalculateCentroid, CalculateRatio, FindPeaks, FitPeak],
)
def test_block_validates(block_cls: type) -> None:
    assert not BlockTestHarness(block_cls).validate_block()


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def test_extract_intensity_one_row_per_spectrum(spectra: Collection) -> None:
    table = _feature_table(ExtractIntensity().run({"spectra": spectra}, _config(target_coordinate=900.0)))
    assert table["spectrum_id"] == ["A", "B"]
    assert set(table) == {"spectrum_id", "measured_coordinate", "intensity", "status"}
    assert table["status"] == ["ok", "ok"]
    assert table["intensity"][0] == pytest.approx(10.0, abs=0.1)
    assert table["measured_coordinate"][0] == pytest.approx(900.0, abs=2.5)


def test_extract_intensity_range_reducer(spectra: Collection) -> None:
    table = _feature_table(
        ExtractIntensity().run({"spectra": spectra}, _config(lambda_min=850.0, lambda_max=950.0, reducer="mean"))
    )
    assert table["status"] == ["ok", "ok"]
    assert table["intensity"][0] is not None


def test_auc_range_integration(spectra: Collection) -> None:
    table = _feature_table(CalculateAUC().run({"spectra": spectra}, _config(lambda_min=400.0, lambda_max=1400.0)))
    assert set(table) == {"spectrum_id", "lambda_min", "lambda_max", "auc", "status"}
    assert table["status"] == ["ok", "ok"]
    # Analytic Gaussian area = amplitude * sigma * sqrt(2*pi).
    expected = 10.0 * 25.0 * float(np.sqrt(2.0 * np.pi))
    assert table["auc"][0] == pytest.approx(expected, abs=1.0)


def test_auc_empty_range_reports_status(spectra: Collection) -> None:
    table = _feature_table(CalculateAUC().run({"spectra": spectra}, _config(lambda_min=2000.0, lambda_max=3000.0)))
    assert table["auc"] == [None, None]
    assert table["status"] == ["range_has_fewer_than_two_points"] * 2


def test_centroid_symmetric_peak(spectra: Collection) -> None:
    table = _feature_table(CalculateCentroid().run({"spectra": spectra}, _config(lambda_min=800.0, lambda_max=1000.0)))
    assert set(table) == {"spectrum_id", "lambda_min", "lambda_max", "centroid_lambda", "status"}
    assert table["status"][0] == "ok"
    assert table["centroid_lambda"][0] == pytest.approx(900.0, abs=1.0)


def test_centroid_reports_status_on_zero_intensity() -> None:
    lam = np.linspace(800.0, 1000.0, 64)
    flat = support.build_spectrum(lam, np.zeros_like(lam), spectrum_id="Z")
    table = _feature_table(
        CalculateCentroid().run(
            {"spectra": support.spectra_collection([flat])},
            _config(lambda_min=800.0, lambda_max=1000.0),
        )
    )
    assert table["centroid_lambda"] == [None]
    assert table["status"] == ["zero_intensity_denominator"]


def test_ratio_peak_to_peak() -> None:
    lam = np.linspace(400.0, 1400.0, 201)
    double = support.build_spectrum(
        lam,
        _gaussian(lam, 5.0, 700.0, 40.0) + _gaussian(lam, 8.0, 1100.0, 20.0),
        spectrum_id="B",
    )
    table = _feature_table(
        CalculateRatio().run(
            {"spectra": support.spectra_collection([double])},
            _config(numerator_peak={"coordinate": 1100.0}, denominator_peak={"coordinate": 700.0}),
        )
    )
    assert set(table) == {
        "spectrum_id",
        "numerator_coordinate",
        "numerator_intensity",
        "denominator_coordinate",
        "denominator_intensity",
        "ratio",
        "status",
    }
    assert table["status"] == ["ok"]
    assert table["ratio"][0] == pytest.approx(8.0 / 5.0, abs=0.05)


def test_ratio_status_on_zero_denominator() -> None:
    lam = np.linspace(400.0, 1400.0, 201)
    intensity = np.zeros_like(lam)
    intensity[int(np.argmin(np.abs(lam - 900.0)))] = 10.0
    spectrum = support.build_spectrum(lam, intensity, spectrum_id="A")
    table = _feature_table(
        CalculateRatio().run(
            {"spectra": support.spectra_collection([spectrum])},
            _config(numerator_peak={"coordinate": 900.0}, denominator_peak={"coordinate": 700.0}),
        )
    )
    assert table["ratio"] == [None]
    assert table["status"] == ["denominator_zero_or_unusable"]


def test_find_peaks_returns_coordinates() -> None:
    pytest.importorskip("scipy")
    lam = np.linspace(400.0, 1400.0, 201)
    double = support.build_spectrum(
        lam,
        _gaussian(lam, 5.0, 700.0, 40.0) + _gaussian(lam, 8.0, 1100.0, 20.0),
        spectrum_id="B",
    )
    table = _feature_table(FindPeaks().run({"spectra": support.spectra_collection([double])}, _config(prominence=1.0)))
    assert set(table) == {"spectrum_id", "peak_coordinate", "peak_intensity", "prominence", "status"}
    assert table["status"] == ["ok"]
    assert table["peak_coordinate"][0] == pytest.approx(1100.0, abs=10.0)


def test_find_peaks_reports_no_peaks() -> None:
    pytest.importorskip("scipy")
    lam = np.linspace(400.0, 1400.0, 64)
    flat = support.build_spectrum(lam, np.zeros_like(lam), spectrum_id="Z")
    table = _feature_table(FindPeaks().run({"spectra": support.spectra_collection([flat])}, _config(prominence=1.0)))
    assert table["peak_coordinate"] == [None]
    assert table["status"] == ["no_peaks_found"]


# ---------------------------------------------------------------------------
# Peak fitting
# ---------------------------------------------------------------------------


def test_fit_peak_emits_three_ports(spectra: Collection) -> None:
    pytest.importorskip("scipy")
    outputs = FitPeak().run({"spectra": spectra}, _config(model="gaussian", lambda_min=800.0, lambda_max=1000.0))
    assert set(outputs) == {"fit_curves", "residuals", "parameters"}
    curves = list(outputs["fit_curves"])
    residuals = list(outputs["residuals"])
    params = list(outputs["parameters"])
    assert len(curves) == 2
    assert len(residuals) == 2
    assert len(params) == 1
    assert all(isinstance(curve, Spectrum) for curve in curves)
    assert isinstance(params[0], DataFrame)
    # spectrum_id preserved across the fit transform (FR-117/FR-118).
    assert [curve.spectrum_id for curve in curves] == ["A", "B"]


def test_fit_peak_parameters_port_name(spectra: Collection) -> None:
    pytest.importorskip("scipy")
    outputs = FitPeak().run({"spectra": spectra}, _config(model="gaussian"))
    # FR-120: tabular port is 'parameters', never 'fit_diagnostics'.
    assert "fit_diagnostics" not in outputs
    table = support.dataframe_arrow(next(iter(outputs["parameters"]))).to_pydict()
    assert table["spectrum_id"] == ["A", "B"]
    assert table["model"] == ["gaussian", "gaussian"]
    assert table["status"][0] == "ok"
    assert table["center"][0] == pytest.approx(900.0, abs=1.0)
    assert table["amplitude"][0] == pytest.approx(10.0, abs=0.5)
    # FWHM = sigma * 2*sqrt(2*ln2).
    assert table["fwhm"][0] == pytest.approx(25.0 * 2.35482, abs=1.0)


def test_fit_peak_does_not_modify_input(spectra: Collection) -> None:
    pytest.importorskip("scipy")
    original = [support.spectrum_arrays(s)[1].copy() for s in spectra]
    outputs = FitPeak().run({"spectra": spectra}, _config(model="gaussian"))
    after = [support.spectrum_arrays(s)[1] for s in spectra]
    for before, now in zip(original, after, strict=True):
        np.testing.assert_allclose(before, now)
    # residual == input - fitted on the same grid (FR-118).
    curves = list(outputs["fit_curves"])
    residuals = list(outputs["residuals"])
    for src, curve, residual in zip(spectra, curves, residuals, strict=True):
        _, in_y = support.spectrum_arrays(src)
        _, fit_y = support.spectrum_arrays(curve)
        _, res_y = support.spectrum_arrays(residual)
        np.testing.assert_allclose(res_y, in_y - fit_y, atol=1e-9)


@pytest.mark.parametrize("model", ["gaussian", "lorentzian", "voigt"])
def test_fit_peak_supports_all_models(model: str) -> None:
    pytest.importorskip("scipy")
    lam = np.linspace(400.0, 1400.0, 201)
    spectrum = support.build_spectrum(lam, _gaussian(lam, 10.0, 900.0, 25.0), spectrum_id="A")
    outputs = FitPeak().run(
        {"spectra": support.spectra_collection([spectrum])},
        _config(model=model, lambda_min=820.0, lambda_max=980.0),
    )
    table = support.dataframe_arrow(next(iter(outputs["parameters"]))).to_pydict()
    assert table["model"] == [model]
    assert table["status"][0] == "ok"
    assert table["center"][0] == pytest.approx(900.0, abs=2.0)


def test_fit_peak_failure_records_status(spectra: Collection) -> None:
    pytest.importorskip("scipy")
    # A 2-point fit window has too few points; status is non-success and the
    # fitted parameters stay None (FR-119, no misleading values).
    outputs = FitPeak().run({"spectra": spectra}, _config(model="gaussian", lambda_min=899.0, lambda_max=901.0))
    table = support.dataframe_arrow(next(iter(outputs["parameters"]))).to_pydict()
    assert table["status"][0] == "fit_range_too_few_points"
    assert table["center"][0] is None
    assert table["amplitude"][0] is None
    assert table["fwhm"][0] is None


def test_fit_peak_rejects_unknown_model(spectra: Collection) -> None:
    pytest.importorskip("scipy")
    with pytest.raises(ValueError, match="model must be one of"):
        FitPeak().run({"spectra": spectra}, _config(model="cauchy"))
