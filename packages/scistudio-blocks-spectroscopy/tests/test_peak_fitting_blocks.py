"""Peak fitting block contract tests (SC-039..SC-042).

- SC-039: the peak fitting group is exactly ``FitPeak``.
- SC-040: ``FitPeak`` supports exactly gaussian / lorentzian / voigt.
- SC-041: ``FitPeak`` emits ``fit_curves``, ``residuals``, and ``parameters``
  and does NOT expose a ``fit_diagnostics`` output port.
- SC-042: ``FitPeak.parameters`` includes center, amplitude, width params, FWHM,
  area, status, and fit-quality fields.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks import peak_fitting
from scistudio_blocks_spectroscopy.blocks.peak_fitting import FitPeak
from scistudio_blocks_spectroscopy.types import Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.testing import BlockTestHarness


def _config(**params: Any) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _gaussian_spectrum(sid: str, *, center: float = 50.0, sigma: float = 5.0) -> Spectrum:
    lam = np.linspace(0.0, 100.0, 201)
    inten = 4.0 * np.exp(-((lam - center) ** 2) / (2 * sigma**2)) + 0.2
    meta = Spectrum.Meta(
        lambda_unit="cm-1", intensity_unit="au", lambda_kind="raman_shift", modality="raman", spectrum_id=sid
    )
    return _support.build_spectrum(lam, inten, meta=meta)


def _params_table(model: str, spectra: list[Spectrum]) -> Any:
    out = FitPeak().run({"spectra": _support.spectra_collection(spectra)}, _config(model=model))
    return out, _support.dataframe_arrow(next(iter(out["parameters"])))


# ---------------------------------------------------------------------------
# SC-039: roster
# ---------------------------------------------------------------------------


def test_peak_fitting_group_is_exactly_fitpeak() -> None:
    assert [b.__name__ for b in peak_fitting.BLOCKS] == ["FitPeak"]


def test_fitpeak_passes_harness() -> None:
    assert not BlockTestHarness(FitPeak).validate_block()


# ---------------------------------------------------------------------------
# SC-040: model enum
# ---------------------------------------------------------------------------


def test_fitpeak_models_closed_set() -> None:
    enum = set(FitPeak.config_schema["properties"]["model"]["enum"])
    assert enum == {"gaussian", "lorentzian", "voigt"}


# ---------------------------------------------------------------------------
# SC-041: output ports — fit_curves / residuals / parameters; NOT fit_diagnostics
# ---------------------------------------------------------------------------


def test_fitpeak_declares_correct_output_ports() -> None:
    names = [p.name for p in FitPeak.output_ports]
    assert names == ["fit_curves", "residuals", "parameters"]
    assert "fit_diagnostics" not in names


def test_fitpeak_run_emits_correct_ports() -> None:
    pytest.importorskip("scipy")
    out, _ = _params_table("gaussian", [_gaussian_spectrum("p1")])
    assert set(out.keys()) == {"fit_curves", "residuals", "parameters"}
    assert "fit_diagnostics" not in out
    assert len(list(out["fit_curves"])) == 1
    assert len(list(out["residuals"])) == 1


# ---------------------------------------------------------------------------
# SC-042: parameters schema
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model", ["gaussian", "lorentzian", "voigt"])
def test_parameters_schema_columns(model: str) -> None:
    pytest.importorskip("scipy")
    _, table = _params_table(model, [_gaussian_spectrum("p1")])
    required = {"spectrum_id", "model", "status", "center", "amplitude", "fwhm", "area"}
    assert required.issubset(table.column_names)
    # width parameters (sigma / gamma) are present for the relevant models.
    assert "sigma" in table.column_names or "gamma" in table.column_names
    # fit-quality field present.
    assert "rmse" in table.column_names


def test_parameters_one_row_per_spectrum_in_order() -> None:
    pytest.importorskip("scipy")
    spectra = [_gaussian_spectrum("p1", center=40.0), _gaussian_spectrum("p2", center=60.0)]
    _, table = _params_table("gaussian", spectra)
    assert table.column("spectrum_id").to_pylist() == ["p1", "p2"]


def test_gaussian_fit_recovers_center_and_fwhm() -> None:
    pytest.importorskip("scipy")
    _, table = _params_table("gaussian", [_gaussian_spectrum("p1", center=50.0, sigma=5.0)])
    status = table.column("status").to_pylist()[0]
    assert status == "ok"
    center = table.column("center").to_pylist()[0]
    fwhm = table.column("fwhm").to_pylist()[0]
    # The fitted center recovers the true peak location.
    assert center == pytest.approx(50.0, abs=0.5)
    # FWHM is a finite positive number in the neighbourhood of the analytic
    # Gaussian FWHM (sigma * 2*sqrt(2*ln2) ~= 11.77 for sigma=5); the exact
    # value depends on the curve_fit result on discrete+offset data.
    assert fwhm is not None and np.isfinite(fwhm)
    assert fwhm == pytest.approx(5.0 * 2.3548, rel=0.15)
