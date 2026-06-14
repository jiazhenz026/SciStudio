"""Spectroscopy reference correction blocks (FR-095..FR-103).

Two blocks operating on ``Collection[Spectrum]`` plus one reference
``Spectrum``: :class:`SubtractReferenceSpectrum` and
:class:`DivideByReferenceSpectrum`. They preserve item count/order,
``spectrum_id``, metadata, and each sample's ``lambda`` grid (FR-099); they
default to an error on grid mismatch (FR-102) and (for division) on reference
zeros (FR-103).
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.types import Spectrum

_SPECTRA_INPUT = InputPort(
    name="spectra",
    accepted_types=[Spectrum],
    is_collection=True,
    required=True,
    description="Sample spectra to correct.",
)
_REFERENCE_INPUT = InputPort(
    name="reference",
    accepted_types=[Spectrum],
    required=True,
    description="Single reference spectrum.",
)
_CORRECTED_OUTPUT = OutputPort(name="corrected", accepted_types=[Spectrum], is_collection=True)

_GRID_POLICY_SCHEMA: dict[str, Any] = {
    "type": "string",
    "enum": ["error", "interpolate_reference_to_sample"],
    "default": "error",
    "title": "Reference grid policy",
}

_GRID_POLICIES = frozenset({"error", "interpolate_reference_to_sample"})
_ZERO_POLICIES = frozenset({"error", "nan", "clip"})


def _aligned_reference_intensity(
    block: str,
    sample_lambda: np.ndarray,
    sample_intensity: np.ndarray,
    reference_lambda: np.ndarray,
    reference_intensity: np.ndarray,
    grid_policy: str,
) -> np.ndarray:
    """Return reference intensity aligned to the sample's ``lambda`` grid.

    ``grid_policy == "error"`` (the default, FR-102) raises ``ValueError`` when
    the sample and reference grids differ. ``interpolate_reference_to_sample``
    resamples the reference onto the sample grid with :func:`numpy.interp`.
    """
    if _support.grids_close(sample_lambda, reference_lambda):
        return reference_intensity
    if grid_policy == "error":
        raise ValueError(
            f"{block}: sample and reference 'lambda' grids differ; set "
            "reference_grid_policy='interpolate_reference_to_sample' to resample the reference."
        )
    # interpolate_reference_to_sample (explicit opt-in).
    order = np.argsort(reference_lambda)
    return np.asarray(
        np.interp(sample_lambda, reference_lambda[order], reference_intensity[order]),
        dtype=np.float64,
    )


class SubtractReferenceSpectrum(ProcessBlock):
    """Subtract one reference spectrum from each sample (FR-100)."""

    type_name: ClassVar[str] = "spectroscopy.subtract_reference_spectrum"
    name: ClassVar[str] = "Subtract Reference Spectrum"
    description: ClassVar[str] = "Subtract a reference spectrum's intensity from each sample spectrum."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "reference_correction"
    algorithm: ClassVar[str] = "subtract_reference_spectrum"

    input_ports: ClassVar[list[InputPort]] = [_SPECTRA_INPUT, _REFERENCE_INPUT]
    output_ports: ClassVar[list[OutputPort]] = [_CORRECTED_OUTPUT]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"reference_grid_policy": _GRID_POLICY_SCHEMA},
        "required": ["reference_grid_policy"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Subtract the reference from each sample (FR-099, FR-100, FR-102).

        Implementation plan:
          1. reference = inputs['reference']; spectra = inputs['spectra'].
          2. Per sample: if grids differ, apply reference_grid_policy — 'error'
             fail with a clear grid-mismatch diagnostic, or
             'interpolate_reference_to_sample' (numpy.interp ref onto sample grid).
          3. corrected_intensity = sample_intensity - reference_intensity; emit
             via _support.derive_spectrum preserving spectrum_id/meta/grid.
        Edge cases: grid mismatch under each policy; single sample; empty input.
        Test plan: test_reference_correction_blocks.py::test_subtract_same_grid,
          ::test_subtract_errors_on_grid_mismatch.
        """
        block = self.name
        grid_policy = str(config.get("reference_grid_policy", "error"))
        if grid_policy not in _GRID_POLICIES:
            raise ValueError(
                f"{block}: reference_grid_policy must be one of {sorted(_GRID_POLICIES)}, got {grid_policy!r}"
            )

        spectra = _support.coerce_spectra(inputs.get("spectra"), block=block, port="spectra")
        reference = _support.coerce_single_spectrum(inputs.get("reference"), block=block, port="reference")
        ref_lambda, ref_intensity = _support.spectrum_arrays(reference)

        corrected: list[Spectrum] = []
        for sample in spectra:
            sample_lambda, sample_intensity = _support.spectrum_arrays(sample)
            aligned_ref = _aligned_reference_intensity(
                block, sample_lambda, sample_intensity, ref_lambda, ref_intensity, grid_policy
            )
            corrected_intensity = sample_intensity - aligned_ref
            derived = _support.derive_spectrum(sample, intensity_values=corrected_intensity)
            corrected.append(cast(Spectrum, self._auto_flush(derived)))

        return {"corrected": _support.spectra_collection(corrected)}


class DivideByReferenceSpectrum(ProcessBlock):
    """Divide each sample by one reference spectrum (FR-101, FR-103)."""

    type_name: ClassVar[str] = "spectroscopy.divide_by_reference_spectrum"
    name: ClassVar[str] = "Divide by Reference Spectrum"
    description: ClassVar[str] = "Divide each sample spectrum's intensity by a reference spectrum."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "reference_correction"
    algorithm: ClassVar[str] = "divide_by_reference_spectrum"

    input_ports: ClassVar[list[InputPort]] = [_SPECTRA_INPUT, _REFERENCE_INPUT]
    output_ports: ClassVar[list[OutputPort]] = [_CORRECTED_OUTPUT]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "reference_grid_policy": _GRID_POLICY_SCHEMA,
            "zero_policy": {
                "type": "string",
                "enum": ["error", "nan", "clip"],
                "default": "error",
                "title": "Reference-zero policy",
            },
        },
        "required": ["reference_grid_policy", "zero_policy"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Divide each sample by the reference (FR-101, FR-102, FR-103).

        Implementation plan:
          1. Apply reference_grid_policy as in SubtractReferenceSpectrum.
          2. corrected = sample_intensity / reference_intensity; handle reference
             zeros per zero_policy — 'error' fail, 'nan' emit NaN, 'clip' clip the
             denominator (FR-103); default is 'error'.
          3. Emit via _support.derive_spectrum preserving identity/grid.
        Edge cases: reference zeros under each policy; grid mismatch; empty input.
        Test plan: test_reference_correction_blocks.py::test_divide_errors_on_zero_default,
          ::test_divide_nan_policy.
        """
        block = self.name
        grid_policy = str(config.get("reference_grid_policy", "error"))
        if grid_policy not in _GRID_POLICIES:
            raise ValueError(
                f"{block}: reference_grid_policy must be one of {sorted(_GRID_POLICIES)}, got {grid_policy!r}"
            )
        zero_policy = str(config.get("zero_policy", "error"))
        if zero_policy not in _ZERO_POLICIES:
            raise ValueError(f"{block}: zero_policy must be one of {sorted(_ZERO_POLICIES)}, got {zero_policy!r}")

        spectra = _support.coerce_spectra(inputs.get("spectra"), block=block, port="spectra")
        reference = _support.coerce_single_spectrum(inputs.get("reference"), block=block, port="reference")
        ref_lambda, ref_intensity = _support.spectrum_arrays(reference)

        corrected: list[Spectrum] = []
        for sample in spectra:
            sample_lambda, sample_intensity = _support.spectrum_arrays(sample)
            aligned_ref = _aligned_reference_intensity(
                block, sample_lambda, sample_intensity, ref_lambda, ref_intensity, grid_policy
            )
            corrected_intensity = self._divide(block, sample_intensity, aligned_ref, zero_policy)
            derived = _support.derive_spectrum(sample, intensity_values=corrected_intensity)
            corrected.append(cast(Spectrum, self._auto_flush(derived)))

        return {"corrected": _support.spectra_collection(corrected)}

    @staticmethod
    def _divide(block: str, numerator: np.ndarray, denominator: np.ndarray, zero_policy: str) -> np.ndarray:
        """Apply the configured zero-handling policy and divide (FR-103)."""
        zero_mask = denominator == 0.0
        if zero_mask.any():
            if zero_policy == "error":
                raise ValueError(
                    f"{block}: reference intensity contains zero values at used coordinates; "
                    "set zero_policy='nan' or 'clip' to handle them explicitly."
                )
            if zero_policy == "clip":
                # Replace zeros with the smallest positive float so the quotient is finite.
                denominator = np.where(zero_mask, np.finfo(np.float64).tiny, denominator)
                with np.errstate(divide="ignore", invalid="ignore"):
                    return np.asarray(numerator / denominator, dtype=np.float64)
            # zero_policy == "nan": emit NaN where the reference is zero.
            with np.errstate(divide="ignore", invalid="ignore"):
                quotient = np.asarray(numerator / denominator, dtype=np.float64)
            quotient[zero_mask] = np.nan
            return quotient
        return np.asarray(numerator / denominator, dtype=np.float64)


BLOCKS: list[type] = [SubtractReferenceSpectrum, DivideByReferenceSpectrum]

__all__ = ["BLOCKS", "DivideByReferenceSpectrum", "SubtractReferenceSpectrum"]
