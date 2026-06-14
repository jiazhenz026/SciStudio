"""Spectral unmixing blocks for the spectroscopy package."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, ClassVar, cast

import numpy as np
import pandas as pd

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy.blocks.library_matching import (
    _spectrum_vector,
    _SpectrumVector,
)
from scistudio_blocks_spectroscopy.types import Spectrum

_UNMIXING_METHODS = (
    "least_squares",
    "non_negative_least_squares",
    "sum_to_one_non_negative_least_squares",
)


@dataclass(frozen=True)
class _SolveResult:
    coefficients: np.ndarray
    residual: np.ndarray
    status: str
    message: str


class SpectralUnmixing(ProcessBlock):
    """Fit sample spectra as linear combinations of reference spectra."""

    name: ClassVar[str] = "Spectral Unmixing"
    type_name: ClassVar[str] = "spectroscopy.spectral_unmixing"
    description: ClassVar[str] = "Estimate reference component coefficients for each sample spectrum."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "analysis"
    algorithm: ClassVar[str] = "linear_spectral_unmixing"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="spectra",
            accepted_types=[Spectrum],
            is_collection=True,
            description="Sample spectra to unmix.",
        ),
        InputPort(
            name="references",
            accepted_types=[Spectrum],
            is_collection=True,
            description="Reference component spectra.",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="coefficients",
            accepted_types=[DataFrame],
            description="Wide coefficient table with one row per sample spectrum.",
        ),
        OutputPort(
            name="fit_quality",
            accepted_types=[DataFrame],
            description="Per-sample residual and fit-quality diagnostics.",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": list(_UNMIXING_METHODS),
                "default": "least_squares",
                "title": "Unmixing Method",
            },
            "component_label_source": {
                "type": "string",
                "default": "spectrum_id",
                "title": "Component Label Source",
            },
            "grid_policy": {
                "type": "string",
                "enum": ["error", "interpolate_references_to_sample"],
                "default": "error",
                "title": "Grid Compatibility Policy",
            },
            "condition_threshold": {
                "type": "number",
                "default": 10000000000.0,
                "exclusiveMinimum": 0,
                "title": "Ill-Conditioned Threshold",
            },
        },
        "required": ["method", "component_label_source"],
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        method = _validated_method(config.get("method", "least_squares"))
        sample_items = _require_collection(inputs.get("spectra"), "spectra")
        reference_items = _require_collection(inputs.get("references"), "references")
        if not reference_items:
            raise ValueError("SpectralUnmixing: references must contain at least one Spectrum")

        samples = [_unmixing_spectrum_vector(item) for item in sample_items]
        references = [_unmixing_spectrum_vector(item) for item in reference_items]
        coefficient_columns = _coefficient_columns(references, str(config.get("component_label_source", "spectrum_id")))

        coefficient_rows: list[dict[str, Any]] = []
        quality_rows: list[dict[str, Any]] = []
        for sample in samples:
            design = _design_matrix_for_sample(sample, references, config)
            condition_number = _condition_number(design)
            ill_conditioned = _is_ill_conditioned(condition_number, config)
            solve = _solve(design, sample.intensities, method)

            status = solve.status
            message = solve.message
            if status == "ok" and ill_conditioned:
                status = "ill_conditioned"
                message = "reference design matrix is ill-conditioned"

            coefficient_row: dict[str, Any] = {
                "spectrum_id": sample.spectrum_id,
                "method": method,
            }
            for column, value in zip(coefficient_columns, solve.coefficients, strict=True):
                coefficient_row[column] = float(value) if np.isfinite(value) else np.nan
            coefficient_rows.append(coefficient_row)

            residual_norm, rmse, r2 = _quality_metrics(sample.intensities, solve.residual)
            quality_rows.append(
                {
                    "spectrum_id": sample.spectrum_id,
                    "method": method,
                    "status": status,
                    "residual_norm": residual_norm,
                    "rmse": rmse,
                    "n_components": len(references),
                    "r2": r2,
                    "condition_number": condition_number,
                    "message": message,
                }
            )

        coefficient_columns_full = ["spectrum_id", "method", *coefficient_columns]
        quality_columns = [
            "spectrum_id",
            "method",
            "status",
            "residual_norm",
            "rmse",
            "n_components",
            "r2",
            "condition_number",
            "message",
        ]
        return {
            "coefficients": _dataframe_collection(coefficient_rows, coefficient_columns_full),
            "fit_quality": _dataframe_collection(quality_rows, quality_columns),
        }


def _validated_method(method: Any) -> str:
    value = str(method)
    if value not in _UNMIXING_METHODS:
        accepted = ", ".join(_UNMIXING_METHODS)
        raise ValueError(f"SpectralUnmixing: method must be one of {accepted}; got {value!r}")
    return value


def _solve(design: np.ndarray, sample: np.ndarray, method: str) -> _SolveResult:
    if not np.all(np.isfinite(design)) or not np.all(np.isfinite(sample)):
        coefficients = np.full(design.shape[1], np.nan, dtype=float)
        return _SolveResult(coefficients, np.full_like(sample, np.nan), "failed", "input contains non-finite values")

    try:
        if method == "least_squares":
            coefficients, *_ = np.linalg.lstsq(design, sample, rcond=None)
        elif method == "non_negative_least_squares":
            coefficients = _non_negative_least_squares(design, sample)
        elif method == "sum_to_one_non_negative_least_squares":
            coefficients = _sum_to_one_non_negative_least_squares(design, sample)
        else:
            raise AssertionError(f"unexpected method {method!r}")
    except Exception as exc:
        coefficients = np.full(design.shape[1], np.nan, dtype=float)
        return _SolveResult(coefficients, np.full_like(sample, np.nan), "failed", str(exc))

    residual = sample - design @ coefficients
    return _SolveResult(coefficients.astype(float), residual.astype(float), "ok", "")


def _non_negative_least_squares(design: np.ndarray, sample: np.ndarray) -> np.ndarray:
    try:
        from scipy.optimize import nnls

        coefficients, _residual = nnls(design, sample)
        return cast(np.ndarray, coefficients)
    except ImportError:
        coefficients, *_ = np.linalg.lstsq(design, sample, rcond=None)
        clipped = np.maximum(coefficients, 0.0)
        return cast(np.ndarray, clipped.astype(float, copy=False))


def _sum_to_one_non_negative_least_squares(design: np.ndarray, sample: np.ndarray) -> np.ndarray:
    n_components = design.shape[1]
    initial = np.full(n_components, 1.0 / n_components, dtype=float)
    try:
        from scipy.optimize import minimize

        scipy_minimize = cast(Any, minimize)
        result = scipy_minimize(
            lambda coeffs: float(np.sum((design @ coeffs - sample) ** 2)),
            initial,
            method="SLSQP",
            bounds=[(0.0, None)] * n_components,
            constraints=({"type": "eq", "fun": lambda coeffs: float(np.sum(coeffs) - 1.0)},),
            options={"ftol": 1e-12, "maxiter": 500},
        )
        if not result.success:
            raise ValueError(result.message)
        return cast(np.ndarray, result.x)
    except ImportError:
        coefficients, *_ = np.linalg.lstsq(design, sample, rcond=None)
        return _project_to_simplex(coefficients)


def _project_to_simplex(values: np.ndarray) -> np.ndarray:
    ordered = np.sort(values)[::-1]
    cumulative = np.cumsum(ordered)
    rho_candidates = ordered * np.arange(1, len(ordered) + 1) > (cumulative - 1.0)
    if not np.any(rho_candidates):
        return np.full(values.size, 1.0 / values.size)
    rho = int(np.nonzero(rho_candidates)[0][-1])
    theta = (cumulative[rho] - 1.0) / float(rho + 1)
    projected = np.maximum(values - theta, 0.0)
    return cast(np.ndarray, projected.astype(float, copy=False))


def _design_matrix_for_sample(
    sample: _SpectrumVector, references: list[_SpectrumVector], config: BlockConfig
) -> np.ndarray:
    columns: list[np.ndarray] = []
    grid_policy = str(config.get("grid_policy", "error"))
    for reference in references:
        if _same_grid(sample.lambda_values, reference.lambda_values):
            columns.append(reference.intensities)
            continue
        if grid_policy == "interpolate_references_to_sample":
            columns.append(_interpolate_reference(reference, sample.lambda_values))
            continue
        raise ValueError(
            "SpectralUnmixing: sample "
            f"{sample.spectrum_id!r} and reference {reference.spectrum_id!r} have incompatible lambda grids"
        )
    return np.column_stack(columns).astype(float)


def _interpolate_reference(reference: _SpectrumVector, target_grid: np.ndarray) -> np.ndarray:
    source_grid = reference.lambda_values
    if np.min(target_grid) < np.min(source_grid) or np.max(target_grid) > np.max(source_grid):
        raise ValueError(
            f"SpectralUnmixing: cannot interpolate reference {reference.spectrum_id!r}; "
            "sample grid extends outside reference grid"
        )
    interpolated = np.interp(target_grid, source_grid, reference.intensities)
    return cast(np.ndarray, interpolated.astype(float, copy=False))


def _same_grid(left: np.ndarray, right: np.ndarray) -> bool:
    return left.shape == right.shape and bool(np.allclose(left, right))


def _condition_number(design: np.ndarray) -> float:
    try:
        value = float(np.linalg.cond(design))
    except Exception:
        return float("inf")
    return value


def _is_ill_conditioned(condition_number: float, config: BlockConfig) -> bool:
    threshold = float(config.get("condition_threshold", 1e10))
    return not np.isfinite(condition_number) or condition_number > threshold


def _quality_metrics(sample: np.ndarray, residual: np.ndarray) -> tuple[float, float, float]:
    if not np.all(np.isfinite(residual)):
        return np.nan, np.nan, np.nan
    residual_norm = float(np.linalg.norm(residual))
    rmse = float(np.sqrt(np.mean(residual**2))) if residual.size else np.nan
    centered = sample - float(np.mean(sample)) if sample.size else sample
    total = float(np.sum(centered**2))
    r2 = float(1.0 - np.sum(residual**2) / total) if total > 0.0 else np.nan
    return residual_norm, rmse, r2


def _coefficient_columns(references: list[_SpectrumVector], label_source: str) -> list[str]:
    base_names: list[str] = []
    for index, reference in enumerate(references, start=1):
        label = _reference_label(reference, label_source)
        base_names.append(_safe_column_base(label, index))

    counts: dict[str, int] = {}
    columns: list[str] = []
    for base in base_names:
        counts[base] = counts.get(base, 0) + 1
        suffix = "" if counts[base] == 1 else f"_{counts[base]}"
        columns.append(f"{base}{suffix}")
    return columns


def _reference_label(reference: _SpectrumVector, label_source: str) -> Any:
    if label_source == "spectrum_id":
        return reference.spectrum_id
    if label_source in reference.metadata:
        return reference.metadata[label_source]
    return reference.spectrum_id


def _safe_column_base(label: Any, index: int) -> str:
    text = str(label).strip().lower()
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_")
    if not text:
        text = f"component_{index}"
    return f"coeff_{text}"


def _require_collection(payload: Any, name: str) -> list[Any]:
    if not isinstance(payload, Collection):
        raise ValueError(f"SpectralUnmixing: input {name!r} must be a Collection[Spectrum]")
    return list(payload)


def _unmixing_spectrum_vector(item: Any) -> _SpectrumVector:
    try:
        return _spectrum_vector(item)
    except ValueError as exc:
        message = str(exc).replace("MatchSpectralLibrary", "SpectralUnmixing")
        raise ValueError(message) from exc


def _dataframe_collection(rows: list[dict[str, Any]], columns: list[str]) -> Collection:
    frame = pd.DataFrame(rows, columns=columns)
    result = DataFrame(columns=list(frame.columns), row_count=len(frame))
    result._data = frame
    return Collection(items=[result], item_type=DataFrame)


__all__ = ["SpectralUnmixing"]
