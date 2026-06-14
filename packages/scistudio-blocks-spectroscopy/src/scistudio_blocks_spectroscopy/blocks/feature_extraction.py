"""Spectroscopy feature extraction / measurement blocks (FR-082..FR-094).

Five blocks that accept ``Collection[Spectrum]`` (never ``SpectralDataset``,
FR-087) and each emit a single flat feature ``DataFrame`` keyed by
``spectrum_id`` (FR-082, FR-083) that can be merged back via
``AttachFeaturesToSpectralDataset``.

scipy (``scipy.signal.find_peaks``) is lazy-imported inside ``FindPeaks`` only.
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
    description="Input spectra to measure.",
)
_FEATURES_OUTPUT = OutputPort(
    name="features",
    accepted_types=[DataFrame],
    description="Flat feature table keyed by spectrum_id.",
)


class ExtractIntensity(ProcessBlock):
    """Measure intensity at a target peak/coordinate/range (FR-088)."""

    type_name: ClassVar[str] = "spectroscopy.extract_intensity"
    name: ClassVar[str] = "Extract Intensity"
    description: ClassVar[str] = "Measure intensity at a target peak, coordinate, or range per spectrum."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "feature_extraction"
    algorithm: ClassVar[str] = "extract_intensity"

    input_ports: ClassVar[list[InputPort]] = [_SPECTRA_INPUT]
    output_ports: ClassVar[list[OutputPort]] = [_FEATURES_OUTPUT]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "target_coordinate": {"type": "number", "title": "Target coordinate"},
            "lambda_min": {"type": "number", "title": "Range min"},
            "lambda_max": {"type": "number", "title": "Range max"},
            "reducer": {
                "type": "string",
                "enum": ["nearest", "max", "mean"],
                "default": "nearest",
                "title": "Range reducer",
            },
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Measure intensity per spectrum (FR-088).

        Implementation plan:
          1. For each Spectrum: lam, inten = _support.spectrum_arrays(spec).
          2. If target_coordinate set, take nearest-grid intensity; if a range
             is set, reduce over [lambda_min, lambda_max] per 'reducer'.
          3. Emit one feature row {spectrum_id, measured_coordinate, intensity,
             status} -> _support.dataframe_from_rows -> dataframe_collection.
        Edge cases: coordinate outside grid; empty range; both/neither provided.
        Test plan: test_feature_extraction_blocks.py::test_extract_intensity_one_row_per_spectrum.
        """
        raise NotImplementedError("skeleton — implement per FR-088; see comment above")


class CalculateAUC(ProcessBlock):
    """Area under the curve over a range (FR-089)."""

    type_name: ClassVar[str] = "spectroscopy.calculate_auc"
    name: ClassVar[str] = "Calculate AUC"
    description: ClassVar[str] = "Calculate area under the curve over a lambda range per spectrum."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "feature_extraction"
    algorithm: ClassVar[str] = "calculate_auc"

    input_ports: ClassVar[list[InputPort]] = [_SPECTRA_INPUT]
    output_ports: ClassVar[list[OutputPort]] = [_FEATURES_OUTPUT]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "lambda_min": {"type": "number", "title": "Range min"},
            "lambda_max": {"type": "number", "title": "Range max"},
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Calculate AUC per spectrum (FR-089).

        Implementation plan:
          1. For each Spectrum: restrict (lambda, intensity) to
             [lambda_min, lambda_max]; auc = numpy.trapz(inten, lam).
          2. Emit one row {spectrum_id, lambda_min, lambda_max, auc, status}.
        Edge cases: <2 points in range; descending lambda; empty range -> status.
        Test plan: test_feature_extraction_blocks.py::test_auc_range_integration.
        """
        raise NotImplementedError("skeleton — implement per FR-089; see comment above")


class CalculateCentroid(ProcessBlock):
    """Intensity-weighted centroid over a range (FR-090)."""

    type_name: ClassVar[str] = "spectroscopy.calculate_centroid"
    name: ClassVar[str] = "Calculate Centroid"
    description: ClassVar[str] = "Calculate the intensity-weighted centroid over a lambda range."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "feature_extraction"
    algorithm: ClassVar[str] = "calculate_centroid"

    input_ports: ClassVar[list[InputPort]] = [_SPECTRA_INPUT]
    output_ports: ClassVar[list[OutputPort]] = [_FEATURES_OUTPUT]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "lambda_min": {"type": "number", "title": "Range min"},
            "lambda_max": {"type": "number", "title": "Range max"},
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Calculate the range centroid per spectrum (FR-090).

        Implementation plan:
          1. Restrict to [lambda_min, lambda_max]; centroid =
             sum(lam*inten)/sum(inten).
          2. Emit one row {spectrum_id, lambda_min, lambda_max, centroid_lambda,
             status}; explicit non-success status when no usable points or the
             intensity denominator is zero (FR-090 / Edge Cases).
        Edge cases: empty range; zero/negative intensity sum.
        Test plan: test_feature_extraction_blocks.py::test_centroid_reports_status_on_empty_range.
        """
        raise NotImplementedError("skeleton — implement per FR-090; see comment above")


class CalculateRatio(ProcessBlock):
    """Peak-to-peak intensity ratio (FR-091, FR-092)."""

    type_name: ClassVar[str] = "spectroscopy.calculate_ratio"
    name: ClassVar[str] = "Calculate Ratio"
    description: ClassVar[str] = "Measure two peak intensities per spectrum and emit their ratio."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "feature_extraction"
    algorithm: ClassVar[str] = "calculate_ratio"

    input_ports: ClassVar[list[InputPort]] = [_SPECTRA_INPUT]
    output_ports: ClassVar[list[OutputPort]] = [_FEATURES_OUTPUT]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "numerator_peak": {"type": "object", "title": "Numerator peak definition"},
            "denominator_peak": {"type": "object", "title": "Denominator peak definition"},
        },
        "required": ["numerator_peak", "denominator_peak"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Calculate the peak-to-peak ratio per spectrum (FR-091, FR-092).

        Implementation plan:
          1. Measure the numerator_peak and denominator_peak intensities per
             spectrum (each peak def carries a center/window/coordinate).
          2. ratio = num_intensity / den_intensity; explicit non-success status
             when a peak cannot be measured or the denominator is zero (FR-092).
          3. Emit one row {spectrum_id, numerator coord/intensity, denominator
             coord/intensity, ratio, status}.
        Edge cases: denominator zero; peak outside grid; identical peaks.
        Test plan: test_feature_extraction_blocks.py::test_ratio_status_on_zero_denominator.
        """
        raise NotImplementedError("skeleton — implement per FR-091/FR-092; see comment above")


class FindPeaks(ProcessBlock):
    """Detect peaks with optional range bounds (FR-093)."""

    type_name: ClassVar[str] = "spectroscopy.find_peaks"
    name: ClassVar[str] = "Find Peaks"
    description: ClassVar[str] = "Detect peaks per spectrum with configurable detection params and optional range."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "feature_extraction"
    algorithm: ClassVar[str] = "find_peaks"

    input_ports: ClassVar[list[InputPort]] = [_SPECTRA_INPUT]
    output_ports: ClassVar[list[OutputPort]] = [_FEATURES_OUTPUT]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "prominence": {"type": "number", "minimum": 0, "title": "Min prominence"},
            "height": {"type": "number", "title": "Min height"},
            "distance": {"type": "number", "minimum": 1, "title": "Min distance (samples)"},
            "lambda_min": {"type": "number", "title": "Range min"},
            "lambda_max": {"type": "number", "title": "Range max"},
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Detect peaks per spectrum (FR-093).

        Implementation plan:
          1. Optionally restrict to [lambda_min, lambda_max].
          2. Lazy-import scipy.signal.find_peaks with prominence/height/distance;
             map sample indices back to lambda coordinates.
          3. Emit feature rows {spectrum_id, peak_coordinate, peak_intensity,
             prominence, status} (covers targeted peak-in-range too; no separate
             MeasurePeakInRange block).
        Edge cases: no peaks found; range with <3 points; all params None.
        Test plan: test_feature_extraction_blocks.py::test_find_peaks_returns_coordinates.
        """
        raise NotImplementedError("skeleton — implement per FR-093; see comment above")


BLOCKS: list[type] = [
    ExtractIntensity,
    CalculateAUC,
    CalculateCentroid,
    CalculateRatio,
    FindPeaks,
]

__all__ = [
    "BLOCKS",
    "CalculateAUC",
    "CalculateCentroid",
    "CalculateRatio",
    "ExtractIntensity",
    "FindPeaks",
]
