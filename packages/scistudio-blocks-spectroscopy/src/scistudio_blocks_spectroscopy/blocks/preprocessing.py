"""Preprocessing blocks for the SciStudio spectroscopy package.

The blocks in this module operate on one ``Spectrum`` or a
``Collection[Spectrum]`` and deliberately reject ``SpectralDataset`` inputs.
Dataset workflows should use the utility conversion blocks around these
scientific transformations.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import Any, ClassVar, cast

import numpy as np
import pyarrow as pa

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

BASELINE_METHODS: tuple[str, ...] = ("polynomial", "asls", "arpls", "airpls")
SMOOTHING_METHODS: tuple[str, ...] = ("savitzky_golay", "moving_average", "gaussian", "median")
ALIGNMENT_METHODS: tuple[str, ...] = ("none", "peak_fit", "cross_correlation")
TARGET_GRID_MODES: tuple[str, ...] = ("first_spectrum", "reference_spectrum", "range_step", "explicit")
NORMALIZATION_METHODS: tuple[str, ...] = ("max", "minmax")
PEAK_COMPONENT_MODELS: tuple[str, ...] = ("gaussian", "lorentzian", "voigt")


def _spectra_input_port() -> InputPort:
    return InputPort(
        name="spectra",
        accepted_types=[Spectrum],
        is_collection=True,
        required=True,
        description="Spectrum or Collection[Spectrum]. SpectralDataset must be converted upstream.",
    )


class CropSpectrumRange(ProcessBlock):
    """Drop spectral points outside a configured lambda range."""

    type_name: ClassVar[str] = "spectroscopy.crop_spectrum_range"
    name: ClassVar[str] = "Crop Spectrum Range"
    description: ClassVar[str] = "Crop spectra to lambda_min and lambda_max without changing kept intensities."
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "crop_spectrum_range"

    input_ports: ClassVar[list[InputPort]] = [_spectra_input_port()]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="cropped", accepted_types=[Spectrum], is_collection=True),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "lambda_min": {"type": ["number", "null"], "default": None},
            "lambda_max": {"type": ["number", "null"], "default": None},
        },
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        items = _require_spectra(inputs.get("spectra"), block_name=type(self).__name__)
        lambda_min = _optional_float(config.get("lambda_min"))
        lambda_max = _optional_float(config.get("lambda_max"))
        if lambda_min is not None and lambda_max is not None and lambda_min > lambda_max:
            raise ValueError("CropSpectrumRange: lambda_min must be <= lambda_max")

        results = []
        for item in items:
            lambda_values, intensities = _spectrum_arrays(item)
            keep = np.ones(lambda_values.shape, dtype=bool)
            if lambda_min is not None:
                keep &= lambda_values >= lambda_min
            if lambda_max is not None:
                keep &= lambda_values <= lambda_max
            results.append(_make_spectrum_like(item, lambda_values[keep], intensities[keep]))
        return {"cropped": _pack_spectra(results)}


class ShiftSpectralAxis(ProcessBlock):
    """Shift each spectrum's lambda coordinate by a configured amount."""

    type_name: ClassVar[str] = "spectroscopy.shift_spectral_axis"
    name: ClassVar[str] = "Shift Spectral Axis"
    description: ClassVar[str] = "Add a constant shift to the lambda axis without changing intensities."
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "shift_spectral_axis"

    input_ports: ClassVar[list[InputPort]] = [_spectra_input_port()]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="shifted", accepted_types=[Spectrum], is_collection=True),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"shift": {"type": "number", "default": 0.0}},
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        items = _require_spectra(inputs.get("spectra"), block_name=type(self).__name__)
        shift = float(config.get("shift", 0.0))
        return {
            "shifted": _pack_spectra(
                [
                    _make_spectrum_like(item, _spectrum_arrays(item)[0] + shift, _spectrum_arrays(item)[1])
                    for item in items
                ]
            )
        }


class BaselineCorrection(ProcessBlock):
    """Estimate and subtract a spectral baseline."""

    type_name: ClassVar[str] = "spectroscopy.baseline_correction"
    name: ClassVar[str] = "Baseline Correction"
    description: ClassVar[str] = "Estimate baseline curves and subtract them from each spectrum."
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "baseline_correction"

    input_ports: ClassVar[list[InputPort]] = [_spectra_input_port()]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="corrected", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="baseline", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="fit_diagnostics", accepted_types=[DataFrame]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {"type": "string", "enum": list(BASELINE_METHODS), "default": "polynomial"},
            "polynomial_order": {"type": "integer", "default": 2, "minimum": 0},
            "lambda_smoothness": {"type": "number", "default": 100000.0, "minimum": 0.0},
            "asymmetry": {"type": "number", "default": 0.001, "minimum": 0.0, "maximum": 1.0},
            "max_iterations": {"type": "integer", "default": 50, "minimum": 1},
            "tolerance": {"type": "number", "default": 1e-6, "minimum": 0.0},
        },
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        items = _require_spectra(inputs.get("spectra"), block_name=type(self).__name__)
        method = _require_choice(str(config.get("method", "polynomial")), BASELINE_METHODS, "BaselineCorrection.method")
        corrected: list[Spectrum] = []
        baselines: list[Spectrum] = []
        rows: list[dict[str, Any]] = []

        for item in items:
            lambda_values, intensities = _spectrum_arrays(item)
            baseline, diagnostic = _estimate_baseline(lambda_values, intensities, method, config)
            corrected_values = intensities - baseline
            corrected.append(_make_spectrum_like(item, lambda_values, corrected_values))
            baselines.append(_make_spectrum_like(item, lambda_values, baseline))
            rows.append(
                {
                    "spectrum_id": _spectrum_id(item),
                    "method": method,
                    "status": diagnostic["status"],
                    "parameters": json.dumps(diagnostic["parameters"], sort_keys=True),
                    "converged": bool(diagnostic["converged"]),
                    "iterations": int(diagnostic["iterations"]),
                    "rmse": _rmse(intensities, baseline),
                    "error": diagnostic.get("error"),
                }
            )

        return {
            "corrected": _pack_spectra(corrected),
            "baseline": _pack_spectra(baselines),
            "fit_diagnostics": _dataframe_from_rows(rows),
        }


class SmoothSpectrum(ProcessBlock):
    """Smooth spectrum intensities without changing lambda coordinates."""

    type_name: ClassVar[str] = "spectroscopy.smooth_spectrum"
    name: ClassVar[str] = "Smooth Spectrum"
    description: ClassVar[str] = "Apply an accepted smoothing method to spectrum intensities."
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "smooth_spectrum"

    input_ports: ClassVar[list[InputPort]] = [_spectra_input_port()]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="smoothed", accepted_types=[Spectrum], is_collection=True),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {"type": "string", "enum": list(SMOOTHING_METHODS), "default": "savitzky_golay"},
            "window": {"type": "integer", "default": 5, "minimum": 1},
            "polyorder": {"type": "integer", "default": 2, "minimum": 0},
            "sigma": {"type": "number", "default": 1.0, "exclusiveMinimum": 0.0},
        },
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        items = _require_spectra(inputs.get("spectra"), block_name=type(self).__name__)
        method = _require_choice(
            str(config.get("method", "savitzky_golay")), SMOOTHING_METHODS, "SmoothSpectrum.method"
        )
        results = []
        for item in items:
            lambda_values, intensities = _spectrum_arrays(item)
            smoothed = _smooth_values(lambda_values, intensities, method, config)
            results.append(_make_spectrum_like(item, lambda_values, smoothed))
        return {"smoothed": _pack_spectra(results)}


class AlignAndResampleSpectra(ProcessBlock):
    """Align and/or resample spectra to a shared target grid."""

    type_name: ClassVar[str] = "spectroscopy.align_and_resample_spectra"
    name: ClassVar[str] = "Align And Resample Spectra"
    description: ClassVar[str] = "Align spectra and resample them onto a configured target grid."
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "align_and_resample_spectra"

    input_ports: ClassVar[list[InputPort]] = [
        _spectra_input_port(),
        InputPort(name="reference", accepted_types=[Spectrum], required=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="aligned", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="fit_curves", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="fit_diagnostics", accepted_types=[DataFrame]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "alignment_method": {"type": "string", "enum": list(ALIGNMENT_METHODS), "default": "none"},
            "target_grid_mode": {"type": "string", "enum": list(TARGET_GRID_MODES), "default": "first_spectrum"},
            "target_grid": {"type": "array", "items": {"type": "number"}},
            "lambda_min": {"type": ["number", "null"], "default": None},
            "lambda_max": {"type": ["number", "null"], "default": None},
            "step": {"type": ["number", "null"], "default": None},
            "reference_index": {"type": "integer", "default": 0, "minimum": 0},
            "peak_center": {"type": ["number", "null"], "default": None},
            "fit_window": {"type": ["number", "null"], "default": None},
        },
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        items = _require_spectra(inputs.get("spectra"), block_name=type(self).__name__)
        method = _require_choice(
            str(config.get("alignment_method", "none")),
            ALIGNMENT_METHODS,
            "AlignAndResampleSpectra.alignment_method",
        )
        target_grid = _target_grid(items, inputs.get("reference"), config)
        reference_item = _reference_spectrum(items, inputs.get("reference"), config)
        reference_lambda, reference_intensity = (
            _spectrum_arrays(reference_item)
            if reference_item is not None
            else (target_grid, np.zeros_like(target_grid))
        )
        reference_on_target = _interp_on_grid(reference_lambda, reference_intensity, target_grid)

        aligned: list[Spectrum] = []
        fit_curves: list[Spectrum] = []
        rows: list[dict[str, Any]] = []

        for item in items:
            lambda_values, intensities = _spectrum_arrays(item)
            applied_shift = 0.0
            status = "ok"
            quality: dict[str, float | None] = {
                "correlation": None,
                "rmse": None,
                "fit_center": None,
                "reference_center": None,
            }
            curve = np.zeros(target_grid.shape, dtype=np.float64)

            if method == "peak_fit":
                sample_fit = _estimate_peak(lambda_values, intensities, config)
                ref_fit = _estimate_peak(reference_lambda, reference_intensity, config)
                applied_shift = sample_fit.center - ref_fit.center
                quality["fit_center"] = sample_fit.center
                quality["reference_center"] = ref_fit.center
                curve = _component_curve(
                    target_grid, ref_fit.center, sample_fit.amplitude, sample_fit.width, "gaussian"
                )
            elif method == "cross_correlation":
                sample_on_target = _interp_on_grid(lambda_values, intensities, target_grid)
                applied_shift = _estimate_peak_shift(target_grid, sample_on_target, reference_on_target)
            elif method == "none":
                status = "not_fit"

            aligned_values = _interp_on_grid(lambda_values, intensities, target_grid + applied_shift)
            if method != "none":
                quality["correlation"] = _correlation(aligned_values, reference_on_target)
                quality["rmse"] = _rmse(aligned_values, reference_on_target)

            aligned.append(_make_spectrum_like(item, target_grid, aligned_values))
            fit_curves.append(_make_spectrum_like(item, target_grid, curve))
            rows.append(
                {
                    "spectrum_id": _spectrum_id(item),
                    "alignment_method": method,
                    "status": status,
                    "applied_shift": applied_shift,
                    "correlation": quality["correlation"],
                    "rmse": quality["rmse"],
                    "fit_center": quality["fit_center"],
                    "reference_center": quality["reference_center"],
                }
            )

        return {
            "aligned": _pack_spectra(aligned),
            "fit_curves": _pack_spectra(fit_curves),
            "fit_diagnostics": _dataframe_from_rows(rows),
        }


class NormalizeSpectrum(ProcessBlock):
    """Normalize spectrum intensities with accepted methods only."""

    type_name: ClassVar[str] = "spectroscopy.normalize_spectrum"
    name: ClassVar[str] = "Normalize Spectrum"
    description: ClassVar[str] = "Normalize spectrum intensities with max or minmax scaling."
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "normalize_spectrum"

    input_ports: ClassVar[list[InputPort]] = [_spectra_input_port()]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="normalized", accepted_types=[Spectrum], is_collection=True),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"method": {"type": "string", "enum": list(NORMALIZATION_METHODS), "default": "max"}},
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        items = _require_spectra(inputs.get("spectra"), block_name=type(self).__name__)
        method = _require_choice(str(config.get("method", "max")), NORMALIZATION_METHODS, "NormalizeSpectrum.method")
        results = []
        for item in items:
            lambda_values, intensities = _spectrum_arrays(item)
            results.append(_make_spectrum_like(item, lambda_values, _normalize(intensities, method)))
        return {"normalized": _pack_spectra(results)}


class SubtractPeakComponent(ProcessBlock):
    """Fit a known peak component and subtract it from each spectrum."""

    type_name: ClassVar[str] = "spectroscopy.subtract_peak_component"
    name: ClassVar[str] = "Subtract Peak Component"
    description: ClassVar[str] = "Fit and subtract a Gaussian, Lorentzian, or Voigt component."
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "subtract_peak_component"

    input_ports: ClassVar[list[InputPort]] = [_spectra_input_port()]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="corrected", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="component", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="fit_diagnostics", accepted_types=[DataFrame]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "model": {"type": "string", "enum": list(PEAK_COMPONENT_MODELS), "default": "gaussian"},
            "center": {"type": ["number", "null"], "default": None},
            "width": {"type": ["number", "null"], "default": None},
            "amplitude": {"type": ["number", "null"], "default": None},
            "fit_window": {"type": ["number", "null"], "default": None},
            "eta": {"type": "number", "default": 0.5, "minimum": 0.0, "maximum": 1.0},
        },
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        items = _require_spectra(inputs.get("spectra"), block_name=type(self).__name__)
        model = _require_choice(
            str(config.get("model", "gaussian")), PEAK_COMPONENT_MODELS, "SubtractPeakComponent.model"
        )
        corrected: list[Spectrum] = []
        components: list[Spectrum] = []
        rows: list[dict[str, Any]] = []

        for item in items:
            lambda_values, intensities = _spectrum_arrays(item)
            fit = _estimate_peak(lambda_values, intensities, config)
            amplitude = _optional_float(config.get("amplitude"))
            if amplitude is not None:
                fit = fit.with_amplitude(amplitude)
            component = _component_curve(
                lambda_values, fit.center, fit.amplitude, fit.width, model, eta=float(config.get("eta", 0.5))
            )
            corrected_values = intensities - component
            corrected.append(_make_spectrum_like(item, lambda_values, corrected_values))
            components.append(_make_spectrum_like(item, lambda_values, component))
            rows.append(
                {
                    "spectrum_id": _spectrum_id(item),
                    "model": model,
                    "status": fit.status,
                    "center": fit.center,
                    "amplitude": fit.amplitude,
                    "width": fit.width,
                    "sigma": fit.width if model in {"gaussian", "voigt"} else None,
                    "gamma": fit.width if model in {"lorentzian", "voigt"} else None,
                    "eta": float(config.get("eta", 0.5)) if model == "voigt" else None,
                    "fwhm": _component_fwhm(fit.width, model, eta=float(config.get("eta", 0.5))),
                    "area": _component_area(fit.amplitude, fit.width, model, eta=float(config.get("eta", 0.5))),
                    "rmse": _rmse(intensities, component),
                }
            )

        return {
            "corrected": _pack_spectra(corrected),
            "component": _pack_spectra(components),
            "fit_diagnostics": _dataframe_from_rows(rows),
        }


def _require_spectra(value: Any, *, block_name: str) -> list[Spectrum]:
    if value is None:
        raise ValueError(f"{block_name}: missing required 'spectra' input")
    if isinstance(value, SpectralDataset):
        raise ValueError(f"{block_name}: SpectralDataset inputs must be converted to Collection[Spectrum] upstream")
    if isinstance(value, Spectrum):
        return [value]
    if isinstance(value, Collection):
        if issubclass(value.item_type, SpectralDataset):
            raise ValueError(f"{block_name}: SpectralDataset collections are not accepted")
        if not issubclass(value.item_type, Spectrum):
            raise ValueError(f"{block_name}: expected Collection[Spectrum], got Collection[{value.item_type.__name__}]")
        return [cast(Spectrum, item) for item in value]
    raise ValueError(f"{block_name}: expected Spectrum or Collection[Spectrum], got {type(value).__name__}")


def _pack_spectra(items: list[Spectrum]) -> Collection:
    return (
        Collection(cast(list[DataObject], items), item_type=Spectrum) if items else Collection([], item_type=Spectrum)
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _require_choice(value: str, choices: Sequence[str], field: str) -> str:
    if value not in choices:
        raise ValueError(f"{field} must be one of {tuple(choices)}, got {value!r}")
    return value


def _spectrum_arrays(spectrum: Spectrum) -> tuple[np.ndarray, np.ndarray]:
    raw = spectrum.get_in_memory_data()
    index_name = getattr(spectrum, "index_name", None) or "lambda"
    value_name = getattr(spectrum, "value_name", None) or "intensity"
    lambda_values, intensities = _arrays_from_payload(raw, index_name=index_name, value_name=value_name)
    if lambda_values.shape != intensities.shape:
        raise ValueError(
            f"{type(spectrum).__name__}: lambda and intensity arrays must have the same shape, "
            f"got {lambda_values.shape} and {intensities.shape}"
        )
    return lambda_values.astype(np.float64, copy=False), intensities.astype(np.float64, copy=False)


def _arrays_from_payload(raw: Any, *, index_name: str, value_name: str) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(raw, pa.Table):
        names = raw.column_names
        x_name = index_name if index_name in names else "lambda" if "lambda" in names else names[0]
        y_name = value_name if value_name in names else "intensity" if "intensity" in names else names[1]
        return _arrow_column(raw, x_name), _arrow_column(raw, y_name)
    if isinstance(raw, dict):
        return np.asarray(raw[index_name if index_name in raw else "lambda"], dtype=np.float64), np.asarray(
            raw[value_name if value_name in raw else "intensity"], dtype=np.float64
        )
    if isinstance(raw, tuple | list) and len(raw) == 2:
        return np.asarray(raw[0], dtype=np.float64), np.asarray(raw[1], dtype=np.float64)

    columns = getattr(raw, "columns", None)
    if columns is not None:
        x_name = index_name if index_name in columns else "lambda" if "lambda" in columns else columns[0]
        y_name = value_name if value_name in columns else "intensity" if "intensity" in columns else columns[1]
        return np.asarray(raw[x_name], dtype=np.float64), np.asarray(raw[y_name], dtype=np.float64)

    arr = np.asarray(raw)
    if arr.dtype.names:
        x_name = index_name if index_name in arr.dtype.names else "lambda"
        y_name = value_name if value_name in arr.dtype.names else "intensity"
        return np.asarray(arr[x_name], dtype=np.float64), np.asarray(arr[y_name], dtype=np.float64)
    if arr.ndim == 1:
        return np.arange(arr.shape[0], dtype=np.float64), arr.astype(np.float64)
    if arr.ndim == 2 and arr.shape[1] >= 2:
        return arr[:, 0].astype(np.float64), arr[:, 1].astype(np.float64)
    if arr.ndim == 2 and arr.shape[0] == 2:
        return arr[0].astype(np.float64), arr[1].astype(np.float64)
    raise ValueError(f"Unsupported Spectrum payload shape {arr.shape}")


def _arrow_column(table: pa.Table, name: str) -> np.ndarray:
    return cast(np.ndarray, table.column(name).combine_chunks().to_numpy(zero_copy_only=False).astype(np.float64))


def _make_spectrum_like(source: Spectrum, lambda_values: np.ndarray, intensities: np.ndarray) -> Spectrum:
    index_name = getattr(source, "index_name", None) or "lambda"
    value_name = getattr(source, "value_name", None) or "intensity"
    table = pa.table(
        {
            index_name: pa.array(lambda_values.astype(np.float64, copy=False), type=pa.float64()),
            value_name: pa.array(intensities.astype(np.float64, copy=False), type=pa.float64()),
        }
    )
    return type(source)(
        index_name=index_name,
        value_name=value_name,
        length=len(lambda_values),
        framework=source.framework.derive(),
        meta=source.meta,
        user=dict(source.user),
        data=table,
    )


def _spectrum_id(spectrum: Spectrum) -> str:
    if spectrum.meta is not None and hasattr(spectrum.meta, "spectrum_id"):
        value = spectrum.meta.spectrum_id
        if value is not None:
            return str(value)
    if "spectrum_id" in spectrum.user:
        return str(spectrum.user["spectrum_id"])
    return str(spectrum.framework.object_id)


def _dataframe_from_rows(rows: list[dict[str, Any]]) -> DataFrame:
    if not rows:
        table = pa.table({})
        return DataFrame(columns=[], row_count=0, data=table)
    columns = list(rows[0].keys())
    arrays = {column: [row.get(column) for row in rows] for column in columns}
    table = pa.table(arrays)
    schema = {field.name: str(field.type) for field in table.schema}
    return DataFrame(columns=columns, row_count=table.num_rows, schema=schema, data=table)


def _estimate_baseline(
    lambda_values: np.ndarray, intensities: np.ndarray, method: str, config: BlockConfig
) -> tuple[np.ndarray, dict[str, Any]]:
    if len(intensities) == 0:
        return intensities.copy(), _diagnostic("empty_input", method, {}, True, 0)
    finite = np.isfinite(lambda_values) & np.isfinite(intensities)
    if not finite.any():
        return np.zeros_like(intensities), _diagnostic("no_finite_points", method, {}, False, 0)

    order = np.argsort(lambda_values, kind="mergesort")
    sorted_y = intensities[order]
    sorted_x = lambda_values[order]
    if method == "polynomial":
        baseline_sorted, diagnostic = _polynomial_baseline(sorted_x, sorted_y, config)
    else:
        baseline_sorted, diagnostic = _whittaker_baseline(sorted_y, method, config)
    baseline = np.empty_like(baseline_sorted)
    baseline[order] = baseline_sorted
    return baseline, diagnostic


def _diagnostic(
    status: str, method: str, parameters: dict[str, Any], converged: bool, iterations: int, error: str | None = None
) -> dict[str, Any]:
    return {
        "status": status,
        "method": method,
        "parameters": parameters,
        "converged": converged,
        "iterations": iterations,
        "error": error,
    }


def _polynomial_baseline(x: np.ndarray, y: np.ndarray, config: BlockConfig) -> tuple[np.ndarray, dict[str, Any]]:
    requested_order = int(config.get("polynomial_order", 2))
    if requested_order < 0:
        raise ValueError("BaselineCorrection.polynomial_order must be >= 0")
    finite = np.isfinite(x) & np.isfinite(y)
    if finite.sum() == 0:
        return np.zeros_like(y), _diagnostic(
            "no_finite_points", "polynomial", {"polynomial_order": requested_order}, False, 0
        )
    order = min(requested_order, max(int(finite.sum()) - 1, 0))
    try:
        coeffs = np.polyfit(x[finite], y[finite], deg=order)
        baseline = np.polyval(coeffs, x)
    except (np.linalg.LinAlgError, ValueError) as exc:
        return np.full_like(y, float(np.nanmean(y[finite]))), _diagnostic(
            "failed", "polynomial", {"polynomial_order": order}, False, 1, str(exc)
        )
    return baseline, _diagnostic("ok", "polynomial", {"polynomial_order": order}, True, 1)


def _whittaker_baseline(y: np.ndarray, method: str, config: BlockConfig) -> tuple[np.ndarray, dict[str, Any]]:
    n = len(y)
    if n < 3:
        return np.minimum.accumulate(y.copy()), _diagnostic("ok", method, {"short_input": True}, True, 1)
    smoothness = float(config.get("lambda_smoothness", 100000.0))
    asymmetry = float(config.get("asymmetry", 0.001))
    max_iterations = int(config.get("max_iterations", 50))
    tolerance = float(config.get("tolerance", 1e-6))
    if smoothness < 0 or max_iterations < 1 or tolerance < 0:
        raise ValueError("BaselineCorrection: smoothness, max_iterations, and tolerance must be non-negative")

    clean_y = np.nan_to_num(y.astype(np.float64), nan=float(np.nanmedian(y)))
    penalty = _second_difference_penalty(n)
    weights = np.ones(n, dtype=np.float64)
    baseline: np.ndarray = clean_y.copy()
    converged = False
    iterations = 0
    for iteration in range(1, max_iterations + 1):
        previous = baseline
        system = np.diag(weights) + smoothness * penalty
        rhs = weights * clean_y
        try:
            baseline = np.linalg.solve(system, rhs)
        except np.linalg.LinAlgError:
            baseline = np.linalg.lstsq(system, rhs, rcond=None)[0]
        residual = clean_y - baseline
        weights = _baseline_weights(residual, method, asymmetry, iteration)
        denom = max(float(np.linalg.norm(previous)), 1e-12)
        iterations = iteration
        if float(np.linalg.norm(baseline - previous) / denom) <= tolerance:
            converged = True
            break
    return baseline, _diagnostic(
        "ok",
        method,
        {"lambda_smoothness": smoothness, "asymmetry": asymmetry},
        converged,
        iterations,
    )


def _second_difference_penalty(n: int) -> np.ndarray:
    diff = np.diff(np.eye(n), n=2, axis=0)
    return cast(np.ndarray, diff.T @ diff)


def _baseline_weights(residual: np.ndarray, method: str, asymmetry: float, iteration: int) -> np.ndarray:
    if method == "asls":
        return np.where(residual > 0.0, asymmetry, 1.0 - asymmetry)
    negative = residual[residual < 0.0]
    if len(negative) == 0:
        return np.ones_like(residual)
    mean = float(np.mean(negative))
    std = max(float(np.std(negative)), 1e-12)
    if method == "arpls":
        arg = np.clip(2.0 * (residual - (2.0 * std - mean)) / std, -50.0, 50.0)
        return 1.0 / (1.0 + np.exp(arg))
    if method == "airpls":
        scale = max(float(np.sum(np.abs(negative))), 1e-12)
        weights = np.where(residual < 0.0, np.exp(np.clip(iteration * np.abs(residual) / scale, 0.0, 50.0)), 0.0)
        if weights[0] == 0.0:
            weights[0] = np.max(weights) if np.max(weights) > 0 else 1.0
        if weights[-1] == 0.0:
            weights[-1] = np.max(weights) if np.max(weights) > 0 else 1.0
        return weights
    raise ValueError(f"Unsupported baseline method {method!r}")


def _smooth_values(lambda_values: np.ndarray, intensities: np.ndarray, method: str, config: BlockConfig) -> np.ndarray:
    if len(intensities) <= 1:
        return intensities.copy()
    order = np.argsort(lambda_values, kind="mergesort")
    sorted_y = intensities[order]
    if method == "moving_average":
        smoothed_sorted = _moving_average(sorted_y, int(config.get("window", 5)))
    elif method == "median":
        smoothed_sorted = _sliding_median(sorted_y, int(config.get("window", 5)))
    elif method == "gaussian":
        smoothed_sorted = _gaussian_smooth(sorted_y, float(config.get("sigma", 1.0)))
    elif method == "savitzky_golay":
        smoothed_sorted = _savitzky_golay(sorted_y, int(config.get("window", 5)), int(config.get("polyorder", 2)))
    else:
        raise ValueError(f"SmoothSpectrum.method must be one of {SMOOTHING_METHODS}, got {method!r}")
    result = np.empty_like(smoothed_sorted)
    result[order] = smoothed_sorted
    return result


def _normalized_window(window: int, n: int) -> int:
    if window < 1:
        raise ValueError("window must be >= 1")
    return max(1, min(int(window), int(n)))


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    window = _normalized_window(window, len(values))
    if window == 1:
        return values.copy()
    radius = window // 2
    padded = np.pad(values, (radius, window - radius - 1), mode="edge")
    kernel = np.ones(window, dtype=np.float64) / float(window)
    return np.convolve(padded, kernel, mode="valid")


def _sliding_median(values: np.ndarray, window: int) -> np.ndarray:
    window = _normalized_window(window, len(values))
    if window == 1:
        return values.copy()
    radius = window // 2
    padded = np.pad(values, (radius, window - radius - 1), mode="edge")
    return np.asarray([np.median(padded[i : i + window]) for i in range(len(values))], dtype=np.float64)


def _gaussian_smooth(values: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        raise ValueError("sigma must be > 0")
    radius = max(1, math.ceil(3.0 * sigma))
    offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-0.5 * (offsets / sigma) ** 2)
    kernel /= np.sum(kernel)
    padded = np.pad(values, (radius, radius), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def _savitzky_golay(values: np.ndarray, window: int, polyorder: int) -> np.ndarray:
    window = _normalized_window(window, len(values))
    if window % 2 == 0 and window > 1:
        window -= 1
    if window <= 2:
        return values.copy()
    polyorder = min(max(polyorder, 0), window - 1)
    radius = window // 2
    positions = np.arange(len(values), dtype=np.float64)
    result = np.empty_like(values, dtype=np.float64)
    for idx in range(len(values)):
        lo = max(0, idx - radius)
        hi = min(len(values), idx + radius + 1)
        x = positions[lo:hi] - positions[idx]
        y = values[lo:hi]
        degree = min(polyorder, max(len(y) - 1, 0))
        if degree == 0:
            result[idx] = float(np.mean(y))
        else:
            coeffs = np.polyfit(x, y, deg=degree)
            result[idx] = float(np.polyval(coeffs, 0.0))
    return result


def _target_grid(items: list[Spectrum], reference_value: Any, config: BlockConfig) -> np.ndarray:
    mode = _require_choice(str(config.get("target_grid_mode", "first_spectrum")), TARGET_GRID_MODES, "target_grid_mode")
    if mode == "explicit":
        grid = np.asarray(config.get("target_grid", []), dtype=np.float64)
    elif mode == "range_step":
        lambda_min = _optional_float(config.get("lambda_min"))
        lambda_max = _optional_float(config.get("lambda_max"))
        step = _optional_float(config.get("step"))
        if lambda_min is None or lambda_max is None or step is None:
            raise ValueError("AlignAndResampleSpectra: range_step requires lambda_min, lambda_max, and step")
        if step <= 0 or lambda_min > lambda_max:
            raise ValueError("AlignAndResampleSpectra: step must be > 0 and lambda_min must be <= lambda_max")
        grid = np.arange(lambda_min, lambda_max + (step * 0.5), step, dtype=np.float64)
    elif mode == "reference_spectrum":
        reference = _reference_spectrum(items, reference_value, config)
        grid = _spectrum_arrays(reference)[0] if reference is not None else np.array([], dtype=np.float64)
    else:
        grid = _spectrum_arrays(items[0])[0] if items else np.array([], dtype=np.float64)
    if grid.ndim != 1:
        raise ValueError("AlignAndResampleSpectra: target grid must be one-dimensional")
    return grid.astype(np.float64, copy=False)


def _reference_spectrum(items: list[Spectrum], reference_value: Any, config: BlockConfig) -> Spectrum | None:
    if reference_value is not None:
        refs = _require_spectra(reference_value, block_name="AlignAndResampleSpectra.reference")
        if len(refs) != 1:
            raise ValueError("AlignAndResampleSpectra.reference must contain exactly one Spectrum")
        return refs[0]
    if not items:
        return None
    index = int(config.get("reference_index", 0))
    if index < 0 or index >= len(items):
        raise ValueError(f"AlignAndResampleSpectra.reference_index {index} is out of range")
    return items[index]


def _interp_on_grid(lambda_values: np.ndarray, intensities: np.ndarray, target_grid: np.ndarray) -> np.ndarray:
    if len(target_grid) == 0:
        return np.array([], dtype=np.float64)
    x, y = _unique_sorted_xy(lambda_values, intensities)
    if len(x) == 0:
        return np.full(target_grid.shape, np.nan, dtype=np.float64)
    if len(x) == 1:
        return np.full(target_grid.shape, y[0], dtype=np.float64)
    return cast(np.ndarray, np.interp(target_grid, x, y, left=y[0], right=y[-1]).astype(np.float64))


def _unique_sorted_xy(lambda_values: np.ndarray, intensities: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    finite = np.isfinite(lambda_values) & np.isfinite(intensities)
    x = lambda_values[finite]
    y = intensities[finite]
    if len(x) == 0:
        return x, y
    order = np.argsort(x, kind="mergesort")
    x = x[order]
    y = y[order]
    unique_x, inverse = np.unique(x, return_inverse=True)
    sums = np.zeros(len(unique_x), dtype=np.float64)
    counts = np.zeros(len(unique_x), dtype=np.float64)
    np.add.at(sums, inverse, y)
    np.add.at(counts, inverse, 1.0)
    return unique_x, sums / counts


def _estimate_peak_shift(grid: np.ndarray, sample: np.ndarray, reference: np.ndarray) -> float:
    if len(grid) == 0 or len(sample) == 0 or len(reference) == 0:
        return 0.0
    if np.all(~np.isfinite(sample)) or np.all(~np.isfinite(reference)):
        return 0.0
    sample_center = grid[int(np.nanargmax(sample))]
    reference_center = grid[int(np.nanargmax(reference))]
    return float(sample_center - reference_center)


def _correlation(a: np.ndarray, b: np.ndarray) -> float | None:
    finite = np.isfinite(a) & np.isfinite(b)
    if finite.sum() < 2:
        return None
    aa = a[finite] - float(np.mean(a[finite]))
    bb = b[finite] - float(np.mean(b[finite]))
    denom = float(np.linalg.norm(aa) * np.linalg.norm(bb))
    if denom == 0.0:
        return 1.0 if np.allclose(a[finite], b[finite]) else 0.0
    return float(np.dot(aa, bb) / denom)


def _normalize(values: np.ndarray, method: str) -> np.ndarray:
    if len(values) == 0:
        return values.copy()
    if method == "max":
        scale = float(np.nanmax(np.abs(values)))
        return np.zeros_like(values, dtype=np.float64) if scale == 0.0 or not np.isfinite(scale) else values / scale
    if method == "minmax":
        low = float(np.nanmin(values))
        high = float(np.nanmax(values))
        if high == low or not np.isfinite(high - low):
            return np.zeros_like(values, dtype=np.float64)
        return (values - low) / (high - low)
    raise ValueError(f"NormalizeSpectrum.method must be one of {NORMALIZATION_METHODS}, got {method!r}")


class _PeakFit:
    def __init__(self, *, center: float, amplitude: float, width: float, status: str) -> None:
        self.center = center
        self.amplitude = amplitude
        self.width = width
        self.status = status

    def with_amplitude(self, amplitude: float) -> _PeakFit:
        return _PeakFit(center=self.center, amplitude=amplitude, width=self.width, status=self.status)


def _estimate_peak(lambda_values: np.ndarray, intensities: np.ndarray, config: BlockConfig) -> _PeakFit:
    center_config = _optional_float(config.get("center", config.get("peak_center")))
    width_config = _optional_float(config.get("width"))
    fit_window = _optional_float(config.get("fit_window"))
    x, y = _unique_sorted_xy(lambda_values, intensities)
    if len(x) == 0:
        center = center_config if center_config is not None else 0.0
        width = width_config if width_config is not None else 1.0
        return _PeakFit(center=center, amplitude=0.0, width=max(width, 1e-12), status="empty_input")
    if center_config is not None and fit_window is not None and fit_window > 0:
        keep = (x >= center_config - fit_window) & (x <= center_config + fit_window)
        if keep.any():
            x = x[keep]
            y = y[keep]
    baseline = float(np.nanmin(y))
    peak_index = int(np.nanargmax(y - baseline))
    center = center_config if center_config is not None else float(x[peak_index])
    amplitude = max(float(y[peak_index] - baseline), 0.0)
    width = width_config if width_config is not None else _estimate_width(x, y, peak_index, baseline)
    return _PeakFit(center=center, amplitude=amplitude, width=max(float(width), 1e-12), status="ok")


def _estimate_width(x: np.ndarray, y: np.ndarray, peak_index: int, baseline: float) -> float:
    if len(x) < 2:
        return 1.0
    peak = float(y[peak_index])
    half = baseline + (peak - baseline) / 2.0
    above = np.flatnonzero(y >= half)
    if len(above) >= 2:
        return max(float((x[above[-1]] - x[above[0]]) / 2.354820045), 1e-12)
    return max(float(np.nanmedian(np.diff(np.unique(x)))), 1.0)


def _component_curve(
    lambda_values: np.ndarray, center: float, amplitude: float, width: float, model: str, *, eta: float = 0.5
) -> np.ndarray:
    width = max(float(width), 1e-12)
    z = (lambda_values - center) / width
    gaussian = amplitude * np.exp(-0.5 * z**2)
    if model == "gaussian":
        return gaussian
    lorentzian = amplitude / (1.0 + z**2)
    if model == "lorentzian":
        return lorentzian
    if model == "voigt":
        eta = min(max(float(eta), 0.0), 1.0)
        return eta * lorentzian + (1.0 - eta) * gaussian
    raise ValueError(f"Unsupported peak component model {model!r}")


def _component_fwhm(width: float, model: str, *, eta: float = 0.5) -> float:
    if model == "gaussian":
        return 2.354820045 * width
    if model == "lorentzian":
        return 2.0 * width
    eta = min(max(float(eta), 0.0), 1.0)
    return eta * (2.0 * width) + (1.0 - eta) * (2.354820045 * width)


def _component_area(amplitude: float, width: float, model: str, *, eta: float = 0.5) -> float:
    gaussian_area = amplitude * width * math.sqrt(2.0 * math.pi)
    lorentzian_area = math.pi * amplitude * width
    if model == "gaussian":
        return gaussian_area
    if model == "lorentzian":
        return lorentzian_area
    eta = min(max(float(eta), 0.0), 1.0)
    return eta * lorentzian_area + (1.0 - eta) * gaussian_area


def _rmse(a: np.ndarray, b: np.ndarray) -> float | None:
    finite = np.isfinite(a) & np.isfinite(b)
    if finite.sum() == 0:
        return None
    return float(np.sqrt(np.mean((a[finite] - b[finite]) ** 2)))


__all__ = [
    "ALIGNMENT_METHODS",
    "BASELINE_METHODS",
    "NORMALIZATION_METHODS",
    "PEAK_COMPONENT_MODELS",
    "SMOOTHING_METHODS",
    "TARGET_GRID_MODES",
    "AlignAndResampleSpectra",
    "BaselineCorrection",
    "CropSpectrumRange",
    "NormalizeSpectrum",
    "ShiftSpectralAxis",
    "SmoothSpectrum",
    "SubtractPeakComponent",
]
