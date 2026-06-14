"""Spectroscopy peak fitting block (FR-113..FR-120).

One block, :class:`FitPeak`. It fits a Gaussian/Lorentzian/Voigt model without
modifying the input spectra and emits fitted curves, residual spectra, and a
``parameters`` feature table. Per FR-120 the tabular output port is named
``parameters`` (NOT ``fit_diagnostics``).

scipy (``scipy.optimize.curve_fit``, ``scipy.special.wofz``) is lazy-imported
inside the run body only.
"""

from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy.types import Spectrum


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
        raise NotImplementedError("skeleton — implement per FR-113..FR-120; see comment above")


BLOCKS: list[type] = [FitPeak]

__all__ = ["BLOCKS", "FitPeak"]
