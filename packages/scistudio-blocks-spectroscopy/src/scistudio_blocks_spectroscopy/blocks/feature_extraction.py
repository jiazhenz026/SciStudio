"""Feature extraction blocks for SciStudio spectroscopy spectra."""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy.types import Spectrum

from ._spectra import (
    PeakMeasurement,
    config_range,
    make_dataframe,
    measure_peak,
    range_mask,
    spectrum_arrays,
    spectrum_id,
    unpack_spectra_collection,
    window_with_interpolated_bounds,
)

_FEATURE_OUTPUT_PORT = [OutputPort(name="features", accepted_types=[DataFrame])]


class ExtractIntensity(ProcessBlock):
    """Measure an intensity at a coordinate, peak definition, or range."""

    type_name: ClassVar[str] = "spectroscopy.extract_intensity"
    name: ClassVar[str] = "Extract Intensity"
    algorithm: ClassVar[str] = "extract_intensity"
    description: ClassVar[str] = "Measure one scalar intensity from each spectrum."
    subcategory: ClassVar[str] = "spectroscopy-features"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="spectra", accepted_types=[Spectrum], is_collection=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = _FEATURE_OUTPUT_PORT
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "target_lambda": {"type": "number"},
            "target_peak": {"type": ["number", "object"]},
            "lambda_min": {"type": "number"},
            "lambda_max": {"type": "number"},
            "interpolation": {
                "type": "string",
                "enum": ["linear", "nearest", "none"],
                "default": "linear",
            },
        },
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        rows: list[dict[str, Any]] = []
        definition = _intensity_definition(config)
        interpolation = config.get("interpolation", "linear")
        for spectrum in unpack_spectra_collection(inputs["spectra"]):
            arrays = spectrum_arrays(spectrum)
            measurement = measure_peak(
                arrays.lambdas,
                arrays.intensities,
                definition,
                interpolation=interpolation,
            )
            rows.append(
                {
                    "spectrum_id": spectrum_id(spectrum),
                    "measured_lambda": measurement.coordinate,
                    "intensity": measurement.intensity,
                    "status": measurement.status,
                }
            )
        table = make_dataframe(rows, ["spectrum_id", "measured_lambda", "intensity", "status"])
        return {"features": Collection([table], item_type=DataFrame)}


class CalculateAUC(ProcessBlock):
    """Calculate area under the curve within a configured lambda range."""

    type_name: ClassVar[str] = "spectroscopy.calculate_auc"
    name: ClassVar[str] = "Calculate AUC"
    algorithm: ClassVar[str] = "calculate_auc"
    description: ClassVar[str] = "Calculate trapezoidal area under each spectrum over a lambda range."
    subcategory: ClassVar[str] = "spectroscopy-features"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="spectra", accepted_types=[Spectrum], is_collection=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = _FEATURE_OUTPUT_PORT
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "lambda_min": {"type": "number"},
            "lambda_max": {"type": "number"},
        },
        "required": ["lambda_min", "lambda_max"],
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        lambda_min, lambda_max = config_range(config)
        rows: list[dict[str, Any]] = []
        for spectrum in unpack_spectra_collection(inputs["spectra"]):
            arrays = spectrum_arrays(spectrum)
            window = window_with_interpolated_bounds(arrays.lambdas, arrays.intensities, lambda_min, lambda_max)
            if window.lambdas.size < 2:
                auc = None
                status = "empty_range"
            else:
                auc = float(np.trapezoid(window.intensities, window.lambdas))
                status = "success"
            rows.append(
                {
                    "spectrum_id": spectrum_id(spectrum),
                    "lambda_min": float(lambda_min),
                    "lambda_max": float(lambda_max),
                    "auc": auc,
                    "status": status,
                }
            )
        table = make_dataframe(rows, ["spectrum_id", "lambda_min", "lambda_max", "auc", "status"])
        return {"features": Collection([table], item_type=DataFrame)}


class CalculateCentroid(ProcessBlock):
    """Calculate intensity-weighted centroid within a configured lambda range."""

    type_name: ClassVar[str] = "spectroscopy.calculate_centroid"
    name: ClassVar[str] = "Calculate Centroid"
    algorithm: ClassVar[str] = "calculate_centroid"
    description: ClassVar[str] = "Calculate the intensity-weighted centroid for each spectrum."
    subcategory: ClassVar[str] = "spectroscopy-features"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="spectra", accepted_types=[Spectrum], is_collection=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = _FEATURE_OUTPUT_PORT
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "lambda_min": {"type": "number"},
            "lambda_max": {"type": "number"},
        },
        "required": ["lambda_min", "lambda_max"],
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        lambda_min, lambda_max = config_range(config)
        rows: list[dict[str, Any]] = []
        for spectrum in unpack_spectra_collection(inputs["spectra"]):
            arrays = spectrum_arrays(spectrum)
            window = window_with_interpolated_bounds(arrays.lambdas, arrays.intensities, lambda_min, lambda_max)
            if window.lambdas.size < 2:
                centroid = None
                status = "empty_range"
            else:
                denominator = float(np.trapezoid(window.intensities, window.lambdas))
                if not np.isfinite(denominator) or np.isclose(denominator, 0.0):
                    centroid = None
                    status = "unusable_denominator"
                else:
                    numerator = float(np.trapezoid(window.lambdas * window.intensities, window.lambdas))
                    centroid = numerator / denominator
                    status = "success"
            rows.append(
                {
                    "spectrum_id": spectrum_id(spectrum),
                    "lambda_min": float(lambda_min),
                    "lambda_max": float(lambda_max),
                    "centroid_lambda": centroid,
                    "status": status,
                }
            )
        table = make_dataframe(rows, ["spectrum_id", "lambda_min", "lambda_max", "centroid_lambda", "status"])
        return {"features": Collection([table], item_type=DataFrame)}


class CalculateRatio(ProcessBlock):
    """Calculate a peak-to-peak intensity ratio."""

    type_name: ClassVar[str] = "spectroscopy.calculate_ratio"
    name: ClassVar[str] = "Calculate Ratio"
    algorithm: ClassVar[str] = "calculate_ratio"
    description: ClassVar[str] = "Calculate numerator peak intensity divided by denominator peak intensity."
    subcategory: ClassVar[str] = "spectroscopy-features"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="spectra", accepted_types=[Spectrum], is_collection=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = _FEATURE_OUTPUT_PORT
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "numerator_peak": {"type": ["number", "object"]},
            "denominator_peak": {"type": ["number", "object"]},
            "interpolation": {
                "type": "string",
                "enum": ["linear", "nearest", "none"],
                "default": "linear",
            },
        },
        "required": ["numerator_peak", "denominator_peak"],
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        numerator_definition = config.get("numerator_peak")
        denominator_definition = config.get("denominator_peak")
        interpolation = config.get("interpolation", "linear")
        rows: list[dict[str, Any]] = []
        for spectrum in unpack_spectra_collection(inputs["spectra"]):
            arrays = spectrum_arrays(spectrum)
            numerator = measure_peak(
                arrays.lambdas,
                arrays.intensities,
                numerator_definition,
                interpolation=interpolation,
            )
            denominator = measure_peak(
                arrays.lambdas,
                arrays.intensities,
                denominator_definition,
                interpolation=interpolation,
            )
            ratio, status = _ratio_status(numerator, denominator)
            rows.append(
                {
                    "spectrum_id": spectrum_id(spectrum),
                    "numerator_lambda": numerator.coordinate,
                    "numerator_intensity": numerator.intensity,
                    "denominator_lambda": denominator.coordinate,
                    "denominator_intensity": denominator.intensity,
                    "ratio": ratio,
                    "status": status,
                }
            )
        columns = [
            "spectrum_id",
            "numerator_lambda",
            "numerator_intensity",
            "denominator_lambda",
            "denominator_intensity",
            "ratio",
            "status",
        ]
        return {"features": Collection([make_dataframe(rows, columns)], item_type=DataFrame)}


class FindPeaks(ProcessBlock):
    """Detect and select peaks within optional lambda bounds."""

    type_name: ClassVar[str] = "spectroscopy.find_peaks"
    name: ClassVar[str] = "Find Peaks"
    algorithm: ClassVar[str] = "find_peaks"
    description: ClassVar[str] = "Detect local maxima and emit selected peak measurements."
    subcategory: ClassVar[str] = "spectroscopy-features"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="spectra", accepted_types=[Spectrum], is_collection=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = _FEATURE_OUTPUT_PORT
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "lambda_min": {"type": "number"},
            "lambda_max": {"type": "number"},
            "min_height": {"type": "number"},
            "min_prominence": {"type": "number", "default": 0.0},
            "target_rank": {"type": "integer", "minimum": 1, "default": 1},
        },
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        rows: list[dict[str, Any]] = []
        for spectrum in unpack_spectra_collection(inputs["spectra"]):
            arrays = spectrum_arrays(spectrum)
            peak = _selected_peak(arrays.lambdas, arrays.intensities, config)
            rows.append({"spectrum_id": spectrum_id(spectrum), **peak})
        columns = [
            "spectrum_id",
            "peak_lambda",
            "peak_intensity",
            "peak_rank",
            "peak_count",
            "prominence",
            "lambda_min",
            "lambda_max",
            "status",
        ]
        return {"features": Collection([make_dataframe(rows, columns)], item_type=DataFrame)}


def _intensity_definition(config: BlockConfig) -> Any:
    if config.get("target_peak") is not None:
        return config.get("target_peak")
    if config.get("target_lambda") is not None:
        return config.get("target_lambda")
    if config.get("coordinate") is not None:
        return config.get("coordinate")
    if config.get("lambda_min") is not None and config.get("lambda_max") is not None:
        return {"lambda_min": config.get("lambda_min"), "lambda_max": config.get("lambda_max")}
    return None


def _ratio_status(numerator: PeakMeasurement, denominator: PeakMeasurement) -> tuple[float | None, str]:
    if numerator.status != "success":
        return None, f"numerator_{numerator.status}"
    if denominator.status != "success":
        return None, f"denominator_{denominator.status}"
    if denominator.intensity is None or not np.isfinite(denominator.intensity):
        return None, "unusable_denominator"
    if np.isclose(float(denominator.intensity), 0.0):
        return None, "zero_denominator"
    assert numerator.intensity is not None
    return float(numerator.intensity) / float(denominator.intensity), "success"


def _selected_peak(lambdas: np.ndarray, intensities: np.ndarray, config: BlockConfig) -> dict[str, Any]:
    lambda_min = config.get("lambda_min")
    lambda_max = config.get("lambda_max")
    min_height = config.get("min_height")
    min_prominence = float(config.get("min_prominence", 0.0) or 0.0)
    target_rank = int(config.get("target_rank", 1) or 1)
    if target_rank < 1:
        raise ValueError("target_rank must be >= 1.")

    mask = np.isfinite(lambdas) & np.isfinite(intensities)
    if lambda_min is not None and lambda_max is not None:
        mask &= range_mask(lambdas, float(lambda_min), float(lambda_max))
    x = lambdas[mask]
    y = intensities[mask]
    if x.size < 3:
        return _peak_row(None, None, target_rank, 0, None, lambda_min, lambda_max, "no_peaks")

    peaks = _find_local_maxima(y)
    if min_height is not None:
        peaks = [idx for idx in peaks if y[idx] >= float(min_height)]

    scored: list[tuple[int, float]] = []
    for idx in peaks:
        left = float(y[idx] - y[idx - 1]) if idx > 0 else 0.0
        right = float(y[idx] - y[idx + 1]) if idx < y.size - 1 else 0.0
        prominence = min(left, right)
        if prominence >= min_prominence:
            scored.append((idx, prominence))

    scored.sort(key=lambda item: (-float(y[item[0]]), float(x[item[0]])))
    if len(scored) < target_rank:
        return _peak_row(None, None, target_rank, len(scored), None, lambda_min, lambda_max, "no_peaks")

    selected_idx, prominence = scored[target_rank - 1]
    return _peak_row(
        float(x[selected_idx]),
        float(y[selected_idx]),
        target_rank,
        len(scored),
        float(prominence),
        lambda_min,
        lambda_max,
        "success",
    )


def _find_local_maxima(y: np.ndarray) -> list[int]:
    maxima: list[int] = []
    for idx in range(1, y.size - 1):
        if y[idx] > y[idx - 1] and y[idx] >= y[idx + 1]:
            maxima.append(idx)
    return maxima


def _peak_row(
    peak_lambda: float | None,
    peak_intensity: float | None,
    peak_rank: int,
    peak_count: int,
    prominence: float | None,
    lambda_min: Any,
    lambda_max: Any,
    status: str,
) -> dict[str, Any]:
    return {
        "peak_lambda": peak_lambda,
        "peak_intensity": peak_intensity,
        "peak_rank": peak_rank,
        "peak_count": peak_count,
        "prominence": prominence,
        "lambda_min": float(lambda_min) if lambda_min is not None else None,
        "lambda_max": float(lambda_max) if lambda_max is not None else None,
        "status": status,
    }


__all__ = [
    "CalculateAUC",
    "CalculateCentroid",
    "CalculateRatio",
    "ExtractIntensity",
    "FindPeaks",
]
