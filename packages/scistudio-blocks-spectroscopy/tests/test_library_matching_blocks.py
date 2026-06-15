"""Library matching block contract tests (SC-043..SC-046).

- SC-043: the library matching group is exactly ``MatchSpectralLibrary``.
- SC-044: only cosine_similarity / pearson_correlation / spectral_angle /
  euclidean_distance are exposed.
- SC-045: ``matches`` has spectrum_id / library_spectrum_id / method / rank /
  score / status, and ranks the best match as rank 1.
- SC-046: incompatible grids or units fail or report a non-success status by
  default (and no calibration/clustering/PCA/reporting block is registered).
"""

from __future__ import annotations

from typing import Any, cast

import numpy as np
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks import library_matching
from scistudio_blocks_spectroscopy.blocks.library_matching import MatchSpectralLibrary
from scistudio_blocks_spectroscopy.blocks.utilities import SpectrumToSpectralDataset
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.testing import BlockTestHarness


def _config(**params: Any) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _spectrum(sid: str, *, lam: Any, inten: Any) -> Spectrum:
    meta = Spectrum.Meta(
        lambda_unit="nm", intensity_unit="au", lambda_kind="wavelength", modality="raman", spectrum_id=sid
    )
    return _support.build_spectrum(np.asarray(lam, dtype=float), np.asarray(inten, dtype=float), meta=meta)


def _library(spectra: list[Spectrum]) -> SpectralDataset:
    out = SpectrumToSpectralDataset().run({"spectra": _support.spectra_collection(spectra)}, _config())
    return cast(SpectralDataset, next(iter(out["dataset"])))


def _matches(query: list[Spectrum], lib: SpectralDataset, **params: Any) -> Any:
    out = MatchSpectralLibrary().run(
        {"spectra": _support.spectra_collection(query), "library": Collection([lib], item_type=SpectralDataset)},
        _config(**params),
    )
    return _support.dataframe_arrow(next(iter(out["matches"])))


# ---------------------------------------------------------------------------
# SC-043: roster
# ---------------------------------------------------------------------------


def test_library_group_is_exactly_match_spectral_library() -> None:
    assert [b.__name__ for b in library_matching.BLOCKS] == ["MatchSpectralLibrary"]


def test_match_block_passes_harness() -> None:
    assert not BlockTestHarness(MatchSpectralLibrary).validate_block()


# ---------------------------------------------------------------------------
# SC-044: method enum
# ---------------------------------------------------------------------------


def test_match_methods_closed_set() -> None:
    enum = set(MatchSpectralLibrary.config_schema["properties"]["method"]["enum"])
    assert enum == {"cosine_similarity", "pearson_correlation", "spectral_angle", "euclidean_distance"}


# ---------------------------------------------------------------------------
# SC-045: matches schema + rank 1 = best
# ---------------------------------------------------------------------------


def test_matches_schema_and_rank_one_is_best() -> None:
    grid = np.linspace(0.0, 10.0, 11)
    ref_flat = _spectrum("flat", lam=grid, inten=np.ones_like(grid))
    ref_ramp = _spectrum("ramp", lam=grid, inten=grid)
    lib = _library([ref_flat, ref_ramp])
    query = _spectrum("q1", lam=grid, inten=grid)  # identical to the ramp
    table = _matches([query], lib, method="cosine_similarity", top_k=2)

    assert {"spectrum_id", "library_spectrum_id", "method", "rank", "score", "status"}.issubset(table.column_names)
    rows = sorted((r for r in table.to_pylist() if r["status"] == "success"), key=lambda r: r["rank"])
    assert rows, "expected at least one successful match"
    best = rows[0]
    assert best["rank"] == 1
    # Best match is the identical ramp reference.
    assert best["library_spectrum_id"] == "ramp"
    # rank 1 has the best (highest, for a similarity method) score.
    if len(rows) > 1:
        assert best["score"] >= rows[1]["score"]


# ---------------------------------------------------------------------------
# SC-046: incompatible grids / units fail or non-success by default
# ---------------------------------------------------------------------------


def test_incompatible_grid_is_non_success_by_default() -> None:
    query_grid = np.linspace(0.0, 10.0, 11)
    lib_grid = np.linspace(0.0, 10.0, 21)  # different length / grid
    lib = _library([_spectrum("ref", lam=lib_grid, inten=lib_grid)])
    query = _spectrum("q1", lam=query_grid, inten=query_grid)
    table = _matches([query], lib, method="cosine_similarity")
    statuses = set(table.column("status").to_pylist())
    # Default grid_policy="error": no success row for the incompatible grid.
    assert "success" not in statuses
    assert any(s != "success" for s in statuses)


def test_mixed_compatible_and_incompatible_library_rows_are_reported() -> None:
    query_grid = np.linspace(0.0, 10.0, 11)
    incompatible_grid = np.linspace(0.0, 10.0, 21)
    lib = _library(
        [
            _spectrum("compatible", lam=query_grid, inten=query_grid),
            _spectrum("incompatible", lam=incompatible_grid, inten=incompatible_grid),
        ]
    )
    query = _spectrum("q1", lam=query_grid, inten=query_grid)
    table = _matches([query], lib, method="cosine_similarity", top_k=1)
    rows = {row["library_spectrum_id"]: row for row in table.to_pylist()}

    assert rows["compatible"]["status"] == "success"
    assert rows["compatible"]["rank"] == 1
    assert rows["incompatible"]["status"] == "incompatible_grid"
    assert rows["incompatible"]["rank"] == 0
