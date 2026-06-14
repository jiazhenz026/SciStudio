"""Private helpers for spectroscopy block implementations."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import pyarrow as pa

from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy.types import Spectrum

LAMBDA_COLUMN = "lambda"
INTENSITY_COLUMN = "intensity"


@dataclass(frozen=True)
class SpectrumArrays:
    lambdas: np.ndarray
    intensities: np.ndarray


@dataclass(frozen=True)
class PeakMeasurement:
    coordinate: float | None
    intensity: float | None
    status: str


def unpack_spectra_collection(collection: Collection) -> list[Spectrum]:
    """Return spectra from a Collection and reject direct dataset-like inputs."""

    if not isinstance(collection, Collection):
        raise TypeError("Expected spectra as Collection[Spectrum].")
    spectra = list(collection)
    for item in spectra:
        if not isinstance(item, Spectrum):
            raise TypeError(f"Expected spectra as Collection[Spectrum]; got item type {type(item).__name__}.")
    return spectra


def unpack_reference(value: Any) -> Spectrum:
    """Accept either a raw Spectrum or a single-item Collection[Spectrum]."""

    if isinstance(value, Collection):
        if len(value) != 1:
            raise ValueError(f"Expected one reference Spectrum, got {len(value)} items.")
        value = value[0]
    if not isinstance(value, Spectrum):
        raise TypeError(f"Expected reference Spectrum, got {type(value).__name__}.")
    return value


def spectrum_id(spectrum: Spectrum) -> str:
    """Return the stable spectrum_id from typed meta, user metadata, or framework."""

    user = getattr(spectrum, "user", {}) or {}
    for key in ("spectrum_id", "id"):
        value = user.get(key)
        if value is not None:
            return str(value)

    meta = getattr(spectrum, "meta", None)
    for key in ("spectrum_id", "id"):
        value = getattr(meta, key, None) if meta is not None else None
        if value is not None:
            return str(value)

    framework = getattr(spectrum, "framework", None)
    object_id = getattr(framework, "object_id", None)
    return str(object_id) if object_id is not None else ""


def spectrum_arrays(spectrum: Spectrum) -> SpectrumArrays:
    """Materialize a Spectrum into numeric lambda and intensity arrays."""

    try:
        raw = spectrum.get_in_memory_data()
    except ValueError:
        raw = spectrum.to_memory()

    lambda_names = _candidate_names(getattr(spectrum, "index_name", None), LAMBDA_COLUMN)
    intensity_names = _candidate_names(getattr(spectrum, "value_name", None), INTENSITY_COLUMN)
    lambdas, intensities = _extract_two_numeric_columns(raw, lambda_names, intensity_names)

    if lambdas.shape != intensities.shape:
        raise ValueError(
            f"Spectrum {spectrum_id(spectrum)!r} has mismatched lambda/intensity lengths: "
            f"{len(lambdas)} != {len(intensities)}."
        )
    return SpectrumArrays(lambdas=lambdas, intensities=intensities)


def sorted_arrays(arrays: SpectrumArrays) -> SpectrumArrays:
    """Return arrays sorted by lambda while preserving duplicates deterministically."""

    order = np.argsort(arrays.lambdas, kind="mergesort")
    return SpectrumArrays(lambdas=arrays.lambdas[order], intensities=arrays.intensities[order])


def make_spectrum_like(source: Spectrum, lambdas: Sequence[float], intensities: Sequence[float]) -> Spectrum:
    """Construct a Spectrum preserving source identity metadata and lambda grid."""

    lambda_arr = np.asarray(lambdas, dtype=float)
    intensity_arr = np.asarray(intensities, dtype=float)
    table = pa.table(
        {
            getattr(source, "index_name", None) or LAMBDA_COLUMN: lambda_arr,
            getattr(source, "value_name", None) or INTENSITY_COLUMN: intensity_arr,
        }
    )
    framework = source.framework.derive(derived_from=source.framework.object_id)
    return type(source)(
        index_name=getattr(source, "index_name", None) or LAMBDA_COLUMN,
        value_name=getattr(source, "value_name", None) or INTENSITY_COLUMN,
        length=int(lambda_arr.size),
        framework=framework,
        meta=getattr(source, "meta", None),
        user=dict(getattr(source, "user", {}) or {}),
        data=table,
    )


def make_dataframe(rows: list[dict[str, Any]], columns: list[str]) -> DataFrame:
    """Create a flat SciStudio DataFrame from rows with stable column order."""

    if rows:
        normalized = [{column: row.get(column) for column in columns} for row in rows]
        table = pa.Table.from_pylist(normalized)
        table = table.select(columns)
    else:
        table = pa.table({column: [] for column in columns})
    schema = {field.name: str(field.type) for field in table.schema}
    return DataFrame(columns=columns, row_count=table.num_rows, schema=schema, data=table)


def range_mask(lambdas: np.ndarray, lambda_min: float, lambda_max: float) -> np.ndarray:
    lo, hi = sorted((float(lambda_min), float(lambda_max)))
    return (lambdas >= lo) & (lambdas <= hi)


def window_with_interpolated_bounds(
    lambdas: np.ndarray,
    intensities: np.ndarray,
    lambda_min: float,
    lambda_max: float,
) -> SpectrumArrays:
    """Return a sorted integration window with exact interpolated boundaries."""

    lo, hi = sorted((float(lambda_min), float(lambda_max)))
    finite = np.isfinite(lambdas) & np.isfinite(intensities)
    sorted_input = sorted_arrays(SpectrumArrays(lambdas[finite], intensities[finite]))
    x = sorted_input.lambdas
    y = sorted_input.intensities
    if x.size == 0 or hi < x[0] or lo > x[-1]:
        return SpectrumArrays(np.array([], dtype=float), np.array([], dtype=float))

    clipped_lo = max(lo, float(x[0]))
    clipped_hi = min(hi, float(x[-1]))
    mask = (x > clipped_lo) & (x < clipped_hi)
    wx = np.concatenate(([clipped_lo], x[mask], [clipped_hi]))
    wy = np.interp(wx, x, y)
    unique_x, unique_indices = np.unique(wx, return_index=True)
    return SpectrumArrays(unique_x, wy[unique_indices])


def measure_peak(
    lambdas: np.ndarray,
    intensities: np.ndarray,
    definition: Any,
    *,
    interpolation: str = "linear",
) -> PeakMeasurement:
    """Measure a peak, coordinate, or range definition from one spectrum."""

    if definition is None:
        return PeakMeasurement(None, None, "missing_peak_definition")

    if isinstance(definition, dict):
        if "lambda_min" in definition and "lambda_max" in definition:
            return measure_range_peak(
                lambdas,
                intensities,
                float(definition["lambda_min"]),
                float(definition["lambda_max"]),
            )
        for key in ("lambda", "coordinate", "target_lambda", "peak"):
            if key in definition:
                return measure_coordinate(
                    lambdas,
                    intensities,
                    float(definition[key]),
                    interpolation=interpolation,
                )

    return measure_coordinate(lambdas, intensities, float(definition), interpolation=interpolation)


def measure_coordinate(
    lambdas: np.ndarray,
    intensities: np.ndarray,
    coordinate: float,
    *,
    interpolation: str = "linear",
) -> PeakMeasurement:
    finite = np.isfinite(lambdas) & np.isfinite(intensities)
    sorted_input = sorted_arrays(SpectrumArrays(lambdas[finite], intensities[finite]))
    x = sorted_input.lambdas
    y = sorted_input.intensities
    if x.size == 0:
        return PeakMeasurement(float(coordinate), None, "empty_spectrum")
    coordinate = float(coordinate)
    if coordinate < x[0] or coordinate > x[-1]:
        return PeakMeasurement(coordinate, None, "coordinate_out_of_range")

    exact = np.where(np.isclose(x, coordinate, rtol=0.0, atol=1e-12))[0]
    if exact.size:
        return PeakMeasurement(float(x[exact[0]]), float(y[exact[0]]), "success")

    if interpolation == "none":
        return PeakMeasurement(coordinate, None, "missing_coordinate")
    if interpolation == "nearest":
        nearest = int(np.argmin(np.abs(x - coordinate)))
        return PeakMeasurement(float(x[nearest]), float(y[nearest]), "success")
    if interpolation != "linear":
        raise ValueError("interpolation must be one of: linear, nearest, none")

    return PeakMeasurement(coordinate, float(np.interp(coordinate, x, y)), "success")


def measure_range_peak(
    lambdas: np.ndarray,
    intensities: np.ndarray,
    lambda_min: float,
    lambda_max: float,
) -> PeakMeasurement:
    mask = range_mask(lambdas, lambda_min, lambda_max) & np.isfinite(intensities)
    if not np.any(mask):
        return PeakMeasurement(None, None, "empty_range")
    x = lambdas[mask]
    y = intensities[mask]
    idx = int(np.argmax(y))
    return PeakMeasurement(float(x[idx]), float(y[idx]), "success")


def interpolate_reference_to_sample(
    reference_lambdas: np.ndarray,
    reference_intensities: np.ndarray,
    sample_lambdas: np.ndarray,
) -> np.ndarray:
    """Interpolate reference intensities to a sample grid without extrapolation."""

    sorted_ref = sorted_arrays(SpectrumArrays(reference_lambdas, reference_intensities))
    x = sorted_ref.lambdas
    y = sorted_ref.intensities
    if x.size == 0:
        raise ValueError("Reference spectrum is empty.")
    if sample_lambdas.size and (np.min(sample_lambdas) < x[0] or np.max(sample_lambdas) > x[-1]):
        raise ValueError("Reference grid does not cover the sample lambda grid.")
    return cast(np.ndarray, np.interp(sample_lambdas, x, y))


def same_grid(left: np.ndarray, right: np.ndarray) -> bool:
    return left.shape == right.shape and bool(np.allclose(left, right, rtol=0.0, atol=1e-12))


def config_range(config: Any) -> tuple[float, float]:
    lambda_min = config.get("lambda_min")
    lambda_max = config.get("lambda_max")
    if lambda_min is None or lambda_max is None:
        raise ValueError("lambda_min and lambda_max are required.")
    return float(lambda_min), float(lambda_max)


def _candidate_names(preferred: str | None, fallback: str) -> list[str]:
    names = [name for name in (preferred, fallback, "wavenumber", "wavelength", "raman_shift", "x", "value") if name]
    deduped: list[str] = []
    for name in names:
        if name not in deduped:
            deduped.append(name)
    return deduped


def _extract_two_numeric_columns(
    raw: Any,
    lambda_names: Iterable[str],
    intensity_names: Iterable[str],
) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(raw, pa.Table):
        return _from_mapping_like(
            {name: raw.column(name).to_pylist() for name in raw.column_names},
            lambda_names,
            intensity_names,
            fallback_columns=raw.column_names,
        )

    if hasattr(raw, "to_dict") and hasattr(raw, "columns"):
        data = raw.to_dict(orient="list")
        return _from_mapping_like(data, lambda_names, intensity_names, fallback_columns=list(raw.columns))

    if isinstance(raw, dict):
        return _from_mapping_like(raw, lambda_names, intensity_names, fallback_columns=list(raw.keys()))

    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        keys = list(raw[0].keys())
        data = {key: [record.get(key) for record in raw] for key in keys}
        return _from_mapping_like(data, lambda_names, intensity_names, fallback_columns=keys)

    array = np.asarray(raw, dtype=float)
    if array.ndim == 2 and array.shape[1] >= 2:
        return array[:, 0].astype(float), array[:, 1].astype(float)
    if array.ndim == 1:
        return np.arange(array.size, dtype=float), array.astype(float)
    raise TypeError(f"Cannot interpret spectrum payload of type {type(raw).__name__}.")


def _from_mapping_like(
    data: dict[str, Any],
    lambda_names: Iterable[str],
    intensity_names: Iterable[str],
    *,
    fallback_columns: Sequence[str],
) -> tuple[np.ndarray, np.ndarray]:
    lambda_key = _first_existing(data, lambda_names)
    intensity_key = _first_existing(data, intensity_names)
    if lambda_key is None and fallback_columns:
        lambda_key = fallback_columns[0]
    if intensity_key is None and len(fallback_columns) > 1:
        intensity_key = fallback_columns[1]
    if lambda_key is None or intensity_key is None:
        raise ValueError("Spectrum payload must contain lambda and intensity columns.")
    return np.asarray(data[lambda_key], dtype=float), np.asarray(data[intensity_key], dtype=float)


def _first_existing(data: dict[str, Any], names: Iterable[str]) -> str | None:
    for name in names:
        if name in data:
            return name
    return None
