"""Spectral library matching blocks for the spectroscopy package."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, cast

import numpy as np
import pandas as pd

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

_MATCHING_METHODS = (
    "cosine_similarity",
    "pearson_correlation",
    "spectral_angle",
    "euclidean_distance",
)
_HIGHER_IS_BETTER = {"cosine_similarity", "pearson_correlation"}
_OUTPUT_COLUMNS = [
    "spectrum_id",
    "library_spectrum_id",
    "method",
    "rank",
    "score",
    "status",
    "library_row_index",
    "message",
]


@dataclass(frozen=True)
class _SpectrumVector:
    spectrum_id: str
    lambda_values: np.ndarray
    intensities: np.ndarray
    lambda_unit: str | None
    intensity_unit: str | None
    metadata: dict[str, Any]


class MatchSpectralLibrary(ProcessBlock):
    """Rank query spectra against a ``SpectralDataset`` reference library."""

    name: ClassVar[str] = "Match Spectral Library"
    type_name: ClassVar[str] = "spectroscopy.match_spectral_library"
    description: ClassVar[str] = "Rank query spectra against a SpectralDataset library with a selected score method."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "analysis"
    algorithm: ClassVar[str] = "spectral_library_matching"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="spectra",
            accepted_types=[Spectrum],
            is_collection=True,
            description="Query spectra to match.",
        ),
        InputPort(
            name="library",
            accepted_types=[SpectralDataset],
            description="Reference library represented as a SpectralDataset.",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="matches",
            accepted_types=[DataFrame],
            description="Ranked spectral library match table.",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": list(_MATCHING_METHODS),
                "default": "cosine_similarity",
                "title": "Matching Method",
            },
            "top_k": {
                "type": "integer",
                "minimum": 1,
                "default": 5,
                "title": "Top Matches",
            },
            "grid_policy": {
                "type": "string",
                "enum": ["error", "report"],
                "default": "error",
                "title": "Grid Compatibility Policy",
            },
            "unit_policy": {
                "type": "string",
                "enum": ["error", "report"],
                "default": "error",
                "title": "Unit Compatibility Policy",
            },
        },
        "required": ["method", "top_k"],
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        method = _validated_method(config.get("method", "cosine_similarity"))
        top_k = int(config.get("top_k", 5))
        if top_k < 1:
            raise ValueError("MatchSpectralLibrary: top_k must be >= 1")

        query_items = _require_collection(inputs.get("spectra"), "spectra")
        library = _require_single_or_object(inputs.get("library"), "library")
        queries = [_spectrum_vector(item) for item in query_items]
        references = _library_vectors(library)

        rows: list[dict[str, Any]] = []
        if not queries:
            return {"matches": _dataframe_collection(rows)}

        if not references:
            for query in queries:
                rows.append(
                    {
                        "spectrum_id": query.spectrum_id,
                        "library_spectrum_id": None,
                        "method": method,
                        "rank": 0,
                        "score": np.nan,
                        "status": "no_matches",
                        "library_row_index": None,
                        "message": "library contains no reference spectra",
                    }
                )
            return {"matches": _dataframe_collection(rows)}

        for query in queries:
            rows.extend(_rank_query(query, references, method, top_k, config))

        return {"matches": _dataframe_collection(rows)}


def _validated_method(method: Any) -> str:
    value = str(method)
    if value not in _MATCHING_METHODS:
        accepted = ", ".join(_MATCHING_METHODS)
        raise ValueError(f"MatchSpectralLibrary: method must be one of {accepted}; got {value!r}")
    return value


def _rank_query(
    query: _SpectrumVector,
    references: list[_SpectrumVector],
    method: str,
    top_k: int,
    config: BlockConfig,
) -> list[dict[str, Any]]:
    scored: list[tuple[int, _SpectrumVector, float]] = []
    reported: list[dict[str, Any]] = []

    for ref_index, reference in enumerate(references):
        problem = _compatibility_problem(query, reference)
        if problem is not None:
            if _should_report(problem, config):
                reported.append(
                    {
                        "spectrum_id": query.spectrum_id,
                        "library_spectrum_id": reference.spectrum_id,
                        "method": method,
                        "rank": 0,
                        "score": np.nan,
                        "status": problem[0],
                        "library_row_index": ref_index,
                        "message": problem[1],
                    }
                )
                continue
            raise ValueError(f"MatchSpectralLibrary: {problem[1]}")

        score = _score(query.intensities, reference.intensities, method)
        if np.isfinite(score):
            scored.append((ref_index, reference, score))
        else:
            reported.append(
                {
                    "spectrum_id": query.spectrum_id,
                    "library_spectrum_id": reference.spectrum_id,
                    "method": method,
                    "rank": 0,
                    "score": np.nan,
                    "status": "failed",
                    "library_row_index": ref_index,
                    "message": "score is not finite",
                }
            )

    if not scored:
        return reported or [
            {
                "spectrum_id": query.spectrum_id,
                "library_spectrum_id": None,
                "method": method,
                "rank": 0,
                "score": np.nan,
                "status": "no_matches",
                "library_row_index": None,
                "message": "no compatible reference spectra",
            }
        ]

    reverse = method in _HIGHER_IS_BETTER
    ordered = sorted(scored, key=lambda item: item[2], reverse=reverse)
    rows: list[dict[str, Any]] = []
    for rank, (ref_index, reference, score) in enumerate(ordered[:top_k], start=1):
        rows.append(
            {
                "spectrum_id": query.spectrum_id,
                "library_spectrum_id": reference.spectrum_id,
                "method": method,
                "rank": rank,
                "score": float(score),
                "status": "ok",
                "library_row_index": ref_index,
                "message": "",
            }
        )
    rows.extend(reported)
    return rows


def _score(query: np.ndarray, reference: np.ndarray, method: str) -> float:
    if method == "cosine_similarity":
        denominator = float(np.linalg.norm(query) * np.linalg.norm(reference))
        if denominator == 0.0:
            return float("nan")
        return float(np.dot(query, reference) / denominator)
    if method == "pearson_correlation":
        q_centered = query - float(np.mean(query))
        r_centered = reference - float(np.mean(reference))
        denominator = float(np.linalg.norm(q_centered) * np.linalg.norm(r_centered))
        if denominator == 0.0:
            return float("nan")
        return float(np.dot(q_centered, r_centered) / denominator)
    if method == "spectral_angle":
        cosine = _score(query, reference, "cosine_similarity")
        if not np.isfinite(cosine):
            return float("nan")
        return float(np.arccos(np.clip(cosine, -1.0, 1.0)))
    if method == "euclidean_distance":
        return float(np.linalg.norm(query - reference))
    raise AssertionError(f"unexpected method {method!r}")


def _compatibility_problem(left: _SpectrumVector, right: _SpectrumVector) -> tuple[str, str] | None:
    if left.lambda_values.shape != right.lambda_values.shape or not np.allclose(
        left.lambda_values, right.lambda_values
    ):
        return (
            "incompatible_grid",
            f"query {left.spectrum_id!r} and library {right.spectrum_id!r} have incompatible lambda grids",
        )
    if left.lambda_unit and right.lambda_unit and left.lambda_unit != right.lambda_unit:
        return (
            "incompatible_units",
            f"query {left.spectrum_id!r} lambda_unit {left.lambda_unit!r} does not match "
            f"library {right.spectrum_id!r} lambda_unit {right.lambda_unit!r}",
        )
    return None


def _should_report(problem: tuple[str, str], config: BlockConfig) -> bool:
    status, _message = problem
    if status == "incompatible_grid":
        return str(config.get("grid_policy", "error")) == "report"
    if status == "incompatible_units":
        return str(config.get("unit_policy", "error")) == "report"
    return False


def _library_vectors(library: Any) -> list[_SpectrumVector]:
    index_obj = _slot(library, "index")
    spectra_obj = _slot(library, "spectra")
    index_frame = _as_pandas_frame(index_obj)
    spectra_frame = _as_pandas_frame(spectra_obj)
    if "spectrum_id" not in index_frame.columns:
        raise ValueError("MatchSpectralLibrary: library index is missing 'spectrum_id'")
    for required in ("spectrum_id", "lambda", "intensity"):
        if required not in spectra_frame.columns:
            raise ValueError(f"MatchSpectralLibrary: library spectra table is missing {required!r}")

    vectors: list[_SpectrumVector] = []
    dataset_meta = getattr(library, "meta", None)
    for _row_index, row in index_frame.iterrows():
        spectrum_id = str(row["spectrum_id"])
        points = spectra_frame.loc[spectra_frame["spectrum_id"] == row["spectrum_id"]]
        if points.empty:
            continue
        metadata = {str(key): value for key, value in row.to_dict().items()}
        vectors.append(
            _SpectrumVector(
                spectrum_id=spectrum_id,
                lambda_values=pd.to_numeric(points["lambda"]).to_numpy(dtype=float),
                intensities=pd.to_numeric(points["intensity"]).to_numpy(dtype=float),
                lambda_unit=_first_present(metadata.get("lambda_unit"), _meta_value(dataset_meta, "lambda_unit")),
                intensity_unit=_first_present(
                    metadata.get("intensity_unit"), _meta_value(dataset_meta, "intensity_unit")
                ),
                metadata=metadata,
            )
        )
    return vectors


def _spectrum_vector(item: Any) -> _SpectrumVector:
    frame = _spectrum_frame(item)
    if frame.empty:
        raise ValueError("MatchSpectralLibrary: spectrum contains no points")
    if "lambda" not in frame.columns or "intensity" not in frame.columns:
        raise ValueError("MatchSpectralLibrary: spectrum data must contain 'lambda' and 'intensity' columns")

    metadata = dict(getattr(item, "user", {}) or {})
    spectrum_id = _metadata_value(item, "spectrum_id")
    if spectrum_id is None:
        spectrum_id = getattr(getattr(item, "framework", None), "object_id", None)
    if spectrum_id is None:
        raise ValueError("MatchSpectralLibrary: spectrum is missing spectrum_id metadata")

    return _SpectrumVector(
        spectrum_id=str(spectrum_id),
        lambda_values=pd.to_numeric(frame["lambda"]).to_numpy(dtype=float),
        intensities=pd.to_numeric(frame["intensity"]).to_numpy(dtype=float),
        lambda_unit=_metadata_value(item, "lambda_unit"),
        intensity_unit=_metadata_value(item, "intensity_unit"),
        metadata=metadata,
    )


def _spectrum_frame(item: Any) -> pd.DataFrame:
    raw = _raw_data(item)
    if isinstance(raw, pd.Series):
        return pd.DataFrame({"lambda": raw.index.to_numpy(), "intensity": raw.to_numpy()})
    frame = _coerce_frame(raw)
    if "lambda" in frame.columns and "intensity" in frame.columns:
        return frame[["lambda", "intensity"]].copy()

    index_name = getattr(item, "index_name", None)
    value_name = getattr(item, "value_name", None)
    if index_name in frame.columns and value_name in frame.columns:
        return frame[[index_name, value_name]].rename(columns={index_name: "lambda", value_name: "intensity"})

    if len(frame.columns) >= 2:
        first, second = frame.columns[:2]
        return frame[[first, second]].rename(columns={first: "lambda", second: "intensity"})
    raise ValueError("MatchSpectralLibrary: spectrum data must be tabular or a two-column array")


def _as_pandas_frame(obj: Any) -> pd.DataFrame:
    return _coerce_frame(_raw_data(obj))


def _coerce_frame(raw: Any) -> pd.DataFrame:
    if isinstance(raw, pd.DataFrame):
        return raw.reset_index(drop=True).copy()
    if hasattr(raw, "to_pandas"):
        return cast(pd.DataFrame, raw.to_pandas()).reset_index(drop=True)
    if isinstance(raw, dict):
        return pd.DataFrame(raw).reset_index(drop=True)
    array = np.asarray(raw)
    if array.ndim == 1:
        return pd.DataFrame({"lambda": np.arange(array.size, dtype=float), "intensity": array.astype(float)})
    if array.ndim == 2:
        return pd.DataFrame(array).reset_index(drop=True)
    raise ValueError(f"MatchSpectralLibrary: unsupported tabular data shape {array.shape}")


def _raw_data(obj: Any) -> Any:
    raw = getattr(obj, "_data", None)
    if raw is not None:
        return raw
    raw = getattr(obj, "_arrow_table", None)
    if raw is not None:
        return raw
    try:
        return obj.get_in_memory_data()
    except Exception:
        pass
    try:
        return obj.to_memory()
    except Exception as exc:
        raise ValueError(f"MatchSpectralLibrary: object {type(obj).__name__} has no readable in-memory data") from exc


def _slot(obj: Any, name: str) -> Any:
    slots = getattr(obj, "slots", None)
    if isinstance(slots, dict) and name in slots:
        return slots[name]
    private_slots = getattr(obj, "_slots", None)
    if isinstance(private_slots, dict) and name in private_slots:
        return private_slots[name]
    getter = getattr(obj, "get", None)
    if callable(getter):
        try:
            return getter(name)
        except Exception:
            pass
    raise ValueError(f"MatchSpectralLibrary: library is missing {name!r} slot")


def _require_collection(payload: Any, name: str) -> list[Any]:
    if not isinstance(payload, Collection):
        raise ValueError(f"MatchSpectralLibrary: input {name!r} must be a Collection[Spectrum]")
    return list(payload)


def _require_single_or_object(payload: Any, name: str) -> Any:
    if payload is None:
        raise ValueError(f"MatchSpectralLibrary: missing required input {name!r}")
    if isinstance(payload, Collection):
        if len(payload) != 1:
            raise ValueError(f"MatchSpectralLibrary: input {name!r} must contain exactly one item")
        return payload[0]
    return payload


def _metadata_value(item: Any, name: str) -> str | None:
    user = getattr(item, "user", {}) or {}
    if name in user and user[name] is not None:
        return str(user[name])
    attr = getattr(item, name, None)
    if attr is not None:
        return str(attr)
    value = _meta_value(getattr(item, "meta", None), name)
    return str(value) if value is not None else None


def _meta_value(meta: Any, name: str) -> Any:
    if meta is None:
        return None
    if hasattr(meta, name):
        return getattr(meta, name)
    if isinstance(meta, dict):
        return meta.get(name)
    return None


def _first_present(*values: Any) -> str | None:
    for value in values:
        if value is not None and value == value:
            return str(value)
    return None


def _dataframe_collection(rows: list[dict[str, Any]]) -> Collection:
    frame = pd.DataFrame(rows, columns=_OUTPUT_COLUMNS)
    result = DataFrame(columns=list(frame.columns), row_count=len(frame))
    result._data = frame
    return Collection(items=[result], item_type=DataFrame)


__all__ = ["MatchSpectralLibrary"]
