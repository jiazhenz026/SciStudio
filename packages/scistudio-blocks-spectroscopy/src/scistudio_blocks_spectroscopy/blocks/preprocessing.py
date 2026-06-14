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

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy.types import Spectrum

_SPECTRA_INPUT = InputPort(
    name="spectra",
    accepted_types=[Spectrum],
    is_collection=True,
    required=True,
    description="Input spectra to preprocess.",
)


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

        Implementation plan:
          1. For each Spectrum: lam, inten = _support.spectrum_arrays(spec).
          2. Keep points where lambda_min <= lam <= lambda_max (open bounds when
             a bound is omitted); intensities for kept points are unchanged.
          3. Emit via _support.derive_spectrum(spec, lambda_values=..,
             intensity_values=..) preserving spectrum_id/meta.
        Edge cases: empty range; min > max; all points dropped.
        Test plan: test_preprocessing_blocks.py::test_crop_keeps_in_range_only.
        """
        raise NotImplementedError("skeleton — implement per FR-057; see comment above")


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
        """Shift the lambda axis (FR-058).

        Implementation plan:
          1. shift = float(config.get('shift', 0.0)).
          2. For each Spectrum: lam, inten = _support.spectrum_arrays(spec);
             emit _support.derive_spectrum(spec, lambda_values=lam+shift,
             intensity_values=inten).
        Edge cases: shift=0 (identity); negative shift.
        Test plan: test_preprocessing_blocks.py::test_shift_axis_preserves_intensity.
        """
        raise NotImplementedError("skeleton — implement per FR-058; see comment above")


class BaselineCorrection(ProcessBlock):
    """Estimate and subtract a baseline per spectrum (FR-059..FR-064)."""

    type_name: ClassVar[str] = "spectroscopy.baseline_correction"
    name: ClassVar[str] = "Baseline Correction"
    description: ClassVar[str] = "Estimate baselines, subtract them, and report fit diagnostics."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "baseline_correction"

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

        Implementation plan:
          1. method = config.get('method','polynomial'); validate in the enum.
          2. polynomial: numpy.polyfit on (lambda, intensity); asls/arpls/airpls:
             lazy-import scipy.sparse + scipy.sparse.linalg, hand-rolled
             Whittaker smoother (lam, p, max_iter). NO pybaselines.
          3. corrected = intensity - baseline; emit corrected/baseline spectra via
             _support.derive_spectrum and a fit_diagnostics DataFrame with one
             row per spectrum (spectrum_id, method, status, parameters, converged,
             iterations, rmse) (FR-064).
          4. Return {'corrected': ..., 'baseline': ...,
             'fit_diagnostics': _support.dataframe_collection(df)}.
        Edge cases: short spectra; non-convergence; flat input.
        Test plan: test_preprocessing_fit_outputs.py::test_baseline_emits_three_ports,
          ::test_baseline_diagnostics_one_row_per_spectrum.
        """
        raise NotImplementedError("skeleton — implement per FR-059..FR-064; see comment above")


class SmoothSpectrum(ProcessBlock):
    """Smooth intensities without changing the ``lambda`` grid (FR-065, FR-066)."""

    type_name: ClassVar[str] = "spectroscopy.smooth_spectrum"
    name: ClassVar[str] = "Smooth Spectrum"
    description: ClassVar[str] = "Smooth intensities with a selectable method; lambda grid unchanged."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "smooth_spectrum"

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
        """Smooth intensities (FR-065, FR-066).

        Implementation plan:
          1. method = config.get('method','savitzky_golay'); validate in enum.
          2. savitzky_golay: lazy scipy.signal.savgol_filter(window, polyorder);
             moving_average: numpy.convolve; gaussian: scipy.ndimage
             .gaussian_filter1d(sigma); median: scipy.signal.medfilt(window).
          3. Emit _support.derive_spectrum(spec, intensity_values=smoothed);
             lambda grid unchanged (FR-066).
        Edge cases: window > length; even window for savgol; window=1 identity.
        Test plan: test_preprocessing_blocks.py::test_smooth_preserves_grid.
        """
        raise NotImplementedError("skeleton — implement per FR-065/FR-066; see comment above")


class AlignAndResampleSpectra(ProcessBlock):
    """Align and resample spectra to a shared grid (FR-067..FR-073)."""

    type_name: ClassVar[str] = "spectroscopy.align_and_resample_spectra"
    name: ClassVar[str] = "Align and Resample Spectra"
    description: ClassVar[str] = "Align and/or resample spectra onto a shared grid with fit diagnostics."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "align_and_resample_spectra"

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
        """Align and resample spectra (FR-067..FR-073).

        Implementation plan:
          1. Build the target grid from target_grid_mode (explicit / first /
             reference (inputs['reference']) / range_step lambda_min..max,step).
          2. alignment_method: none -> resample only (numpy.interp); peak_fit ->
             lazy scipy.optimize.curve_fit to estimate per-spectrum shift +
             emit fit_curves; cross_correlation -> scipy.signal.correlate shift.
          3. Resample each spectrum onto the target grid; emit aligned spectra,
             fit_curves (empty/status-compatible when no fit, FR-072), and a
             fit_diagnostics DataFrame (method, status, applied shift, quality).
        Edge cases: reference required but missing; non-overlapping grids; no fit.
        Test plan: test_preprocessing_fit_outputs.py::test_align_emits_three_ports,
          ::test_align_peak_fit_populates_fit_curves.
        """
        raise NotImplementedError("skeleton — implement per FR-067..FR-073; see comment above")


class NormalizeSpectrum(ProcessBlock):
    """Normalize intensities with ``max`` or ``minmax`` (FR-074, FR-075)."""

    type_name: ClassVar[str] = "spectroscopy.normalize_spectrum"
    name: ClassVar[str] = "Normalize Spectrum"
    description: ClassVar[str] = "Normalize intensities using max or minmax scaling."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "normalize_spectrum"

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
        """Normalize intensities (FR-074, FR-075).

        Implementation plan:
          1. method = config.get('method','max'); validate in {'max','minmax'}.
          2. max: intensity / max(intensity); minmax: (i-min)/(max-min).
          3. Emit _support.derive_spectrum(spec, intensity_values=normalized).
        Edge cases: constant spectrum (max==min); all-zero spectrum.
        Test plan: test_preprocessing_blocks.py::test_normalize_max_and_minmax.
        """
        raise NotImplementedError("skeleton — implement per FR-074/FR-075; see comment above")


class SubtractPeakComponent(ProcessBlock):
    """Fit and subtract a peak component per spectrum (FR-076..FR-080)."""

    type_name: ClassVar[str] = "spectroscopy.subtract_peak_component"
    name: ClassVar[str] = "Subtract Peak Component"
    description: ClassVar[str] = "Fit a peak/component, subtract it, output the fitted curve and diagnostics."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
    algorithm: ClassVar[str] = "subtract_peak_component"

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
        """Fit and subtract a peak component (FR-076..FR-080).

        Implementation plan:
          1. model = config.get('model','gaussian'); validate in enum.
          2. Within [peak_center +/- window], lazy scipy.optimize.curve_fit a
             gaussian/lorentzian/voigt (voigt via scipy.special.wofz) model.
          3. component = fitted curve on the spectrum grid; corrected =
             intensity - component; emit both via _support.derive_spectrum plus a
             fit_diagnostics DataFrame (model, status, center, amplitude, width,
             FWHM, area, fit quality) (FR-080).
        Edge cases: fit failure -> non-success status, component=0; window outside data.
        Test plan: test_preprocessing_fit_outputs.py::test_subtract_peak_emits_three_ports.
        """
        raise NotImplementedError("skeleton — implement per FR-076..FR-080; see comment above")


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
