"""Spectroscopy spectral unmixing block (FR-104..FR-112).

One block, :class:`SpectralUnmixing`. It fits each sample spectrum as a linear
combination of reference spectra and emits a wide ``coefficients`` table plus a
``fit_quality`` table. It does NOT output fitted/residual/component spectra or a
new result type in this draft (FR-112).

``scipy.optimize.nnls`` is lazy-imported inside the run body for the
non-negative methods; unconstrained least squares uses ``numpy.linalg.lstsq``.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.types import Spectrum

_METHODS = frozenset(
    {
        "least_squares",
        "non_negative_least_squares",
        "sum_to_one_non_negative_least_squares",
    }
)
_GRID_POLICIES = frozenset({"error", "interpolate_references_to_sample"})

#: Reserved coefficient-table columns that component labels must never collide with.
_RESERVED_COLUMNS = ("spectrum_id", "method")

_STATUS_SUCCESS = "success"
_STATUS_ILL_CONDITIONED = "ill_conditioned"
_STATUS_FAILED = "failed"
_STATUS_CONSTRAINT_NOT_SATISFIED = "constraint_not_satisfied"

#: Large weight for the sum-to-one equality row in the augmented NNLS.
_SUM_TO_ONE_WEIGHT = 1.0e6
_SUM_TO_ONE_TOLERANCE = 1.0e-6


class SpectralUnmixing(ProcessBlock):
    """Linearly unmix sample spectra into reference-component coefficients."""

    type_name: ClassVar[str] = "spectroscopy.spectral_unmixing"
    name: ClassVar[str] = "Spectral Unmixing"
    description: ClassVar[str] = "Fit each sample as a linear mix of references; emit coefficients + fit quality."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "unmixing"
    algorithm: ClassVar[str] = "spectral_unmixing"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="spectra",
            accepted_types=[Spectrum],
            is_collection=True,
            required=True,
            description="Sample spectra to unmix.",
        ),
        InputPort(
            name="references",
            accepted_types=[Spectrum],
            is_collection=True,
            required=True,
            description="Reference component spectra.",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="coefficients", accepted_types=[DataFrame]),
        OutputPort(name="fit_quality", accepted_types=[DataFrame]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": [
                    "least_squares",
                    "non_negative_least_squares",
                    "sum_to_one_non_negative_least_squares",
                ],
                "default": "least_squares",
                "title": "Unmixing method",
            },
            "component_label_source": {
                "type": "string",
                "default": "spectrum_id",
                "title": "Component label source",
                "description": "Reference field used to name coefficient columns.",
            },
            "grid_policy": {
                "type": "string",
                "enum": ["error", "interpolate_references_to_sample"],
                "default": "error",
                "title": "Grid compatibility policy",
            },
        },
        "required": ["method"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Unmix samples into reference coefficients (FR-104..FR-112).

        Implementation plan:
          1. spectra = inputs['spectra']; references = inputs['references'].
          2. Apply grid_policy: 'error' fail on incompatible grids, else
             numpy.interp references onto each sample grid (FR-111).
          3. Build design matrix A (references as columns); solve per method —
             least_squares: numpy.linalg.lstsq; non_negative_least_squares: lazy
             scipy.optimize.nnls; sum_to_one_nnls: augment with a large-weight
             ones row then nnls.
          4. coefficients: wide DataFrame, one row per sample, columns
             {spectrum_id, method, <one per reference>}; column names generated
             from component_label_source, deterministic/table-safe/collision-free
             (FR-108, FR-109).
          5. fit_quality: one row per sample {spectrum_id, method, status,
             residual_norm, rmse, n_components, r2?} (FR-110).
          6. Return {'coefficients': dataframe_collection(coef_df),
             'fit_quality': dataframe_collection(quality_df)}.
        Edge cases: duplicate reference labels (dedupe column names); singular A
          (ill_conditioned status); zero references.
        Test plan: test_unmixing_blocks.py::test_unmixing_wide_coefficients,
          ::test_unmixing_collision_free_columns,
          ::test_unmixing_fit_quality_rows.
        """
        block = self.name
        method = str(config.get("method", "least_squares"))
        if method not in _METHODS:
            raise ValueError(f"{block}: method must be one of {sorted(_METHODS)}, got {method!r}")
        grid_policy = str(config.get("grid_policy", "error"))
        if grid_policy not in _GRID_POLICIES:
            raise ValueError(f"{block}: grid_policy must be one of {sorted(_GRID_POLICIES)}, got {grid_policy!r}")
        label_source = str(config.get("component_label_source", "spectrum_id"))

        spectra = _support.coerce_spectra(inputs.get("spectra"), block=block, port="spectra")
        references = _support.coerce_spectra(inputs.get("references"), block=block, port="references")

        reference_arrays = [_support.spectrum_arrays(ref) for ref in references]
        component_labels = _component_labels(references, label_source)
        n_components = len(references)

        nnls = None
        if method in {"non_negative_least_squares", "sum_to_one_non_negative_least_squares"}:
            from scipy.optimize import nnls as _nnls  # lazy import (scipy-free package import)

            nnls = _nnls

        coef_rows: list[dict[str, Any]] = []
        quality_rows: list[dict[str, Any]] = []
        for sample in spectra:
            sample_lambda, sample_intensity = _support.spectrum_arrays(sample)
            design = self._design_matrix(block, sample_lambda, reference_arrays, grid_policy)
            coeffs, quality = _solve(method, design, sample_intensity, nnls)

            coef_row: dict[str, Any] = {"spectrum_id": sample.spectrum_id, "method": method}
            for label, value in zip(component_labels, coeffs, strict=True):
                coef_row[label] = float(value)
            coef_rows.append(coef_row)

            quality_rows.append(
                {
                    "spectrum_id": sample.spectrum_id,
                    "method": method,
                    "status": quality["status"],
                    "residual_norm": quality["residual_norm"],
                    "rmse": quality["rmse"],
                    "n_components": n_components,
                    "r2": quality["r2"],
                    "condition_number": quality["condition_number"],
                    "message": quality["message"],
                }
            )

        coef_columns = ["spectrum_id", "method", *component_labels]
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
        coef_df = _support.dataframe_from_rows(coef_rows, columns=coef_columns)
        quality_df = _support.dataframe_from_rows(quality_rows, columns=quality_columns)
        return {
            "coefficients": _support.dataframe_collection(coef_df),
            "fit_quality": _support.dataframe_collection(quality_df),
        }

    @staticmethod
    def _design_matrix(
        block: str,
        sample_lambda: np.ndarray,
        reference_arrays: list[tuple[np.ndarray, np.ndarray]],
        grid_policy: str,
    ) -> np.ndarray:
        """Build the design matrix (references as columns) on the sample grid (FR-111)."""
        columns: list[np.ndarray] = []
        for ref_lambda, ref_intensity in reference_arrays:
            if _support.grids_close(sample_lambda, ref_lambda):
                columns.append(ref_intensity)
                continue
            if grid_policy == "error":
                raise ValueError(
                    f"{block}: sample and reference 'lambda' grids differ; set "
                    "grid_policy='interpolate_references_to_sample' to resample references."
                )
            order = np.argsort(ref_lambda)
            columns.append(
                np.asarray(np.interp(sample_lambda, ref_lambda[order], ref_intensity[order]), dtype=np.float64)
            )
        if not columns:
            return np.empty((sample_lambda.shape[0], 0), dtype=np.float64)
        return np.column_stack(columns)


# ---------------------------------------------------------------------------
# Solvers
# ---------------------------------------------------------------------------


def _solve(
    method: str,
    design: np.ndarray,
    target: np.ndarray,
    nnls: Any,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Solve one unmixing problem and report fit quality (FR-110)."""
    n_components = design.shape[1]
    target = np.asarray(target, dtype=np.float64)

    if n_components == 0:
        quality = _quality(target, np.zeros_like(target), status=_STATUS_FAILED, message="no reference components")
        return np.zeros(0, dtype=np.float64), quality

    condition_number = _condition_number(design)
    status = _STATUS_SUCCESS
    message = ""
    try:
        if method == "least_squares":
            coeffs, _, _, _ = np.linalg.lstsq(design, target, rcond=None)
        elif method == "non_negative_least_squares":
            coeffs, _ = nnls(design, target)
        else:  # sum_to_one_non_negative_least_squares
            augmented_design = np.vstack([design, np.full((1, n_components), _SUM_TO_ONE_WEIGHT)])
            augmented_target = np.concatenate([target, [_SUM_TO_ONE_WEIGHT]])
            coeffs, _ = nnls(augmented_design, augmented_target)
    except Exception as exc:  # solver failure -> non-success status, no crash.
        quality = _quality(
            target,
            np.zeros_like(target),
            status=_STATUS_FAILED,
            message=f"{type(exc).__name__}: {exc}",
            condition_number=condition_number,
        )
        return np.zeros(n_components, dtype=np.float64), quality

    coeffs = np.asarray(coeffs, dtype=np.float64)
    if condition_number is not None and not np.isfinite(condition_number):
        status = _STATUS_ILL_CONDITIONED
        message = "singular design matrix"
    elif condition_number is not None and condition_number > 1.0e12:
        status = _STATUS_ILL_CONDITIONED
        message = "design matrix is ill-conditioned"
    if method == "sum_to_one_non_negative_least_squares":
        coefficient_sum = float(np.sum(coeffs))
        if not np.isfinite(coefficient_sum) or abs(coefficient_sum - 1.0) > _SUM_TO_ONE_TOLERANCE:
            detail = (
                f"sum-to-one constraint not satisfied: sum={coefficient_sum:.12g}, "
                f"tolerance={_SUM_TO_ONE_TOLERANCE:.1e}"
            )
            if status == _STATUS_SUCCESS:
                status = _STATUS_CONSTRAINT_NOT_SATISFIED
                message = detail
            else:
                message = f"{message}; {detail}" if message else detail

    # Reconstruct the fit on the original (un-augmented) design for quality stats.
    fitted = design @ coeffs
    quality = _quality(target, fitted, status=status, message=message, condition_number=condition_number)
    return coeffs, quality


def _quality(
    target: np.ndarray,
    fitted: np.ndarray,
    *,
    status: str,
    message: str,
    condition_number: float | None = None,
) -> dict[str, Any]:
    """Compute residual_norm / rmse / r2 and pack the fit-quality fields (FR-110)."""
    residual = target - fitted
    residual_norm = float(np.linalg.norm(residual))
    rmse = float(np.sqrt(np.mean(residual**2))) if target.size else float("nan")

    total_ss = float(np.sum((target - target.mean()) ** 2)) if target.size else 0.0
    if total_ss > 0.0:
        r2: float | None = float(1.0 - float(np.sum(residual**2)) / total_ss)
    else:
        r2 = None

    return {
        "status": status,
        "residual_norm": residual_norm,
        "rmse": rmse,
        "r2": r2,
        "condition_number": (
            float(condition_number) if condition_number is not None and np.isfinite(condition_number) else None
        ),
        "message": message,
    }


def _condition_number(design: np.ndarray) -> float | None:
    """Return the 2-norm condition number of the design matrix, or ``None``."""
    if design.size == 0:
        return None
    try:
        return float(np.linalg.cond(design))
    except np.linalg.LinAlgError:
        return float("inf")


# ---------------------------------------------------------------------------
# Component column naming (FR-109)
# ---------------------------------------------------------------------------


def _component_labels(references: list[Spectrum], label_source: str) -> list[str]:
    """Generate deterministic, table-safe, collision-free coefficient columns.

    The raw label for each reference comes from ``label_source`` (``spectrum_id``
    or a ``Spectrum.Meta`` field); it is sanitised to a table-safe identifier and
    de-duplicated with numeric suffixes so no two references share a column and
    none collide with the reserved ``spectrum_id`` / ``method`` columns (FR-109).
    """
    raw_labels = [_raw_label(ref, label_source, position) for position, ref in enumerate(references)]
    sanitized = [_sanitize(label, position) for position, label in enumerate(raw_labels)]
    return _dedupe(sanitized)


def _raw_label(reference: Spectrum, label_source: str, position: int) -> str:
    """Resolve the raw label string for one reference from ``label_source``."""
    if label_source == "spectrum_id":
        value: Any = reference.spectrum_id
    else:
        meta = reference.meta
        value = getattr(meta, label_source, None) if isinstance(meta, Spectrum.Meta) else None
    if value is None or str(value).strip() == "":
        return f"component_{position}"
    return str(value)


def _sanitize(label: str, position: int) -> str:
    """Reduce ``label`` to a deterministic, table-safe column token."""
    cleaned = re.sub(r"[^0-9A-Za-z_]+", "_", label).strip("_")
    if not cleaned:
        cleaned = f"component_{position}"
    if cleaned[0].isdigit():
        cleaned = f"c_{cleaned}"
    return cleaned


def _dedupe(labels: list[str]) -> list[str]:
    """Append ``_N`` suffixes so labels are unique and avoid reserved columns."""
    used: set[str] = set(_RESERVED_COLUMNS)
    result: list[str] = []
    for label in labels:
        candidate = label
        suffix = 1
        while candidate in used:
            candidate = f"{label}_{suffix}"
            suffix += 1
        used.add(candidate)
        result.append(candidate)
    return result


BLOCKS: list[type] = [SpectralUnmixing]

__all__ = ["BLOCKS", "SpectralUnmixing"]
