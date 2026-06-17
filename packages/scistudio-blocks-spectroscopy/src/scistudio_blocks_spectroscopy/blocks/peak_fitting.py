"""Spectroscopy peak fitting block (FR-113..FR-120).

One block, :class:`FitPeak`. It fits a Gaussian/Lorentzian/Voigt model without
modifying the input spectra and emits fitted curves, residual spectra, and a
``parameters`` feature table. Per FR-120 the tabular output port is named
``parameters`` (NOT ``fit_diagnostics``).

A fit that fails to converge does not crash the block: the curve/residual are
emitted on the input grid (zeroed curve, raw intensity residual) and the
``parameters`` row records a non-success status with no misleading fitted
values (FR-3 acceptance, FR-119).

scipy (``scipy.optimize.curve_fit``, ``scipy.special.wofz``) is lazy-imported
inside the run body only.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.types import Spectrum

_STATUS_OK = "ok"
_MODELS = ("gaussian", "lorentzian", "voigt")

#: numpy trapezoidal integrator: ``np.trapezoid`` (numpy>=2) with a
#: ``np.trapz`` fallback for older numpy (FR-119 area).
_trapezoid: Callable[..., Any] = getattr(np, "trapezoid", None) or np.trapz  # type: ignore[attr-defined]

#: Conversion factor: a Gaussian's sigma -> FWHM (2*sqrt(2*ln2)).
_GAUSS_SIGMA_TO_FWHM = 2.0 * math.sqrt(2.0 * math.log(2.0))

_PARAM_COLUMNS = [
    "spectrum_id",
    "model",
    "status",
    "center",
    "amplitude",
    "sigma",
    "gamma",
    "fwhm",
    "area",
    "rmse",
]


def _gaussian(lam: np.ndarray, amplitude: float, center: float, sigma: float) -> np.ndarray:
    return amplitude * np.exp(-((lam - center) ** 2) / (2.0 * sigma**2))


def _lorentzian(lam: np.ndarray, amplitude: float, center: float, gamma: float) -> np.ndarray:
    return amplitude * (gamma**2 / ((lam - center) ** 2 + gamma**2))


def _voigt(lam: np.ndarray, amplitude: float, center: float, sigma: float, gamma: float) -> np.ndarray:
    from scipy.special import wofz

    sigma = max(abs(sigma), 1e-12)
    z = ((lam - center) + 1j * abs(gamma)) / (sigma * math.sqrt(2.0))
    profile = np.real(wofz(z)) / (sigma * math.sqrt(2.0 * math.pi))
    norm = np.real(wofz(1j * abs(gamma) / (sigma * math.sqrt(2.0)))) / (sigma * math.sqrt(2.0 * math.pi))
    if norm == 0.0 or not np.isfinite(norm):
        return np.zeros_like(lam)
    return np.asarray(amplitude * profile / norm, dtype=np.float64)


def _voigt_fwhm(sigma: float, gamma: float) -> float:
    """Approximate Voigt FWHM from the Gaussian/Lorentzian widths (Olivero 1977)."""
    fwhm_g = abs(sigma) * _GAUSS_SIGMA_TO_FWHM
    fwhm_l = 2.0 * abs(gamma)
    return 0.5346 * fwhm_l + math.sqrt(0.2166 * fwhm_l**2 + fwhm_g**2)


def _initial_guess(lam: np.ndarray, inten: np.ndarray, model: str) -> list[float]:
    amplitude = float(np.max(inten) - np.min(inten)) or 1.0
    center = float(lam[int(np.argmax(inten))])
    span = float(lam[-1] - lam[0]) if lam.size > 1 else 1.0
    width = abs(span) / 6.0 or 1.0
    if model == "gaussian":
        return [amplitude, center, width]
    if model == "lorentzian":
        return [amplitude, center, width]
    return [amplitude, center, width, width]  # voigt: sigma, gamma


def _empty_param_row(spectrum_id: str, model: str, status: str) -> dict[str, Any]:
    return {
        "spectrum_id": spectrum_id,
        "model": model,
        "status": status,
        "center": None,
        "amplitude": None,
        "sigma": None,
        "gamma": None,
        "fwhm": None,
        "area": None,
        "rmse": None,
    }


class FitPeak(ProcessBlock):
    """Fit a peak model and emit fitted curves, residuals, and parameters."""

    type_name: ClassVar[str] = "spectroscopy.fit_peak"
    name: ClassVar[str] = "Fit Peak"
    description: ClassVar[str] = "Fit a Gaussian/Lorentzian/Voigt peak; emit fitted curves, residuals, parameters."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "peak_fitting"
    algorithm: ClassVar[str] = "fit_peak"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="spectra",
            accepted_types=[Spectrum],
            is_collection=True,
            required=True,
            description="Input spectra to fit (not modified).",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="fit_curves", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="residuals", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="parameters", accepted_types=[DataFrame]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "model": {
                "type": "string",
                "enum": ["gaussian", "lorentzian", "voigt"],
                "default": "gaussian",
                "title": "Peak model",
            },
            "lambda_min": {"type": "number", "title": "Fit range min"},
            "lambda_max": {"type": "number", "title": "Fit range max"},
        },
        "required": ["model"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Fit a peak model per spectrum (FR-113..FR-120).

        Implementation plan:
          1. model = config.get('model','gaussian'); validate in enum.
          2. Within [lambda_min, lambda_max], lazy scipy.optimize.curve_fit a
             gaussian/lorentzian/voigt (voigt via scipy.special.wofz) model.
          3. fit_curves = fitted intensity on the input grid; residuals =
             input_intensity - fitted_intensity (FR-117, FR-118); both emitted
             via _support.derive_spectrum preserving spectrum_id.
          4. parameters DataFrame: one row per attempted fit with spectrum_id,
             model, status, center, amplitude, width params, FWHM, area, RMSE
             (FR-119). Port is named 'parameters', NOT 'fit_diagnostics' (FR-120).
          5. Return {'fit_curves':..., 'residuals':...,
             'parameters': _support.dataframe_collection(df)}.
        Edge cases: fit failure -> non-success status, no misleading params
          (FR-3 acceptance); range with too few points; flat input.
        Test plan: test_peak_fitting_blocks.py::test_fit_peak_emits_three_ports,
          ::test_fit_peak_parameters_port_name,
          ::test_fit_peak_failure_records_status.
        """
        from scipy.optimize import curve_fit  # lazy (FR-115) — keeps import scipy-free

        spectra = _support.coerce_spectra(inputs.get("spectra"), block=self.name)
        model = str(config.get("model", "gaussian"))
        if model not in _MODELS:
            raise ValueError(f"{self.name}: model must be one of {list(_MODELS)}, got {model!r}")
        lambda_min = config.get("lambda_min")
        lambda_max = config.get("lambda_max")
        lo = None if lambda_min is None else float(lambda_min)
        hi = None if lambda_max is None else float(lambda_max)

        fit_curves: list[Spectrum] = []
        residuals: list[Spectrum] = []
        param_rows: list[dict[str, Any]] = []

        for spectrum in spectra:
            spectrum_id = spectrum.spectrum_id or _support.new_spectrum_id()
            lam, inten = _support.spectrum_arrays(spectrum)
            fit_mask = np.ones(lam.shape, dtype=bool)
            if lo is not None:
                fit_mask &= lam >= lo
            if hi is not None:
                fit_mask &= lam <= hi
            fit_lam = lam[fit_mask]
            fit_inten = inten[fit_mask]

            fitted_full, row = self._fit_one(model, spectrum_id, lam, inten, fit_lam, fit_inten, curve_fit)
            residual_full = inten - fitted_full

            fit_curves.append(_support.derive_spectrum(spectrum, intensity_values=fitted_full))
            residuals.append(_support.derive_spectrum(spectrum, intensity_values=residual_full))
            param_rows.append(row)

        frame = _support.dataframe_from_rows(param_rows, columns=_PARAM_COLUMNS)
        return {
            "fit_curves": _support.spectra_collection(fit_curves),
            "residuals": _support.spectra_collection(residuals),
            "parameters": _support.dataframe_collection(frame),
        }

    def _fit_one(
        self,
        model: str,
        spectrum_id: str,
        lam: np.ndarray,
        inten: np.ndarray,
        fit_lam: np.ndarray,
        fit_inten: np.ndarray,
        curve_fit: Any,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """Fit one spectrum; return ``(fitted_curve_on_full_grid, param_row)``.

        On any failure the fitted curve is all-zeros and the row carries a
        non-success status with no misleading fitted parameters (FR-3, FR-119).
        """
        zeros = np.zeros_like(lam)
        if fit_lam.size < 3:
            return zeros, _empty_param_row(spectrum_id, model, "fit_range_too_few_points")

        models: dict[str, Callable[..., np.ndarray]] = {
            "gaussian": _gaussian,
            "lorentzian": _lorentzian,
            "voigt": _voigt,
        }
        func = models[model]
        p0 = _initial_guess(fit_lam, fit_inten, model)
        try:
            popt, _ = curve_fit(func, fit_lam, fit_inten, p0=p0, maxfev=10000)
        except (RuntimeError, ValueError, TypeError):
            return zeros, _empty_param_row(spectrum_id, model, "fit_failed")

        if not np.all(np.isfinite(popt)):
            return zeros, _empty_param_row(spectrum_id, model, "fit_non_finite_parameters")

        fitted_full = np.asarray(func(lam, *popt), dtype=np.float64)
        if not np.all(np.isfinite(fitted_full)):
            return zeros, _empty_param_row(spectrum_id, model, "fit_non_finite_curve")

        fitted_fit = np.asarray(func(fit_lam, *popt), dtype=np.float64)
        rmse = float(np.sqrt(np.mean((fit_inten - fitted_fit) ** 2)))
        row = self._param_row(model, spectrum_id, popt, fit_lam, fitted_fit, rmse)
        return fitted_full, row

    @staticmethod
    def _param_row(
        model: str,
        spectrum_id: str,
        popt: np.ndarray,
        fit_lam: np.ndarray,
        fitted_fit: np.ndarray,
        rmse: float,
    ) -> dict[str, Any]:
        amplitude = float(popt[0])
        center = float(popt[1])
        area = float(_trapezoid(fitted_fit, fit_lam))
        if model == "gaussian":
            sigma = abs(float(popt[2]))
            return {
                "spectrum_id": spectrum_id,
                "model": model,
                "status": _STATUS_OK,
                "center": center,
                "amplitude": amplitude,
                "sigma": sigma,
                "gamma": None,
                "fwhm": sigma * _GAUSS_SIGMA_TO_FWHM,
                "area": area,
                "rmse": rmse,
            }
        if model == "lorentzian":
            gamma = abs(float(popt[2]))
            return {
                "spectrum_id": spectrum_id,
                "model": model,
                "status": _STATUS_OK,
                "center": center,
                "amplitude": amplitude,
                "sigma": None,
                "gamma": gamma,
                "fwhm": 2.0 * gamma,
                "area": area,
                "rmse": rmse,
            }
        # voigt
        sigma = abs(float(popt[2]))
        gamma = abs(float(popt[3]))
        return {
            "spectrum_id": spectrum_id,
            "model": model,
            "status": _STATUS_OK,
            "center": center,
            "amplitude": amplitude,
            "sigma": sigma,
            "gamma": gamma,
            "fwhm": _voigt_fwhm(sigma, gamma),
            "area": area,
            "rmse": rmse,
        }


BLOCKS: list[type] = [FitPeak]

__all__ = ["BLOCKS", "FitPeak"]
