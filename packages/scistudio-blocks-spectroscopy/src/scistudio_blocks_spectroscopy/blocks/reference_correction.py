"""Reference correction blocks for spectroscopy spectra."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio_blocks_spectroscopy.types import Spectrum

from ._spectra import (
    SpectrumArrays,
    interpolate_reference_to_sample,
    make_spectrum_like,
    same_grid,
    spectrum_arrays,
    unpack_reference,
    unpack_spectra_collection,
)

_REFERENCE_GRID_POLICIES = {"error", "interpolate_reference_to_sample"}
_ZERO_POLICIES = {"error", "nan", "zero", "epsilon", "inf"}


class SubtractReferenceSpectrum(ProcessBlock):
    """Subtract one reference spectrum from every sample spectrum."""

    type_name: ClassVar[str] = "spectroscopy.subtract_reference_spectrum"
    name: ClassVar[str] = "Subtract Reference Spectrum"
    algorithm: ClassVar[str] = "subtract_reference_spectrum"
    description: ClassVar[str] = "Subtract one explicit reference spectrum from each input spectrum."
    subcategory: ClassVar[str] = "spectroscopy-reference"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="spectra", accepted_types=[Spectrum], is_collection=True),
        InputPort(name="reference", accepted_types=[Spectrum]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="corrected", accepted_types=[Spectrum]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "reference_grid_policy": {
                "type": "string",
                "enum": sorted(_REFERENCE_GRID_POLICIES),
                "default": "error",
            },
        },
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        samples = unpack_spectra_collection(inputs["spectra"])
        reference = unpack_reference(inputs["reference"])
        reference_arrays = spectrum_arrays(reference)
        policy = _grid_policy(config)
        corrected: list[Spectrum] = []
        for sample in samples:
            sample_arrays = spectrum_arrays(sample)
            reference_intensity = _aligned_reference_intensity(sample_arrays.lambdas, reference_arrays, policy)
            corrected.append(
                make_spectrum_like(
                    sample,
                    sample_arrays.lambdas.tolist(),
                    sample_arrays.intensities - reference_intensity,
                )
            )
        return {"corrected": Collection(cast(list[DataObject], corrected), item_type=Spectrum)}


class DivideByReferenceSpectrum(ProcessBlock):
    """Divide every sample spectrum by one reference spectrum."""

    type_name: ClassVar[str] = "spectroscopy.divide_by_reference_spectrum"
    name: ClassVar[str] = "Divide By Reference Spectrum"
    algorithm: ClassVar[str] = "divide_by_reference_spectrum"
    description: ClassVar[str] = "Divide each input spectrum by one explicit reference spectrum."
    subcategory: ClassVar[str] = "spectroscopy-reference"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="spectra", accepted_types=[Spectrum], is_collection=True),
        InputPort(name="reference", accepted_types=[Spectrum]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="corrected", accepted_types=[Spectrum]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "reference_grid_policy": {
                "type": "string",
                "enum": sorted(_REFERENCE_GRID_POLICIES),
                "default": "error",
            },
            "zero_denominator_policy": {
                "type": "string",
                "enum": sorted(_ZERO_POLICIES),
                "default": "error",
            },
            "epsilon": {"type": "number", "default": 1e-12},
        },
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        samples = unpack_spectra_collection(inputs["spectra"])
        reference = unpack_reference(inputs["reference"])
        reference_arrays = spectrum_arrays(reference)
        grid_policy = _grid_policy(config)
        zero_policy = _zero_policy(config)
        corrected: list[Spectrum] = []
        for sample in samples:
            sample_arrays = spectrum_arrays(sample)
            reference_intensity = _aligned_reference_intensity(sample_arrays.lambdas, reference_arrays, grid_policy)
            denominator = _handle_zero_denominators(reference_intensity, zero_policy, config)
            corrected_intensity = sample_arrays.intensities / denominator
            if zero_policy == "zero":
                corrected_intensity = np.where(np.isclose(reference_intensity, 0.0), 0.0, corrected_intensity)
            corrected.append(make_spectrum_like(sample, sample_arrays.lambdas.tolist(), corrected_intensity.tolist()))
        return {"corrected": Collection(cast(list[DataObject], corrected), item_type=Spectrum)}


def _grid_policy(config: BlockConfig) -> str:
    policy = str(config.get("reference_grid_policy", "error"))
    if policy not in _REFERENCE_GRID_POLICIES:
        raise ValueError("reference_grid_policy must be one of: " + ", ".join(sorted(_REFERENCE_GRID_POLICIES)))
    return policy


def _zero_policy(config: BlockConfig) -> str:
    policy = str(config.get("zero_denominator_policy", config.get("zero_policy", "error")))
    if policy not in _ZERO_POLICIES:
        raise ValueError("zero_denominator_policy must be one of: " + ", ".join(sorted(_ZERO_POLICIES)))
    return policy


def _aligned_reference_intensity(
    sample_lambdas: np.ndarray,
    reference_arrays: SpectrumArrays,
    policy: str,
) -> np.ndarray:
    if same_grid(sample_lambdas, reference_arrays.lambdas):
        return cast(np.ndarray, reference_arrays.intensities.astype(float))
    if policy == "error":
        raise ValueError(
            "Sample and reference lambda grids differ. Set "
            "reference_grid_policy='interpolate_reference_to_sample' to interpolate explicitly."
        )
    return cast(
        np.ndarray,
        interpolate_reference_to_sample(reference_arrays.lambdas, reference_arrays.intensities, sample_lambdas),
    )


def _handle_zero_denominators(reference_intensity: np.ndarray, policy: str, config: BlockConfig) -> np.ndarray:
    zeros = np.isclose(reference_intensity, 0.0)
    if not np.any(zeros):
        return reference_intensity.astype(float)
    if policy == "error":
        raise ValueError(
            "Reference spectrum contains zero denominator values. Set "
            "zero_denominator_policy explicitly to nan, zero, epsilon, or inf."
        )
    denominator = reference_intensity.astype(float).copy()
    if policy == "nan" or policy == "zero":
        denominator[zeros] = np.nan
    elif policy == "epsilon":
        epsilon = float(config.get("epsilon", 1e-12))
        if epsilon <= 0:
            raise ValueError("epsilon must be positive for zero_denominator_policy='epsilon'.")
        denominator[zeros] = epsilon
    elif policy == "inf":
        denominator[zeros] = np.inf
    return denominator


__all__ = ["DivideByReferenceSpectrum", "SubtractReferenceSpectrum"]
