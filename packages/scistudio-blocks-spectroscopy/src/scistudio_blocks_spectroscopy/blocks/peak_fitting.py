"""Peak fitting blocks for SciStudio spectroscopy spectra."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy.types import Spectrum

from ._spectra import (
    config_range,
    make_dataframe,
    make_spectrum_like,
    spectrum_arrays,
    spectrum_id,
    unpack_spectra_collection,
    window_with_interpolated_bounds,
)

_MODELS = {"gaussian", "lorentzian", "voigt"}


@dataclass(frozen=True)
class _FitResult:
    status: str
    center: float | None
    amplitude: float | None
    sigma: float | None
    gamma: float | None
    eta: float | None
    baseline: float | None
    fwhm: float | None
    area: float | None
    rmse: float | None
    r2: float | None
    fitted: np.ndarray


class FitPeak(ProcessBlock):
    """Fit Gaussian, Lorentzian, or Voigt peak models to spectra."""

    type_name: ClassVar[str] = "spectroscopy.fit_peak"
    name: ClassVar[str] = "Fit Peak"
    algorithm: ClassVar[str] = "fit_peak"
    description: ClassVar[str] = "Fit a configured peak model and emit fitted curves, residuals, and parameters."
    subcategory: ClassVar[str] = "spectroscopy-fit"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="spectra", accepted_types=[Spectrum], is_collection=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="fit_curves", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="residuals", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="parameters", accepted_types=[DataFrame]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "lambda_min": {"type": "number"},
            "lambda_max": {"type": "number"},
            "model": {"type": "string", "enum": sorted(_MODELS), "default": "gaussian"},
        },
        "required": ["lambda_min", "lambda_max", "model"],
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        model = _model_name(config)
        lambda_min, lambda_max = config_range(config)
        fit_curves: list[Spectrum] = []
        residuals: list[Spectrum] = []
        rows: list[dict[str, Any]] = []

        for spectrum in unpack_spectra_collection(inputs["spectra"]):
            arrays = spectrum_arrays(spectrum)
            result = _fit_peak(arrays.lambdas, arrays.intensities, lambda_min, lambda_max, model)
            fit_curves.append(make_spectrum_like(spectrum, arrays.lambdas.tolist(), result.fitted.tolist()))
            residuals.append(
                make_spectrum_like(spectrum, arrays.lambdas.tolist(), (arrays.intensities - result.fitted).tolist())
            )
            rows.append(
                {
                    "spectrum_id": spectrum_id(spectrum),
                    "model": model,
                    "status": result.status,
                    "center": result.center,
                    "amplitude": result.amplitude,
                    "sigma": result.sigma,
                    "gamma": result.gamma,
                    "eta": result.eta,
                    "baseline": result.baseline,
                    "fwhm": result.fwhm,
                    "area": result.area,
                    "rmse": result.rmse,
                    "r2": result.r2,
                }
            )

        parameter_columns = [
            "spectrum_id",
            "model",
            "status",
            "center",
            "amplitude",
            "sigma",
            "gamma",
            "eta",
            "baseline",
            "fwhm",
            "area",
            "rmse",
            "r2",
        ]
        return {
            "fit_curves": Collection(cast(list[DataObject], fit_curves), item_type=Spectrum),
            "residuals": Collection(cast(list[DataObject], residuals), item_type=Spectrum),
            "parameters": Collection([make_dataframe(rows, parameter_columns)], item_type=DataFrame),
        }


def _model_name(config: BlockConfig) -> str:
    model = str(config.get("model", "gaussian")).lower()
    if model not in _MODELS:
        raise ValueError("model must be one of: " + ", ".join(sorted(_MODELS)))
    return model


def _fit_peak(
    lambdas: np.ndarray,
    intensities: np.ndarray,
    lambda_min: float,
    lambda_max: float,
    model: str,
) -> _FitResult:
    window = window_with_interpolated_bounds(lambdas, intensities, lambda_min, lambda_max)
    if window.lambdas.size < 4:
        return _failed_fit("insufficient_points", lambdas)
    if np.allclose(window.intensities, window.intensities[0]):
        return _failed_fit("flat_spectrum", lambdas)

    guess = _initial_guess(window.lambdas, window.intensities, model)
    try:
        params = _curve_fit(window.lambdas, window.intensities, model, guess)
        fitted_full = _model_function(model)(lambdas, *params)
        fitted_window = _model_function(model)(window.lambdas, *params)
        return _successful_fit(model, params, fitted_full, fitted_window, window.intensities)
    except Exception:
        params = guess
        fitted_full = _model_function(model)(lambdas, *params)
        fitted_window = _model_function(model)(window.lambdas, *params)
        result = _successful_fit(model, params, fitted_full, fitted_window, window.intensities)
        return _FitResult(
            status="estimated",
            center=result.center,
            amplitude=result.amplitude,
            sigma=result.sigma,
            gamma=result.gamma,
            eta=result.eta,
            baseline=result.baseline,
            fwhm=result.fwhm,
            area=result.area,
            rmse=result.rmse,
            r2=result.r2,
            fitted=result.fitted,
        )


def _curve_fit(x: np.ndarray, y: np.ndarray, model: str, guess: tuple[float, ...]) -> tuple[float, ...]:
    try:
        from scipy.optimize import curve_fit
    except Exception as exc:  # pragma: no cover - exercised only without scipy
        raise RuntimeError("scipy.optimize is unavailable") from exc

    lower, upper = _bounds(model, x)
    params, _cov = curve_fit(
        _model_function(model),
        x,
        y,
        p0=guess,
        bounds=(lower, upper),
        maxfev=20000,
    )
    return tuple(float(value) for value in params)


def _initial_guess(x: np.ndarray, y: np.ndarray, model: str) -> tuple[float, ...]:
    baseline = float(np.nanmin(y))
    peak_idx = int(np.nanargmax(y))
    center = float(x[peak_idx])
    amplitude = max(float(y[peak_idx] - baseline), 1e-12)
    span = max(float(np.nanmax(x) - np.nanmin(x)), 1e-12)
    width = max(span / 8.0, 1e-12)
    if model == "gaussian":
        return baseline, amplitude, center, width
    if model == "lorentzian":
        return baseline, amplitude, center, width
    return baseline, amplitude, center, width, width, 0.5


def _bounds(model: str, x: np.ndarray) -> tuple[tuple[float, ...], tuple[float, ...]]:
    xmin = float(np.nanmin(x))
    xmax = float(np.nanmax(x))
    span = max(xmax - xmin, 1e-12)
    lower_common = (-np.inf, 0.0, xmin, 1e-12)
    upper_common = (np.inf, np.inf, xmax, span * 10.0)
    if model in {"gaussian", "lorentzian"}:
        return lower_common, upper_common
    return (
        (-np.inf, 0.0, xmin, 1e-12, 1e-12, 0.0),
        (np.inf, np.inf, xmax, span * 10.0, span * 10.0, 1.0),
    )


def _model_function(model: str) -> Callable[..., np.ndarray]:
    if model == "gaussian":
        return _gaussian
    if model == "lorentzian":
        return _lorentzian
    return _pseudo_voigt


def _gaussian(x: np.ndarray, baseline: float, amplitude: float, center: float, sigma: float) -> np.ndarray:
    sigma = max(float(sigma), 1e-12)
    return baseline + amplitude * np.exp(-0.5 * ((x - center) / sigma) ** 2)


def _lorentzian(x: np.ndarray, baseline: float, amplitude: float, center: float, gamma: float) -> np.ndarray:
    gamma = max(float(gamma), 1e-12)
    return baseline + amplitude * (gamma**2 / ((x - center) ** 2 + gamma**2))


def _pseudo_voigt(
    x: np.ndarray,
    baseline: float,
    amplitude: float,
    center: float,
    sigma: float,
    gamma: float,
    eta: float,
) -> np.ndarray:
    eta = float(np.clip(eta, 0.0, 1.0))
    return baseline + amplitude * (
        eta * _lorentzian(x, 0.0, 1.0, center, gamma) + (1.0 - eta) * _gaussian(x, 0.0, 1.0, center, sigma)
    )


def _successful_fit(
    model: str,
    params: tuple[float, ...],
    fitted_full: np.ndarray,
    fitted_window: np.ndarray,
    observed_window: np.ndarray,
) -> _FitResult:
    baseline = float(params[0])
    center = float(params[2])
    if model == "gaussian":
        amplitude = float(params[1])
        sigma = abs(float(params[3]))
        gamma = None
        eta = None
        fwhm = 2.0 * math.sqrt(2.0 * math.log(2.0)) * sigma
        area = amplitude * sigma * math.sqrt(2.0 * math.pi)
    elif model == "lorentzian":
        amplitude = float(params[1])
        sigma = None
        gamma = abs(float(params[3]))
        eta = None
        fwhm = 2.0 * gamma
        area = math.pi * amplitude * gamma
    else:
        amplitude = float(params[1])
        sigma = abs(float(params[3]))
        gamma = abs(float(params[4]))
        eta = float(np.clip(params[5], 0.0, 1.0))
        lorentz_fwhm = 2.0 * gamma
        gauss_fwhm = 2.0 * math.sqrt(2.0 * math.log(2.0)) * sigma
        fwhm = 0.5346 * lorentz_fwhm + math.sqrt(0.2166 * lorentz_fwhm**2 + gauss_fwhm**2)
        area = amplitude * (eta * math.pi * gamma + (1.0 - eta) * sigma * math.sqrt(2.0 * math.pi))

    residual = observed_window - fitted_window
    rmse = float(np.sqrt(np.mean(residual**2)))
    total = float(np.sum((observed_window - np.mean(observed_window)) ** 2))
    r2 = None if np.isclose(total, 0.0) else float(1.0 - np.sum(residual**2) / total)
    return _FitResult(
        status="success",
        center=center,
        amplitude=amplitude,
        sigma=sigma,
        gamma=gamma,
        eta=eta,
        baseline=baseline,
        fwhm=float(fwhm),
        area=float(area),
        rmse=rmse,
        r2=r2,
        fitted=fitted_full.astype(float),
    )


def _failed_fit(status: str, lambdas: np.ndarray) -> _FitResult:
    return _FitResult(
        status=status,
        center=None,
        amplitude=None,
        sigma=None,
        gamma=None,
        eta=None,
        baseline=None,
        fwhm=None,
        area=None,
        rmse=None,
        r2=None,
        fitted=np.full_like(lambdas, np.nan, dtype=float),
    )


__all__ = ["FitPeak"]
