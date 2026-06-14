from __future__ import annotations

import math

import numpy as np
import pytest
from _test_support import install_type_shim

install_type_shim()

from _test_support import make_spectrum, spectrum_collection, spectrum_xy, table_rows  # noqa: E402
from scistudio_blocks_spectroscopy.blocks.peak_fitting import FitPeak  # noqa: E402

from scistudio.core.types.collection import Collection  # noqa: E402
from scistudio.core.types.dataframe import DataFrame  # noqa: E402
from scistudio.testing import BlockTestHarness  # noqa: E402


def test_fit_peak_contract_and_output_ports() -> None:
    errors = BlockTestHarness(FitPeak).validate_block()
    assert not errors, errors
    assert [port.name for port in FitPeak.output_ports] == ["fit_curves", "residuals", "parameters"]
    assert "fit_diagnostics" not in {port.name for port in FitPeak.output_ports}


def test_fit_peak_gaussian_outputs_curves_residuals_and_parameters() -> None:
    x = np.linspace(0.0, 10.0, 101)
    y = 1.0 + 5.0 * np.exp(-0.5 * ((x - 5.0) / 0.8) ** 2)
    spectrum = make_spectrum("gauss", x, y)
    block = FitPeak(config={"params": {"model": "gaussian", "lambda_min": 2.0, "lambda_max": 8.0}})

    result = block.run({"spectra": spectrum_collection(spectrum)}, block.config)

    assert set(result) == {"fit_curves", "residuals", "parameters"}
    assert isinstance(result["fit_curves"], Collection)
    assert isinstance(result["residuals"], Collection)
    assert result["parameters"].item_type is DataFrame

    row = table_rows(result["parameters"])[0]
    assert row["spectrum_id"] == "gauss"
    assert row["model"] == "gaussian"
    assert row["status"] == "success"
    assert math.isclose(row["center"], 5.0, abs_tol=0.05)
    assert math.isclose(row["fwhm"], 2.0 * math.sqrt(2.0 * math.log(2.0)) * 0.8, rel_tol=0.08)
    assert row["rmse"] < 1e-4

    fit_x, fit_y = spectrum_xy(result["fit_curves"][0])
    residual_x, residual_y = spectrum_xy(result["residuals"][0])
    np.testing.assert_allclose(fit_x, x)
    np.testing.assert_allclose(residual_x, x)
    np.testing.assert_allclose(y - fit_y, residual_y, atol=1e-8)


def test_fit_peak_supports_all_accepted_models() -> None:
    x = np.linspace(0.0, 10.0, 81)
    y = 0.5 + 4.0 * np.exp(-0.5 * ((x - 4.0) / 0.7) ** 2)

    for model in ("gaussian", "lorentzian", "voigt"):
        spectrum = make_spectrum(model, x, y)
        block = FitPeak(config={"params": {"model": model, "lambda_min": 1.0, "lambda_max": 7.0}})

        rows = table_rows(block.run({"spectra": spectrum_collection(spectrum)}, block.config)["parameters"])

        assert rows[0]["model"] == model
        assert rows[0]["status"] in {"success", "estimated"}
        assert rows[0]["center"] is not None
        assert rows[0]["fwhm"] is not None
        assert rows[0]["area"] is not None


def test_fit_peak_rejects_unaccepted_model() -> None:
    spectrum = make_spectrum("s1", [0, 1, 2, 3], [0, 1, 0, 0])
    block = FitPeak(config={"params": {"model": "exponential", "lambda_min": 0.0, "lambda_max": 3.0}})

    with pytest.raises(ValueError, match="model must be one of"):
        block.run({"spectra": spectrum_collection(spectrum)}, block.config)


def test_fit_peak_reports_flat_spectrum_without_misleading_parameters() -> None:
    spectrum = make_spectrum("flat", [0, 1, 2, 3, 4], [2, 2, 2, 2, 2])
    block = FitPeak(config={"params": {"model": "gaussian", "lambda_min": 0.0, "lambda_max": 4.0}})

    result = block.run({"spectra": spectrum_collection(spectrum)}, block.config)
    rows = table_rows(result["parameters"])
    _fit_x, fit_y = spectrum_xy(result["fit_curves"][0])

    assert rows[0]["status"] == "flat_spectrum"
    assert rows[0]["center"] is None
    assert np.isnan(fit_y).all()
