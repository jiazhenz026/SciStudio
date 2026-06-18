"""Spectroscopy preprocessing blocks (FR-053..FR-081).

Seven blocks that operate on ``Collection[Spectrum]`` (never ``SpectralDataset``,
FR-054) and preserve item count/order/``spectrum_id`` (FR-055). Any block that
fits or estimates a baseline exposes both a fitted-curve output and a
``fit_diagnostics`` table (FR-081).

scipy is lazy-imported inside method bodies only (it is not in the base env and
not imported at module top level).
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.types import Spectrum

_SPECTRA_INPUT = InputPort(
    name="spectra",
    accepted_types=[Spectrum],
    is_collection=True,
    required=True,
    description="Input spectra to preprocess.",
)


# ---------------------------------------------------------------------------
# Shared baseline (Whittaker-smoothing) helpers — lazy scipy callers pass these
# their own sparse modules so scipy stays out of module scope.
# ---------------------------------------------------------------------------


def _whittaker_solver() -> Any:
    """Return ``scipy.sparse.linalg.spsolve`` (lazy import)."""
    from scipy.sparse.linalg import spsolve

    return spsolve


def _second_diff_operator(size: int) -> Any:
    """Return the second-difference sparse matrix ``D`` for a length-``size`` signal."""
    from scipy import sparse

    return sparse.diags([1.0, -2.0, 1.0], [0, -1, -2], shape=(size, size - 2))


def _asls_baseline(y: np.ndarray, lam: float, p: float, max_iter: int) -> tuple[np.ndarray, bool, int]:
    """Asymmetric least squares baseline (Eilers & Boelens).

    Returns ``(baseline, converged, iterations)``.
    """
    from scipy import sparse

    spsolve = _whittaker_solver()
    size = y.shape[0]
    diff = _second_diff_operator(size)
    penalty = lam * (diff @ diff.transpose())
    weights = np.ones(size, dtype=np.float64)
    baseline = np.asarray(y, dtype=np.float64)
    converged = False
    iterations = 0
    for iteration in range(1, max_iter + 1):
        iterations = iteration
        weight_mat = sparse.diags(weights, 0)
        new_baseline = np.asarray(spsolve((weight_mat + penalty).tocsc(), weights * y))
        new_weights = np.where(y > new_baseline, p, 1.0 - p)
        if np.allclose(new_weights, weights):
            baseline = new_baseline
            converged = True
            break
        weights = new_weights
        baseline = new_baseline
    return np.asarray(baseline, dtype=np.float64), converged, iterations


def _arpls_baseline(y: np.ndarray, lam: float, max_iter: int) -> tuple[np.ndarray, bool, int]:
    """Asymmetrically reweighted penalized least squares baseline (Baek et al.).

    Returns ``(baseline, converged, iterations)``.
    """
    from scipy import sparse

    spsolve = _whittaker_solver()
    size = y.shape[0]
    diff = _second_diff_operator(size)
    penalty = lam * (diff @ diff.transpose())
    weights = np.ones(size, dtype=np.float64)
    baseline = np.asarray(y, dtype=np.float64)
    converged = False
    iterations = 0
    for iteration in range(1, max_iter + 1):
        iterations = iteration
        weight_mat = sparse.diags(weights, 0)
        baseline = np.asarray(spsolve((weight_mat + penalty).tocsc(), weights * y))
        residual = y - baseline
        negative = residual[residual < 0]
        mean = float(negative.mean()) if negative.size else 0.0
        std = float(negative.std()) if negative.size else 0.0
        # Logistic reweighting; guard the exponent to avoid overflow.
        denom = std if std > 1e-12 else 1e-12
        exponent = np.clip(2.0 * (residual - (2.0 * std - mean)) / denom, -50.0, 50.0)
        new_weights = 1.0 / (1.0 + np.exp(exponent))
        weight_norm = float(np.linalg.norm(weights))
        norm_ratio = float(np.linalg.norm(weights - new_weights)) / max(weight_norm, 1e-12)
        weights = new_weights
        if norm_ratio < 1e-3:
            converged = True
            break
    return np.asarray(baseline, dtype=np.float64), converged, iterations


def _airpls_baseline(y: np.ndarray, lam: float, max_iter: int) -> tuple[np.ndarray, bool, int]:
    """Adaptive iteratively reweighted penalized least squares baseline (Zhang et al.).

    Returns ``(baseline, converged, iterations)``.
    """
    from scipy import sparse

    spsolve = _whittaker_solver()
    size = y.shape[0]
    diff = _second_diff_operator(size)
    penalty = lam * (diff @ diff.transpose())
    weights = np.ones(size, dtype=np.float64)
    baseline = np.asarray(y, dtype=np.float64)
    converged = False
    iterations = 0
    total_abs = float(np.abs(y).sum()) or 1.0
    for iteration in range(1, max_iter + 1):
        iterations = iteration
        weight_mat = sparse.diags(weights, 0)
        baseline = np.asarray(spsolve((weight_mat + penalty).tocsc(), weights * y))
        residual = y - baseline
        negative_mask = residual < 0
        neg_sum = float(np.abs(residual[negative_mask]).sum())
        if neg_sum < 1e-3 * total_abs:
            converged = True
            break
        new_weights = np.zeros(size, dtype=np.float64)
        denom = neg_sum if neg_sum > 1e-12 else 1e-12
        exponent = np.clip(iteration * np.abs(residual[negative_mask]) / denom, -50.0, 50.0)
        new_weights[negative_mask] = np.exp(exponent)
        weights = new_weights
    return np.asarray(baseline, dtype=np.float64), converged, iterations


# ---------------------------------------------------------------------------
# Peak-model helpers (shared by AlignAndResampleSpectra + SubtractPeakComponent)
# ---------------------------------------------------------------------------


def _gaussian(x: np.ndarray, amplitude: float, center: float, sigma: float) -> np.ndarray:
    sigma = sigma if abs(sigma) > 1e-12 else 1e-12
    return amplitude * np.exp(-0.5 * ((x - center) / sigma) ** 2)


def _lorentzian(x: np.ndarray, amplitude: float, center: float, gamma: float) -> np.ndarray:
    gamma = gamma if abs(gamma) > 1e-12 else 1e-12
    return amplitude * (gamma**2) / ((x - center) ** 2 + gamma**2)


def _voigt(x: np.ndarray, amplitude: float, center: float, sigma: float, gamma: float) -> np.ndarray:
    from scipy.special import voigt_profile

    sigma = abs(sigma) if abs(sigma) > 1e-12 else 1e-12
    gamma = abs(gamma) if abs(gamma) > 1e-12 else 1e-12
    profile = voigt_profile(x - center, sigma, gamma)
    peak = float(voigt_profile(np.array([0.0]), sigma, gamma)[0])
    peak = peak if abs(peak) > 1e-12 else 1e-12
    return np.asarray(amplitude * profile / peak, dtype=np.float64)


def _gaussian_fwhm(sigma: float) -> float:
    return float(2.0 * np.sqrt(2.0 * np.log(2.0)) * abs(sigma))


def _lorentzian_fwhm(gamma: float) -> float:
    return float(2.0 * abs(gamma))


def _voigt_fwhm(sigma: float, gamma: float) -> float:
    # Olivero & Longbothum pseudo-Voigt FWHM approximation.
    fg = _gaussian_fwhm(sigma)
    fl = _lorentzian_fwhm(gamma)
    return float(0.5346 * fl + np.sqrt(0.2166 * fl**2 + fg**2))


def _rmse(observed: np.ndarray, predicted: np.ndarray) -> float:
    diff = np.asarray(observed, dtype=np.float64) - np.asarray(predicted, dtype=np.float64)
    return float(np.sqrt(np.mean(diff**2))) if diff.size else float("nan")


class CropSpectrumRange(ProcessBlock):
    """Crop each spectrum to a ``[lambda_min, lambda_max]`` range (FR-057)."""

    type_name: ClassVar[str] = "spectroscopy.crop_spectrum_range"
    name: ClassVar[str] = "Crop Spectrum Range"
    description: ClassVar[str] = "Drop out-of-range coordinate points without changing kept intensities."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "crop_spectrum_range"

    input_ports: ClassVar[list[InputPort]] = [_SPECTRA_INPUT]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="cropped", accepted_types=[Spectrum], is_collection=True),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "lambda_min": {"type": "number", "title": "Lambda min"},
            "lambda_max": {"type": "number", "title": "Lambda max"},
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Crop spectra to a coordinate range (FR-057).

        Keeps points where ``lambda_min <= lambda <= lambda_max`` (bounds are
        open when omitted); intensities for kept points are unchanged.
        """
        spectra = _support.coerce_spectra(inputs.get("spectra"), block=self.name, port="spectra")
        raw_min = config.get("lambda_min", None)
        raw_max = config.get("lambda_max", None)
        lambda_min = float(raw_min) if raw_min is not None else None
        lambda_max = float(raw_max) if raw_max is not None else None
        if lambda_min is not None and lambda_max is not None and lambda_min > lambda_max:
            raise ValueError(f"{self.name}: lambda_min ({lambda_min}) must not exceed lambda_max ({lambda_max})")

        cropped: list[Spectrum] = []
        for spectrum in spectra:
            lam, inten = _support.spectrum_arrays(spectrum)
            mask = np.ones(lam.shape, dtype=bool)
            if lambda_min is not None:
                mask &= lam >= lambda_min
            if lambda_max is not None:
                mask &= lam <= lambda_max
            new_spectrum = _support.derive_spectrum(
                spectrum,
                lambda_values=lam[mask],
                intensity_values=inten[mask],
            )
            cropped.append(self._auto_flush(new_spectrum))

        return {"cropped": _support.spectra_collection(cropped)}


class ShiftSpectralAxis(ProcessBlock):
    """Shift each spectrum's ``lambda`` axis by a constant (FR-058)."""

    type_name: ClassVar[str] = "spectroscopy.shift_spectral_axis"
    name: ClassVar[str] = "Shift Spectral Axis"
    description: ClassVar[str] = "Shift the lambda axis by a configured amount without changing intensities."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "shift_spectral_axis"

    input_ports: ClassVar[list[InputPort]] = [_SPECTRA_INPUT]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="shifted", accepted_types=[Spectrum], is_collection=True),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"shift": {"type": "number", "default": 0.0, "title": "Axis shift"}},
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Shift the lambda axis by a constant; intensities unchanged (FR-058)."""
        spectra = _support.coerce_spectra(inputs.get("spectra"), block=self.name, port="spectra")
        shift = float(config.get("shift", 0.0))

        shifted: list[Spectrum] = []
        for spectrum in spectra:
            lam, inten = _support.spectrum_arrays(spectrum)
            new_spectrum = _support.derive_spectrum(
                spectrum,
                lambda_values=lam + shift,
                intensity_values=inten,
            )
            shifted.append(self._auto_flush(new_spectrum))

        return {"shifted": _support.spectra_collection(shifted)}


class BaselineCorrection(ProcessBlock):
    """Estimate and subtract a baseline per spectrum (FR-059..FR-064)."""

    type_name: ClassVar[str] = "spectroscopy.baseline_correction"
    name: ClassVar[str] = "Baseline Correction"
    description: ClassVar[str] = "Estimate baselines, subtract them, and report fit diagnostics."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "baseline_correction"

    _METHODS: ClassVar[frozenset[str]] = frozenset({"polynomial", "asls", "arpls", "airpls"})

    input_ports: ClassVar[list[InputPort]] = [_SPECTRA_INPUT]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="corrected", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="baseline", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="fit_diagnostics", accepted_types=[DataFrame]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["polynomial", "asls", "arpls", "airpls"],
                "default": "polynomial",
                "title": "Baseline method",
            },
            "poly_order": {"type": "number", "default": 3, "minimum": 0, "title": "Polynomial order"},
            "lam": {"type": "number", "default": 100000.0, "title": "Smoothness (asls/arpls/airpls)"},
            "p": {"type": "number", "default": 0.01, "title": "Asymmetry (asls)"},
            "max_iter": {"type": "number", "default": 50, "minimum": 1, "title": "Max iterations"},
        },
        "required": ["method"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Baseline-correct each spectrum (FR-059..FR-064).

        ``corrected = intensity - baseline``. Emits ``corrected`` / ``baseline``
        spectra on the input grid plus a per-spectrum ``fit_diagnostics`` table
        (spectrum_id, method, status, parameters, converged, iterations, rmse).
        On a per-spectrum failure the input passes through with a zero baseline
        and a non-success status row (does not crash the whole block).
        """
        spectra = _support.coerce_spectra(inputs.get("spectra"), block=self.name, port="spectra")
        method = str(config.get("method", "polynomial"))
        if method not in self._METHODS:
            raise ValueError(f"{self.name}: unknown method {method!r}; expected one of {sorted(self._METHODS)}")
        poly_order = int(float(config.get("poly_order", 3)))
        lam_smooth = float(config.get("lam", 100000.0))
        asym_p = float(config.get("p", 0.01))
        max_iter = int(float(config.get("max_iter", 50)))

        corrected_list: list[Spectrum] = []
        baseline_list: list[Spectrum] = []
        diag_rows: list[dict[str, Any]] = []

        for spectrum in spectra:
            lam, inten = _support.spectrum_arrays(spectrum)
            parameters: dict[str, Any] = {"method": method}
            converged = False
            iterations = 0
            status = "ok"
            try:
                if inten.shape[0] < 3:
                    raise ValueError("spectrum too short for baseline estimation (need >= 3 points)")
                if method == "polynomial":
                    parameters["poly_order"] = poly_order
                    coeffs = np.polyfit(lam, inten, poly_order)
                    baseline = np.asarray(np.polyval(coeffs, lam), dtype=np.float64)
                    converged = True
                    iterations = 1
                elif method == "asls":
                    parameters.update({"lam": lam_smooth, "p": asym_p, "max_iter": max_iter})
                    baseline, converged, iterations = _asls_baseline(inten, lam_smooth, asym_p, max_iter)
                elif method == "arpls":
                    parameters.update({"lam": lam_smooth, "max_iter": max_iter})
                    baseline, converged, iterations = _arpls_baseline(inten, lam_smooth, max_iter)
                else:  # airpls
                    parameters.update({"lam": lam_smooth, "max_iter": max_iter})
                    baseline, converged, iterations = _airpls_baseline(inten, lam_smooth, max_iter)
                corrected = inten - baseline
            except Exception as exc:
                status = f"error: {type(exc).__name__}: {exc}"
                baseline = np.zeros_like(inten)
                corrected = inten.copy()

            corrected_list.append(self._auto_flush(_support.derive_spectrum(spectrum, intensity_values=corrected)))
            baseline_list.append(self._auto_flush(_support.derive_spectrum(spectrum, intensity_values=baseline)))
            diag_rows.append(
                {
                    "spectrum_id": spectrum.spectrum_id,
                    "method": method,
                    "status": status,
                    "parameters": str(parameters),
                    "converged": bool(converged),
                    "iterations": int(iterations),
                    "rmse": _rmse(inten, baseline),
                }
            )

        diagnostics = _support.dataframe_from_rows(
            diag_rows,
            columns=[
                "spectrum_id",
                "method",
                "status",
                "parameters",
                "converged",
                "iterations",
                "rmse",
            ],
        )
        return {
            "corrected": _support.spectra_collection(corrected_list),
            "baseline": _support.spectra_collection(baseline_list),
            "fit_diagnostics": _support.dataframe_collection(diagnostics),
        }


class SmoothSpectrum(ProcessBlock):
    """Smooth intensities without changing the ``lambda`` grid (FR-065, FR-066)."""

    type_name: ClassVar[str] = "spectroscopy.smooth_spectrum"
    name: ClassVar[str] = "Smooth Spectrum"
    description: ClassVar[str] = "Smooth intensities with a selectable method; lambda grid unchanged."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "smooth_spectrum"

    _METHODS: ClassVar[frozenset[str]] = frozenset({"savitzky_golay", "moving_average", "gaussian", "median"})

    input_ports: ClassVar[list[InputPort]] = [_SPECTRA_INPUT]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="smoothed", accepted_types=[Spectrum], is_collection=True),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["savitzky_golay", "moving_average", "gaussian", "median"],
                "default": "savitzky_golay",
                "title": "Smoothing method",
            },
            "window": {"type": "number", "default": 5, "minimum": 1, "title": "Window length"},
            "polyorder": {"type": "number", "default": 2, "minimum": 0, "title": "Polynomial order (savgol)"},
            "sigma": {"type": "number", "default": 1.0, "minimum": 0.0, "title": "Sigma (gaussian)"},
        },
        "required": ["method"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Smooth intensities, leaving the lambda grid untouched (FR-065, FR-066)."""
        spectra = _support.coerce_spectra(inputs.get("spectra"), block=self.name, port="spectra")
        method = str(config.get("method", "savitzky_golay"))
        if method not in self._METHODS:
            raise ValueError(f"{self.name}: unknown method {method!r}; expected one of {sorted(self._METHODS)}")
        window = int(float(config.get("window", 5)))
        polyorder = int(float(config.get("polyorder", 2)))
        sigma = float(config.get("sigma", 1.0))
        if window < 1:
            raise ValueError(f"{self.name}: window must be >= 1, got {window}")

        smoothed_list: list[Spectrum] = []
        for spectrum in spectra:
            _, inten = _support.spectrum_arrays(spectrum)
            smoothed = self._smooth(inten, method, window, polyorder, sigma)
            smoothed_list.append(self._auto_flush(_support.derive_spectrum(spectrum, intensity_values=smoothed)))

        return {"smoothed": _support.spectra_collection(smoothed_list)}

    @staticmethod
    def _smooth(inten: np.ndarray, method: str, window: int, polyorder: int, sigma: float) -> np.ndarray:
        size = inten.shape[0]
        if size == 0 or window <= 1:
            return inten.copy()

        if method == "moving_average":
            from scipy.ndimage import uniform_filter1d

            eff_window = min(window, size)
            return np.asarray(uniform_filter1d(inten, size=eff_window, mode="nearest"), dtype=np.float64)

        if method == "gaussian":
            from scipy.ndimage import gaussian_filter1d

            return np.asarray(gaussian_filter1d(inten, sigma=sigma, mode="nearest"), dtype=np.float64)

        if method == "median":
            from scipy.signal import medfilt

            eff_window = min(window, size)
            if eff_window % 2 == 0:  # medfilt requires an odd kernel
                eff_window -= 1
            if eff_window < 1:
                return inten.copy()
            return np.asarray(medfilt(inten, kernel_size=eff_window), dtype=np.float64)

        # savitzky_golay
        from scipy.signal import savgol_filter

        eff_window = min(window, size)
        if eff_window % 2 == 0:  # savgol requires an odd window
            eff_window -= 1
        if eff_window < 3:
            return inten.copy()
        eff_poly = min(polyorder, eff_window - 1)
        return np.asarray(savgol_filter(inten, window_length=eff_window, polyorder=eff_poly), dtype=np.float64)


class AlignAndResampleSpectra(ProcessBlock):
    """Align and resample spectra to a shared grid (FR-067..FR-073)."""

    type_name: ClassVar[str] = "spectroscopy.align_and_resample_spectra"
    name: ClassVar[str] = "Align and Resample Spectra"
    description: ClassVar[str] = "Align and/or resample spectra onto a shared grid with fit diagnostics."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "align_and_resample_spectra"

    _ALIGN_METHODS: ClassVar[frozenset[str]] = frozenset({"none", "peak_fit", "cross_correlation"})
    _GRID_MODES: ClassVar[frozenset[str]] = frozenset({"explicit", "first", "reference", "range_step"})

    input_ports: ClassVar[list[InputPort]] = [
        _SPECTRA_INPUT,
        InputPort(
            name="reference",
            accepted_types=[Spectrum],
            required=False,
            description="Optional reference spectrum for target grid / alignment.",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="aligned", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="fit_curves", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="fit_diagnostics", accepted_types=[DataFrame]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "alignment_method": {
                "type": "string",
                "enum": ["none", "peak_fit", "cross_correlation"],
                "default": "none",
                "title": "Alignment method",
            },
            "target_grid_mode": {
                "type": "string",
                "enum": ["explicit", "first", "reference", "range_step"],
                "default": "first",
                "title": "Target grid mode",
            },
            "target_grid": {"type": "array", "items": {"type": "number"}, "title": "Explicit target grid"},
            "lambda_min": {"type": "number", "title": "Range min (range_step)"},
            "lambda_max": {"type": "number", "title": "Range max (range_step)"},
            "step": {"type": "number", "minimum": 0, "title": "Range step (range_step)"},
        },
        "required": ["alignment_method", "target_grid_mode"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Align and resample spectra onto a shared grid (FR-067..FR-073).

        ``fit_curves`` carries fitted peak curves when ``alignment_method`` is
        ``peak_fit`` (one per input spectrum, on the input grid) and is an empty
        ``Collection[Spectrum]`` otherwise (FR-072). ``fit_diagnostics`` records
        one row per input spectrum (method, status, applied_shift, fit quality).
        A per-spectrum alignment failure records a non-success status, applies a
        zero shift, and still resamples.
        """
        spectra = _support.coerce_spectra(inputs.get("spectra"), block=self.name, port="spectra")
        alignment_method = str(config.get("alignment_method", "none"))
        if alignment_method not in self._ALIGN_METHODS:
            raise ValueError(
                f"{self.name}: unknown alignment_method {alignment_method!r}; "
                f"expected one of {sorted(self._ALIGN_METHODS)}"
            )
        grid_mode = str(config.get("target_grid_mode", "first"))
        if grid_mode not in self._GRID_MODES:
            raise ValueError(
                f"{self.name}: unknown target_grid_mode {grid_mode!r}; expected one of {sorted(self._GRID_MODES)}"
            )

        reference_value = inputs.get("reference")
        reference = (
            _support.coerce_single_spectrum(reference_value, block=self.name, port="reference")
            if reference_value is not None
            else None
        )
        target_grid = self._target_grid(config, grid_mode, spectra, reference)

        aligned_list: list[Spectrum] = []
        fit_curves: list[Spectrum] = []
        diag_rows: list[dict[str, Any]] = []

        for spectrum in spectra:
            lam, inten = _support.spectrum_arrays(spectrum)
            applied_shift = 0.0
            quality = float("nan")
            status = "ok"
            fit_curve: np.ndarray | None = None
            try:
                if alignment_method == "peak_fit":
                    applied_shift, quality, fit_curve = self._peak_fit_shift(lam, inten, reference)
                elif alignment_method == "cross_correlation":
                    applied_shift, quality = self._cross_correlation_shift(lam, inten, reference)
            except Exception as exc:
                status = f"error: {type(exc).__name__}: {exc}"
                applied_shift = 0.0

            shifted_lam = lam + applied_shift
            resampled = np.interp(target_grid, shifted_lam, inten, left=float("nan"), right=float("nan"))
            aligned_list.append(
                self._auto_flush(
                    _support.derive_spectrum(spectrum, lambda_values=target_grid, intensity_values=resampled)
                )
            )

            if alignment_method == "peak_fit":
                curve = fit_curve if fit_curve is not None else np.zeros_like(inten)
                fit_curves.append(self._auto_flush(_support.derive_spectrum(spectrum, intensity_values=curve)))

            diag_rows.append(
                {
                    "spectrum_id": spectrum.spectrum_id,
                    "method": alignment_method,
                    "status": status,
                    "applied_shift": float(applied_shift),
                    "fit_quality": float(quality),
                }
            )

        diagnostics = _support.dataframe_from_rows(
            diag_rows,
            columns=["spectrum_id", "method", "status", "applied_shift", "fit_quality"],
        )
        return {
            "aligned": _support.spectra_collection(aligned_list),
            "fit_curves": _support.spectra_collection(fit_curves),
            "fit_diagnostics": _support.dataframe_collection(diagnostics),
        }

    def _target_grid(
        self,
        config: BlockConfig,
        grid_mode: str,
        spectra: list[Spectrum],
        reference: Spectrum | None,
    ) -> np.ndarray:
        if grid_mode == "explicit":
            raw = config.get("target_grid", None)
            if not raw:
                raise ValueError(f"{self.name}: target_grid_mode='explicit' requires a non-empty 'target_grid'")
            return np.asarray(raw, dtype=np.float64)
        if grid_mode == "reference":
            if reference is None:
                raise ValueError(f"{self.name}: target_grid_mode='reference' requires a 'reference' input")
            ref_lam, _ = _support.spectrum_arrays(reference)
            return ref_lam
        if grid_mode == "range_step":
            raw_min = config.get("lambda_min", None)
            raw_max = config.get("lambda_max", None)
            raw_step = config.get("step", None)
            if raw_min is None or raw_max is None or raw_step is None:
                raise ValueError(
                    f"{self.name}: target_grid_mode='range_step' requires lambda_min, lambda_max, and step"
                )
            start, stop, step = float(raw_min), float(raw_max), float(raw_step)
            if step <= 0:
                raise ValueError(f"{self.name}: step must be > 0 for range_step, got {step}")
            return np.arange(start, stop + 0.5 * step, step, dtype=np.float64)
        # first
        first_lam, _ = _support.spectrum_arrays(spectra[0])
        return first_lam

    def _peak_fit_shift(
        self, lam: np.ndarray, inten: np.ndarray, reference: Spectrum | None
    ) -> tuple[float, float, np.ndarray]:
        from scipy.optimize import curve_fit

        amplitude0 = float(np.max(inten) - np.min(inten)) or 1.0
        center0 = float(lam[int(np.argmax(inten))])
        span = float(lam[-1] - lam[0]) if lam.shape[0] > 1 else 1.0
        sigma0 = abs(span) / 10.0 or 1.0
        popt, _ = curve_fit(_gaussian, lam, inten, p0=[amplitude0, center0, sigma0], maxfev=10000)
        fit_curve = _gaussian(lam, *popt)
        quality = _rmse(inten, fit_curve)
        fitted_center = float(popt[1])

        reference_center = fitted_center
        if reference is not None:
            ref_lam, ref_inten = _support.spectrum_arrays(reference)
            ref_amp0 = float(np.max(ref_inten) - np.min(ref_inten)) or 1.0
            ref_center0 = float(ref_lam[int(np.argmax(ref_inten))])
            ref_span = float(ref_lam[-1] - ref_lam[0]) if ref_lam.shape[0] > 1 else 1.0
            ref_sigma0 = abs(ref_span) / 10.0 or 1.0
            try:
                ref_popt, _ = curve_fit(
                    _gaussian, ref_lam, ref_inten, p0=[ref_amp0, ref_center0, ref_sigma0], maxfev=10000
                )
                reference_center = float(ref_popt[1])
            except Exception:
                reference_center = fitted_center

        applied_shift = reference_center - fitted_center
        return applied_shift, quality, np.asarray(fit_curve, dtype=np.float64)

    def _cross_correlation_shift(
        self, lam: np.ndarray, inten: np.ndarray, reference: Spectrum | None
    ) -> tuple[float, float]:
        if reference is None or lam.shape[0] < 2:
            return 0.0, float("nan")
        ref_lam, ref_inten = _support.spectrum_arrays(reference)
        # Resample the reference onto this spectrum's grid so lags map to lambda.
        ref_on_grid = np.interp(lam, ref_lam, ref_inten)
        a = inten - float(np.mean(inten))
        b = ref_on_grid - float(np.mean(ref_on_grid))
        correlation = np.correlate(b, a, mode="full")
        lag = int(np.argmax(correlation)) - (a.shape[0] - 1)
        spacing = float(np.mean(np.diff(lam))) if lam.shape[0] > 1 else 0.0
        applied_shift = lag * spacing
        peak = float(np.max(correlation))
        norm = float(np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
        quality = peak / norm
        return applied_shift, quality


class NormalizeSpectrum(ProcessBlock):
    """Normalize intensities with ``max`` or ``minmax`` (FR-074, FR-075)."""

    type_name: ClassVar[str] = "spectroscopy.normalize_spectrum"
    name: ClassVar[str] = "Normalize Spectrum"
    description: ClassVar[str] = "Normalize intensities using max or minmax scaling."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "normalize_spectrum"

    _METHODS: ClassVar[frozenset[str]] = frozenset({"max", "minmax"})

    input_ports: ClassVar[list[InputPort]] = [_SPECTRA_INPUT]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="normalized", accepted_types=[Spectrum], is_collection=True),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["max", "minmax"],
                "default": "max",
                "title": "Normalization method",
            },
        },
        "required": ["method"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Normalize intensities with ``max`` or ``minmax`` (FR-074, FR-075).

        ``max`` divides by the maximum; ``minmax`` rescales to ``[0, 1]``. A
        constant or all-zero spectrum (zero denominator) is passed through
        unchanged to avoid divide-by-zero.
        """
        spectra = _support.coerce_spectra(inputs.get("spectra"), block=self.name, port="spectra")
        method = str(config.get("method", "max"))
        if method not in self._METHODS:
            raise ValueError(f"{self.name}: unknown method {method!r}; expected one of {sorted(self._METHODS)}")

        normalized_list: list[Spectrum] = []
        for spectrum in spectra:
            _, inten = _support.spectrum_arrays(spectrum)
            if inten.size == 0:
                normalized = inten.copy()
            elif method == "max":
                denom = float(np.max(inten))
                normalized = inten / denom if abs(denom) > 1e-12 else inten.copy()
            else:  # minmax
                low = float(np.min(inten))
                high = float(np.max(inten))
                span = high - low
                normalized = (inten - low) / span if abs(span) > 1e-12 else inten.copy()
            normalized_list.append(self._auto_flush(_support.derive_spectrum(spectrum, intensity_values=normalized)))

        return {"normalized": _support.spectra_collection(normalized_list)}


class SubtractPeakComponent(ProcessBlock):
    """Fit and subtract a peak component per spectrum (FR-076..FR-080)."""

    type_name: ClassVar[str] = "spectroscopy.subtract_peak_component"
    name: ClassVar[str] = "Subtract Peak Component"
    description: ClassVar[str] = "Fit a peak/component, subtract it, output the fitted curve and diagnostics."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "subtract_peak_component"

    _MODELS: ClassVar[frozenset[str]] = frozenset({"gaussian", "lorentzian", "voigt"})

    input_ports: ClassVar[list[InputPort]] = [_SPECTRA_INPUT]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="corrected", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="component", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="fit_diagnostics", accepted_types=[DataFrame]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "model": {
                "type": "string",
                "enum": ["gaussian", "lorentzian", "voigt"],
                "default": "gaussian",
                "title": "Component model",
            },
            "peak_center": {"type": "number", "title": "Peak center"},
            "window": {"type": "number", "minimum": 0, "title": "Fit window half-width"},
        },
        "required": ["model"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Fit and subtract one peak component per spectrum (FR-076..FR-080).

        Emits ``component`` (the fitted curve on the input grid), ``corrected``
        (``intensity - component``), and a per-spectrum ``fit_diagnostics`` table
        (model, status, center, amplitude, width params, fwhm, area, rmse). On a
        per-spectrum fit failure the component is zero, the input passes through,
        and a non-success status row is recorded.
        """
        spectra = _support.coerce_spectra(inputs.get("spectra"), block=self.name, port="spectra")
        model = str(config.get("model", "gaussian"))
        if model not in self._MODELS:
            raise ValueError(f"{self.name}: unknown model {model!r}; expected one of {sorted(self._MODELS)}")
        raw_center = config.get("peak_center", None)
        peak_center = float(raw_center) if raw_center is not None else None
        raw_window = config.get("window", None)
        window = float(raw_window) if raw_window is not None else None

        corrected_list: list[Spectrum] = []
        component_list: list[Spectrum] = []
        diag_rows: list[dict[str, Any]] = []

        for spectrum in spectra:
            lam, inten = _support.spectrum_arrays(spectrum)
            row: dict[str, Any] = {
                "spectrum_id": spectrum.spectrum_id,
                "model": model,
                "status": "ok",
                "center": float("nan"),
                "amplitude": float("nan"),
                "sigma": float("nan"),
                "gamma": float("nan"),
                "fwhm": float("nan"),
                "area": float("nan"),
                "rmse": float("nan"),
            }
            component = np.zeros_like(inten)
            try:
                component, row = self._fit_component(lam, inten, model, peak_center, window, row)
            except Exception as exc:
                row["status"] = f"error: {type(exc).__name__}: {exc}"
                component = np.zeros_like(inten)

            corrected = inten - component
            corrected_list.append(self._auto_flush(_support.derive_spectrum(spectrum, intensity_values=corrected)))
            component_list.append(self._auto_flush(_support.derive_spectrum(spectrum, intensity_values=component)))
            diag_rows.append(row)

        diagnostics = _support.dataframe_from_rows(
            diag_rows,
            columns=[
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
            ],
        )
        return {
            "corrected": _support.spectra_collection(corrected_list),
            "component": _support.spectra_collection(component_list),
            "fit_diagnostics": _support.dataframe_collection(diagnostics),
        }

    def _fit_component(
        self,
        lam: np.ndarray,
        inten: np.ndarray,
        model: str,
        peak_center: float | None,
        window: float | None,
        row: dict[str, Any],
    ) -> tuple[np.ndarray, dict[str, Any]]:
        from scipy.optimize import curve_fit

        # Restrict the fit window when a center + half-width are configured.
        if peak_center is not None and window is not None and window > 0:
            mask = (lam >= peak_center - window) & (lam <= peak_center + window)
            if int(mask.sum()) < 4:
                raise ValueError("fit window contains too few points (need >= 4)")
            fit_lam, fit_inten = lam[mask], inten[mask]
        else:
            fit_lam, fit_inten = lam, inten

        if fit_lam.shape[0] < 4:
            raise ValueError("too few points to fit a peak component (need >= 4)")

        amplitude0 = float(np.max(fit_inten) - np.min(fit_inten)) or 1.0
        center0 = peak_center if peak_center is not None else float(fit_lam[int(np.argmax(fit_inten))])
        span = float(fit_lam[-1] - fit_lam[0]) if fit_lam.shape[0] > 1 else 1.0
        width0 = abs(span) / 10.0 or 1.0

        if model == "gaussian":
            popt, _ = curve_fit(_gaussian, fit_lam, fit_inten, p0=[amplitude0, center0, width0], maxfev=10000)
            amplitude, center, sigma = float(popt[0]), float(popt[1]), float(popt[2])
            component = _gaussian(lam, amplitude, center, sigma)
            fwhm = _gaussian_fwhm(sigma)
            area = float(amplitude * abs(sigma) * np.sqrt(2.0 * np.pi))
            row.update({"amplitude": amplitude, "center": center, "sigma": abs(sigma)})
        elif model == "lorentzian":
            popt, _ = curve_fit(_lorentzian, fit_lam, fit_inten, p0=[amplitude0, center0, width0], maxfev=10000)
            amplitude, center, gamma = float(popt[0]), float(popt[1]), float(popt[2])
            component = _lorentzian(lam, amplitude, center, gamma)
            fwhm = _lorentzian_fwhm(gamma)
            area = float(amplitude * np.pi * abs(gamma))
            row.update({"amplitude": amplitude, "center": center, "gamma": abs(gamma)})
        else:  # voigt
            popt, _ = curve_fit(
                _voigt,
                fit_lam,
                fit_inten,
                p0=[amplitude0, center0, width0, width0],
                maxfev=10000,
            )
            amplitude, center, sigma, gamma = (
                float(popt[0]),
                float(popt[1]),
                float(popt[2]),
                float(popt[3]),
            )
            component = _voigt(lam, amplitude, center, sigma, gamma)
            fwhm = _voigt_fwhm(sigma, gamma)
            area = float(np.trapezoid(component, lam))
            row.update({"amplitude": amplitude, "center": center, "sigma": abs(sigma), "gamma": abs(gamma)})

        component = np.asarray(component, dtype=np.float64)
        row["fwhm"] = float(fwhm)
        row["area"] = float(area)
        # RMSE is measured on the actual fit window for fidelity.
        row["rmse"] = _rmse(fit_inten, _model_on(model, fit_lam, row))
        return component, row


def _model_on(model: str, x: np.ndarray, row: dict[str, Any]) -> np.ndarray:
    """Evaluate the fitted model on ``x`` using parameters captured in ``row``."""
    amplitude = float(row["amplitude"])
    center = float(row["center"])
    if model == "gaussian":
        return _gaussian(x, amplitude, center, float(row["sigma"]))
    if model == "lorentzian":
        return _lorentzian(x, amplitude, center, float(row["gamma"]))
    return _voigt(x, amplitude, center, float(row["sigma"]), float(row["gamma"]))


BLOCKS: list[type] = [
    CropSpectrumRange,
    ShiftSpectralAxis,
    BaselineCorrection,
    SmoothSpectrum,
    AlignAndResampleSpectra,
    NormalizeSpectrum,
    SubtractPeakComponent,
]

__all__ = [
    "BLOCKS",
    "AlignAndResampleSpectra",
    "BaselineCorrection",
    "CropSpectrumRange",
    "NormalizeSpectrum",
    "ShiftSpectralAxis",
    "SmoothSpectrum",
    "SubtractPeakComponent",
]
