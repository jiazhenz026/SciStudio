"""Spectroscopy library matching block (FR-121..FR-126).

One block, :class:`MatchSpectralLibrary`. It matches query spectra against a
library represented as a ``SpectralDataset`` (no separate library type, FR-122)
using a selectable similarity/distance method and emits a ranked ``matches``
table.

All matching math (cosine/pearson/spectral angle/euclidean) is pure numpy; no
scipy is required.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import pyarrow as pa

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.types import (
    INTENSITY_COLUMN,
    LAMBDA_COLUMN,
    SPECTRUM_ID_COLUMN,
    SpectralDataset,
    Spectrum,
)

#: Methods whose larger score means a better match (FR-125 orientation).
_SIMILARITY_METHODS = frozenset({"cosine_similarity", "pearson_correlation"})
#: Methods whose smaller score means a better match (distance orientation).
_DISTANCE_METHODS = frozenset({"spectral_angle", "euclidean_distance"})
_METHODS = _SIMILARITY_METHODS | _DISTANCE_METHODS

_STATUS_SUCCESS = "success"
_STATUS_INCOMPATIBLE = "incompatible_grid"
_STATUS_EMPTY_LIBRARY = "empty_library"

_MATCH_COLUMNS = (
    "spectrum_id",
    "library_spectrum_id",
    "method",
    "rank",
    "score",
    "status",
)


class MatchSpectralLibrary(ProcessBlock):
    """Rank library spectra against each query spectrum."""

    type_name: ClassVar[str] = "spectroscopy.match_spectral_library"
    name: ClassVar[str] = "Match Spectral Library"
    description: ClassVar[str] = "Match query spectra against a SpectralDataset library using a selectable method."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "library_matching"
    algorithm: ClassVar[str] = "match_spectral_library"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="spectra",
            accepted_types=[Spectrum],
            is_collection=True,
            required=True,
            description="Query spectra.",
        ),
        InputPort(
            name="library",
            accepted_types=[SpectralDataset],
            required=True,
            description="Library represented as a SpectralDataset.",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="matches", accepted_types=[DataFrame]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": [
                    "cosine_similarity",
                    "pearson_correlation",
                    "spectral_angle",
                    "euclidean_distance",
                ],
                "default": "cosine_similarity",
                "title": "Matching method",
            },
            "top_k": {"type": "integer", "default": 1, "minimum": 1, "title": "Top K matches"},
            "grid_policy": {
                "type": "string",
                "enum": ["error", "interpolate_library_to_query"],
                "default": "error",
                "title": "Grid/unit compatibility policy",
            },
        },
        "required": ["method"],
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Match queries against the library (FR-121..FR-126).

        Implementation plan:
          1. spectra = inputs['spectra']; library = inputs['library'] -> split its
             `index`/`spectra` slots into library spectra keyed by spectrum_id.
          2. Apply grid_policy: 'error' fail/non-success on incompatible grids or
             units; otherwise interpolate library onto query grid (FR-126).
          3. method (numpy): cosine = a.b/(|a||b|); pearson = corrcoef; spectral
             angle = arccos(cosine); euclidean = norm(a-b). rank 1 = best match
             regardless of similarity- vs distance-orientation (FR-125).
          4. Keep top_k per query; emit matches rows {spectrum_id,
             library_spectrum_id, method, rank, score, status} (FR-124).
        Edge cases: empty library; incompatible grids; ties in score.
        Test plan: test_library_matching_blocks.py::test_match_ranks_top_k,
          ::test_match_errors_on_incompatible_grid.
        """
        block = self.name
        method = str(config.get("method", "cosine_similarity"))
        if method not in _METHODS:
            raise ValueError(f"{block}: method must be one of {sorted(_METHODS)}, got {method!r}")
        top_k = int(config.get("top_k", 1))
        if top_k < 1:
            raise ValueError(f"{block}: top_k must be >= 1, got {top_k}")
        grid_policy = str(config.get("grid_policy", "error"))
        if grid_policy not in {"error", "interpolate_library_to_query"}:
            raise ValueError(
                f"{block}: grid_policy must be one of ['error', 'interpolate_library_to_query'], got {grid_policy!r}"
            )

        spectra = _support.coerce_spectra(inputs.get("spectra"), block=block, port="spectra")
        library = _support.coerce_dataset(inputs.get("library"), block=block, port="library")
        library_spectra = self._library_spectra(library)
        library_units = self._library_units(library)

        rows: list[dict[str, Any]] = []
        for query in spectra:
            rows.extend(self._match_query(query, library_spectra, library_units, method, top_k, grid_policy))

        matches_df = _support.dataframe_from_rows(rows, columns=list(_MATCH_COLUMNS)) if rows else _empty_matches()
        return {"matches": _support.dataframe_collection(matches_df)}

    # ------------------------------------------------------------------
    # Library extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _library_spectra(library: SpectralDataset) -> list[tuple[str, np.ndarray, np.ndarray]]:
        """Group the dataset ``spectra`` slot by ``spectrum_id`` (ordered).

        Returns ``(spectrum_id, lambda, intensity)`` tuples in index-row order
        when the ``index`` slot is present, otherwise first-seen order.
        """
        index_table, spectra_table = _support.dataset_frames(library)

        if SPECTRUM_ID_COLUMN not in spectra_table.column_names:
            raise ValueError(
                f"Match Spectral Library: library 'spectra' slot is missing the '{SPECTRUM_ID_COLUMN}' column."
            )
        ids = [str(value) for value in spectra_table.column(SPECTRUM_ID_COLUMN).to_pylist()]
        lam = np.asarray(spectra_table.column(LAMBDA_COLUMN).to_numpy(zero_copy_only=False), dtype=np.float64)
        inten = np.asarray(spectra_table.column(INTENSITY_COLUMN).to_numpy(zero_copy_only=False), dtype=np.float64)

        grouped: dict[str, tuple[list[float], list[float]]] = {}
        first_seen: list[str] = []
        for spectrum_id, lam_value, inten_value in zip(ids, lam, inten, strict=True):
            if spectrum_id not in grouped:
                grouped[spectrum_id] = ([], [])
                first_seen.append(spectrum_id)
            grouped[spectrum_id][0].append(float(lam_value))
            grouped[spectrum_id][1].append(float(inten_value))

        # Prefer the explicit index ordering when it covers the grouped ids.
        order = first_seen
        if SPECTRUM_ID_COLUMN in index_table.column_names:
            index_ids = [str(value) for value in index_table.column(SPECTRUM_ID_COLUMN).to_pylist()]
            if set(index_ids) >= set(grouped):
                order = [spectrum_id for spectrum_id in index_ids if spectrum_id in grouped]

        result: list[tuple[str, np.ndarray, np.ndarray]] = []
        for spectrum_id in order:
            lam_list, inten_list = grouped[spectrum_id]
            grid = np.asarray(lam_list, dtype=np.float64)
            sort_order = np.argsort(grid)
            result.append((spectrum_id, grid[sort_order], np.asarray(inten_list, dtype=np.float64)[sort_order]))
        return result

    @staticmethod
    def _library_units(library: SpectralDataset) -> tuple[str | None, str | None]:
        """Return the dataset-level ``(lambda_unit, intensity_unit)`` if typed."""
        meta = library.meta
        if isinstance(meta, SpectralDataset.Meta):
            return meta.lambda_unit, meta.intensity_unit
        return None, None

    # ------------------------------------------------------------------
    # Per-query matching
    # ------------------------------------------------------------------

    def _match_query(
        self,
        query: Spectrum,
        library_spectra: list[tuple[str, np.ndarray, np.ndarray]],
        library_units: tuple[str | None, str | None],
        method: str,
        top_k: int,
        grid_policy: str,
    ) -> list[dict[str, Any]]:
        query_id = query.spectrum_id
        if not library_spectra:
            return [_status_row(query_id, None, method, _STATUS_EMPTY_LIBRARY)]

        query_lambda, query_intensity = _support.spectrum_arrays(query)
        query_units = self._query_units(query)
        units_compatible = _units_compatible(query_units, library_units)

        scored: list[tuple[str, float]] = []
        incompatible: list[dict[str, Any]] = []
        for lib_id, lib_lambda, lib_intensity in library_spectra:
            aligned = _align_library(query_lambda, lib_lambda, lib_intensity, grid_policy)
            if aligned is None or not units_compatible:
                incompatible.append(_status_row(query_id, lib_id, method, _STATUS_INCOMPATIBLE))
                continue
            scored.append((lib_id, _score(method, query_intensity, aligned)))

        if not scored:
            # Every library entry was incompatible: surface the non-success rows.
            return incompatible

        descending = method in _SIMILARITY_METHODS
        ranked = sorted(scored, key=lambda item: item[1], reverse=descending)[:top_k]
        rows: list[dict[str, Any]] = [
            {
                "spectrum_id": query_id,
                "library_spectrum_id": lib_id,
                "method": method,
                "rank": rank,
                "score": float(score),
                "status": _STATUS_SUCCESS,
            }
            for rank, (lib_id, score) in enumerate(ranked, start=1)
        ]
        return rows

    @staticmethod
    def _query_units(query: Spectrum) -> tuple[str | None, str | None]:
        meta = query.meta
        if isinstance(meta, Spectrum.Meta):
            return meta.lambda_unit, meta.intensity_unit
        return None, None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _align_library(
    query_lambda: np.ndarray,
    lib_lambda: np.ndarray,
    lib_intensity: np.ndarray,
    grid_policy: str,
) -> np.ndarray | None:
    """Return library intensity on the query grid, or ``None`` if incompatible.

    The default ``grid_policy="error"`` reports a non-success match status (via
    the ``None`` sentinel) on grid mismatch rather than silently interpolating
    (FR-126). ``interpolate_library_to_query`` resamples explicitly.
    """
    if _support.grids_close(query_lambda, lib_lambda):
        return lib_intensity
    if grid_policy == "error":
        return None
    return np.asarray(np.interp(query_lambda, lib_lambda, lib_intensity), dtype=np.float64)


def _units_compatible(
    query_units: tuple[str | None, str | None],
    library_units: tuple[str | None, str | None],
) -> bool:
    """Return ``True`` unless both sides declare conflicting units (FR-126).

    Unknown (``None``) units are treated as compatible so that libraries lacking
    typed unit metadata still match; a mismatch is reported only when both sides
    explicitly declare differing units.
    """
    for query_unit, library_unit in zip(query_units, library_units, strict=True):
        if query_unit is not None and library_unit is not None and query_unit != library_unit:
            return False
    return True


def _score(method: str, a: np.ndarray, b: np.ndarray) -> float:
    """Compute the configured similarity/distance score (pure numpy)."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if method == "euclidean_distance":
        return float(np.linalg.norm(a - b))
    if method == "pearson_correlation":
        if a.size < 2:
            return 0.0
        a_centered = a - a.mean()
        b_centered = b - b.mean()
        denom = np.linalg.norm(a_centered) * np.linalg.norm(b_centered)
        return 0.0 if denom == 0.0 else float(np.dot(a_centered, b_centered) / denom)
    # cosine_similarity and spectral_angle both rely on the cosine.
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    cosine = 0.0 if denom == 0.0 else float(np.dot(a, b) / denom)
    if method == "cosine_similarity":
        return cosine
    # spectral_angle: arccos of the clamped cosine (radians); smaller is better.
    return float(np.arccos(np.clip(cosine, -1.0, 1.0)))


def _status_row(
    query_id: str | None,
    library_id: str | None,
    method: str,
    status: str,
) -> dict[str, Any]:
    """Build a non-success match row (rank 0, NaN score)."""
    return {
        "spectrum_id": query_id,
        "library_spectrum_id": library_id,
        "method": method,
        "rank": 0,
        "score": float("nan"),
        "status": status,
    }


def _empty_matches() -> DataFrame:
    """Return an empty ``matches`` table with the declared column schema."""
    table = pa.table(
        {
            "spectrum_id": pa.array([], type=pa.string()),
            "library_spectrum_id": pa.array([], type=pa.string()),
            "method": pa.array([], type=pa.string()),
            "rank": pa.array([], type=pa.int64()),
            "score": pa.array([], type=pa.float64()),
            "status": pa.array([], type=pa.string()),
        }
    )
    return _support.dataframe_from_arrow(table)


BLOCKS: list[type] = [MatchSpectralLibrary]

__all__ = ["BLOCKS", "MatchSpectralLibrary"]
