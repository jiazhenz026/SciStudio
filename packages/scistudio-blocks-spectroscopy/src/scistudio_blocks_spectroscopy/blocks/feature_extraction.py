"""Spectroscopy feature extraction / measurement blocks (FR-082..FR-094).

Five blocks that accept ``Collection[Spectrum]`` (never ``SpectralDataset``,
FR-087) and each emit a single flat feature ``DataFrame`` keyed by
``spectrum_id`` (FR-082, FR-083) that can be merged back via
``AttachFeaturesToSpectralDataset``.

Per-spectrum failures do not crash the block: they emit a feature row with a
non-success ``status`` value and ``None`` measurements (FR-088..FR-093). All
table cells are scalars (FR-083); never a ``Spectrum``/``DataObject``.

scipy (``scipy.signal.find_peaks``) is lazy-imported inside ``FindPeaks`` only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.types import Spectrum

#: Success status value used in every feature table (FR-088..FR-093).
_STATUS_OK = "ok"

#: numpy trapezoidal integrator: ``np.trapezoid`` (numpy>=2) with a
#: ``np.trapz`` fallback for older numpy (FR-089).
_trapezoid = getattr(np, "trapezoid", None) or np.trapz  # type: ignore[attr-defined]

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


# ---------------------------------------------------------------------------
# Shared measurement helpers (numpy-only; no object cells)
# ---------------------------------------------------------------------------


def _restrict_range(
    lam: np.ndarray, inten: np.ndarray, lambda_min: float | None, lambda_max: float | None
) -> tuple[np.ndarray, np.ndarray]:
    """Restrict ``(lam, inten)`` to ``[lambda_min, lambda_max]`` (inclusive).

    Either bound may be ``None`` (open on that side). Tolerates a descending
    grid; the mask is purely value based, so the original order is preserved.
    """
    mask = np.ones(lam.shape, dtype=bool)
    if lambda_min is not None:
        mask &= lam >= lambda_min
    if lambda_max is not None:
        mask &= lam <= lambda_max
    return lam[mask], inten[mask]


def _measure_at_coordinate(
    lam: np.ndarray, inten: np.ndarray, coordinate: float
) -> tuple[float | None, float | None, str]:
    """Return nearest-grid measurement or a non-success status for out-of-grid coordinates."""
    if lam.size == 0:
        return None, None, "empty_spectrum"
    lo = float(np.min(lam))
    hi = float(np.max(lam))
    if coordinate < lo or coordinate > hi:
        return None, None, "coordinate_out_of_grid"
    idx = int(np.argmin(np.abs(lam - coordinate)))
    return float(lam[idx]), float(inten[idx]), _STATUS_OK


def _reduce_range(inten: np.ndarray, reducer: str) -> float:
    if reducer == "max":
        return float(np.max(inten))
    if reducer == "mean":
        return float(np.mean(inten))
    raise ValueError(f"unknown range reducer {reducer!r}; expected one of ['max', 'mean']")


def _measure_peak_intensity(
    lam: np.ndarray, inten: np.ndarray, peak: Mapping[str, Any]
) -> tuple[float | None, float | None, str]:
    """Measure one peak definition against a spectrum.

    A peak definition is a config object that carries either a single
    ``coordinate`` (nearest-grid sampling) or a ``lambda_min``/``lambda_max``
    window reduced by ``reducer`` (``"max"`` default, also ``"mean"``).
    Returns ``(measured_coordinate, intensity, status)``; on a non-measurable
    peak the coordinate/intensity are ``None`` and the status describes why.
    """
    coordinate = peak.get("coordinate", peak.get("target_coordinate"))
    lambda_min = peak.get("lambda_min")
    lambda_max = peak.get("lambda_max")
    reducer = str(peak.get("reducer", "max"))

    if coordinate is not None:
        return _measure_at_coordinate(lam, inten, float(coordinate))

    if lambda_min is None and lambda_max is None:
        return None, None, "peak_definition_missing_coordinate_or_range"

    win_lam, win_inten = _restrict_range(
        lam,
        inten,
        None if lambda_min is None else float(lambda_min),
        None if lambda_max is None else float(lambda_max),
    )
    if win_lam.size == 0:
        return None, None, "peak_range_has_no_points"

    if reducer not in ("max", "mean"):
        return None, None, f"unknown_reducer_{reducer}"
    if reducer == "max":
        idx = int(np.argmax(win_inten))
        return float(win_lam[idx]), float(win_inten[idx]), _STATUS_OK
    # mean: report the window midpoint as the measured coordinate.
    return float(np.mean(win_lam)), float(np.mean(win_inten)), _STATUS_OK


def _spectrum_key(spectrum: Spectrum) -> str:
    """Return the spectrum_id, generating a stable fallback if absent."""
    return spectrum.spectrum_id or _support.new_spectrum_id()


def _features_output(rows: list[dict[str, Any]], columns: list[str]) -> dict[str, Collection]:
    frame = _support.dataframe_from_rows(rows, columns=columns)
    return {"features": _support.dataframe_collection(frame)}


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
        spectra = _support.coerce_spectra(inputs.get("spectra"), block=self.name)

        target = config.get("target_coordinate")
        lambda_min = config.get("lambda_min")
        lambda_max = config.get("lambda_max")
        reducer = str(config.get("reducer", "nearest"))
        if reducer not in ("nearest", "max", "mean"):
            raise ValueError(f"{self.name}: reducer must be one of ['nearest', 'max', 'mean'], got {reducer!r}")
        use_range = target is None and (lambda_min is not None or lambda_max is not None)

        columns = ["spectrum_id", "measured_coordinate", "intensity", "status"]
        rows: list[dict[str, Any]] = []
        for spectrum in spectra:
            key = _spectrum_key(spectrum)
            lam, inten = _support.spectrum_arrays(spectrum)
            coord: float | None
            value: float | None
            if lam.size == 0:
                coord, value, status = None, None, "empty_spectrum"
            elif use_range:
                win_lam, win_inten = _restrict_range(
                    lam,
                    inten,
                    None if lambda_min is None else float(lambda_min),
                    None if lambda_max is None else float(lambda_max),
                )
                if win_lam.size == 0:
                    coord, value, status = None, None, "range_has_no_points"
                elif reducer == "nearest":
                    # No coordinate given for a nearest reduction over a range:
                    # fall back to the window peak so a value is still produced.
                    idx = int(np.argmax(win_inten))
                    coord, value, status = float(win_lam[idx]), float(win_inten[idx]), _STATUS_OK
                else:
                    value = _reduce_range(win_inten, reducer)
                    coord = float(np.mean(win_lam))
                    status = _STATUS_OK
            elif target is not None:
                coord, value, status = _measure_at_coordinate(lam, inten, float(target))
            else:
                coord, value, status = None, None, "no_target_coordinate_or_range"
            rows.append({"spectrum_id": key, "measured_coordinate": coord, "intensity": value, "status": status})
        return _features_output(rows, columns)


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
        spectra = _support.coerce_spectra(inputs.get("spectra"), block=self.name)
        lambda_min = config.get("lambda_min")
        lambda_max = config.get("lambda_max")
        lo = None if lambda_min is None else float(lambda_min)
        hi = None if lambda_max is None else float(lambda_max)

        columns = ["spectrum_id", "lambda_min", "lambda_max", "auc", "status"]
        rows: list[dict[str, Any]] = []
        for spectrum in spectra:
            key = _spectrum_key(spectrum)
            lam, inten = _support.spectrum_arrays(spectrum)
            win_lam, win_inten = _restrict_range(lam, inten, lo, hi)
            auc: float | None
            if win_lam.size < 2:
                auc, status = None, "range_has_fewer_than_two_points"
            else:
                # Sort by lambda so trapz is well defined on descending grids.
                order = np.argsort(win_lam)
                auc = float(_trapezoid(win_inten[order], win_lam[order]))
                status = _STATUS_OK
            rows.append(
                {
                    "spectrum_id": key,
                    "lambda_min": lo,
                    "lambda_max": hi,
                    "auc": auc,
                    "status": status,
                }
            )
        return _features_output(rows, columns)


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
        spectra = _support.coerce_spectra(inputs.get("spectra"), block=self.name)
        lambda_min = config.get("lambda_min")
        lambda_max = config.get("lambda_max")
        lo = None if lambda_min is None else float(lambda_min)
        hi = None if lambda_max is None else float(lambda_max)

        columns = ["spectrum_id", "lambda_min", "lambda_max", "centroid_lambda", "status"]
        rows: list[dict[str, Any]] = []
        for spectrum in spectra:
            key = _spectrum_key(spectrum)
            lam, inten = _support.spectrum_arrays(spectrum)
            win_lam, win_inten = _restrict_range(lam, inten, lo, hi)
            centroid: float | None
            if win_lam.size == 0:
                centroid, status = None, "range_has_no_points"
            else:
                denom = float(np.sum(win_inten))
                if denom == 0.0 or not np.isfinite(denom):
                    centroid, status = None, "zero_intensity_denominator"
                else:
                    centroid = float(np.sum(win_lam * win_inten) / denom)
                    status = _STATUS_OK
            rows.append(
                {
                    "spectrum_id": key,
                    "lambda_min": lo,
                    "lambda_max": hi,
                    "centroid_lambda": centroid,
                    "status": status,
                }
            )
        return _features_output(rows, columns)


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
        spectra = _support.coerce_spectra(inputs.get("spectra"), block=self.name)
        numerator_peak = config.get("numerator_peak")
        denominator_peak = config.get("denominator_peak")
        if not isinstance(numerator_peak, Mapping):
            raise ValueError(f"{self.name}: 'numerator_peak' must be a peak-definition object")
        if not isinstance(denominator_peak, Mapping):
            raise ValueError(f"{self.name}: 'denominator_peak' must be a peak-definition object")

        columns = [
            "spectrum_id",
            "numerator_coordinate",
            "numerator_intensity",
            "denominator_coordinate",
            "denominator_intensity",
            "ratio",
            "status",
        ]
        rows: list[dict[str, Any]] = []
        for spectrum in spectra:
            key = _spectrum_key(spectrum)
            lam, inten = _support.spectrum_arrays(spectrum)
            ratio: float | None
            if lam.size == 0:
                rows.append(
                    {
                        "spectrum_id": key,
                        "numerator_coordinate": None,
                        "numerator_intensity": None,
                        "denominator_coordinate": None,
                        "denominator_intensity": None,
                        "ratio": None,
                        "status": "empty_spectrum",
                    }
                )
                continue
            num_coord, num_val, num_status = _measure_peak_intensity(lam, inten, numerator_peak)
            den_coord, den_val, den_status = _measure_peak_intensity(lam, inten, denominator_peak)

            if num_status != _STATUS_OK:
                ratio, status = None, f"numerator_{num_status}"
            elif den_status != _STATUS_OK:
                ratio, status = None, f"denominator_{den_status}"
            elif den_val is None or den_val == 0.0 or not np.isfinite(den_val):
                ratio, status = None, "denominator_zero_or_unusable"
            else:
                ratio = float(num_val) / float(den_val)  # type: ignore[arg-type]
                status = _STATUS_OK
            rows.append(
                {
                    "spectrum_id": key,
                    "numerator_coordinate": num_coord,
                    "numerator_intensity": num_val,
                    "denominator_coordinate": den_coord,
                    "denominator_intensity": den_val,
                    "ratio": ratio,
                    "status": status,
                }
            )
        return _features_output(rows, columns)


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
        from scipy.signal import find_peaks  # lazy (FR-093) — keeps import scipy-free

        spectra = _support.coerce_spectra(inputs.get("spectra"), block=self.name)

        prominence = config.get("prominence")
        height = config.get("height")
        distance = config.get("distance")
        lambda_min = config.get("lambda_min")
        lambda_max = config.get("lambda_max")
        lo = None if lambda_min is None else float(lambda_min)
        hi = None if lambda_max is None else float(lambda_max)

        find_kwargs: dict[str, Any] = {}
        if prominence is not None:
            find_kwargs["prominence"] = float(prominence)
        if height is not None:
            find_kwargs["height"] = float(height)
        if distance is not None:
            find_kwargs["distance"] = max(1, int(float(distance)))

        columns = ["spectrum_id", "peak_coordinate", "peak_intensity", "prominence", "status"]
        rows: list[dict[str, Any]] = []
        for spectrum in spectra:
            key = _spectrum_key(spectrum)
            lam, inten = _support.spectrum_arrays(spectrum)
            win_lam, win_inten = _restrict_range(lam, inten, lo, hi)
            if win_lam.size < 3:
                rows.append(
                    {
                        "spectrum_id": key,
                        "peak_coordinate": None,
                        "peak_intensity": None,
                        "prominence": None,
                        "status": "range_has_fewer_than_three_points",
                    }
                )
                continue
            order = np.argsort(win_lam)
            ordered_lam = win_lam[order]
            ordered_inten = win_inten[order]
            peak_indices, properties = find_peaks(ordered_inten, **find_kwargs)
            if peak_indices.size == 0:
                rows.append(
                    {
                        "spectrum_id": key,
                        "peak_coordinate": None,
                        "peak_intensity": None,
                        "prominence": None,
                        "status": "no_peaks_found",
                    }
                )
                continue
            # Select the most prominent (or, absent prominences, the tallest) peak
            # as the representative coordinate; emit detection metrics alongside.
            prominences = properties.get("prominences")
            if prominences is not None and len(prominences) == peak_indices.size:
                best = int(np.argmax(prominences))
                best_prom: float | None = float(prominences[best])
            else:
                best = int(np.argmax(ordered_inten[peak_indices]))
                best_prom = None
            best_idx = int(peak_indices[best])
            rows.append(
                {
                    "spectrum_id": key,
                    "peak_coordinate": float(ordered_lam[best_idx]),
                    "peak_intensity": float(ordered_inten[best_idx]),
                    "prominence": best_prom,
                    "status": _STATUS_OK,
                }
            )
        return _features_output(rows, columns)


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
