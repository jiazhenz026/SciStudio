"""End-to-end tests for MatchSpectralLibrary (US11, FR-121..FR-126).

Builds a library-shaped ``SpectralDataset`` and query spectra, runs the block,
and asserts the correct top-1 match, rank ordering (rank 1 == best for both
similarity- and distance-oriented methods), top_k handling, and the default
ERROR-on-incompatible-grid behavior (reported as a non-success status row).
"""

from __future__ import annotations

from typing import Any

import fixtures as fx
import numpy as np
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks.library_matching import MatchSpectralLibrary
from scistudio_blocks_spectroscopy.types import Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.testing import BlockTestHarness


def _cfg(**params: object) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _frame(out: dict) -> Any:
    return _support.dataframe_pandas(next(iter(out["matches"])))


def test_block_validates() -> None:
    assert not BlockTestHarness(MatchSpectralLibrary).validate_block()


def test_match_correct_top1() -> None:
    library, truth = fx.make_library_dataset()
    # Query == the ref_520 entry exactly -> top-1 must be ref_520.
    query = _support.build_spectrum(
        fx.DEFAULT_GRID,
        truth["ref_520"],
        meta=Spectrum.Meta(lambda_unit="nm", intensity_unit="au"),
        spectrum_id="q1",
    )
    out = MatchSpectralLibrary().run(
        {"spectra": _support.spectra_collection([query]), "library": library},
        _cfg(method="cosine_similarity", top_k=1),
    )
    assert set(out) == {"matches"}
    df = _frame(out)
    assert {"spectrum_id", "library_spectrum_id", "method", "rank", "score", "status"} <= set(df.columns)
    best = df.sort_values("rank").iloc[0]
    assert int(best["rank"]) == 1
    assert best["library_spectrum_id"] == "ref_520"
    assert best["status"] == "success"


def test_match_top_k_ranking() -> None:
    library, truth = fx.make_library_dataset()
    query = _support.build_spectrum(fx.DEFAULT_GRID, truth["ref_500"], spectrum_id="q1")
    out = MatchSpectralLibrary().run(
        {"spectra": _support.spectra_collection([query]), "library": library},
        _cfg(method="cosine_similarity", top_k=3),
    )
    df = _frame(out).sort_values("rank")
    assert list(df["rank"]) == [1, 2, 3]
    assert df.iloc[0]["library_spectrum_id"] == "ref_500"  # rank 1 best
    # cosine: scores monotonically non-increasing with rank.
    scores = [float(s) for s in df["score"]]
    assert scores == sorted(scores, reverse=True)


def test_match_distance_method_ranks_smallest_first() -> None:
    library, truth = fx.make_library_dataset()
    query = _support.build_spectrum(fx.DEFAULT_GRID, truth["ref_480"], spectrum_id="q1")
    out = MatchSpectralLibrary().run(
        {"spectra": _support.spectra_collection([query]), "library": library},
        _cfg(method="euclidean_distance", top_k=3),
    )
    df = _frame(out).sort_values("rank")
    assert df.iloc[0]["library_spectrum_id"] == "ref_480"  # exact -> distance ~0
    scores = [float(s) for s in df["score"]]
    assert scores == sorted(scores)  # distance ascending with rank


def test_match_top_k_larger_than_library() -> None:
    library, truth = fx.make_library_dataset(entries=[("only", fx.PeakSpec("gaussian", 5.0, 500.0, 8.0))])
    query = _support.build_spectrum(fx.DEFAULT_GRID, truth["only"], spectrum_id="q1")
    out = MatchSpectralLibrary().run(
        {"spectra": _support.spectra_collection([query]), "library": library},
        _cfg(method="cosine_similarity", top_k=10),
    )
    df = _frame(out)
    # top_k > library size: clamps to the available matches (1), no crash.
    assert len(df) == 1
    assert df.iloc[0]["library_spectrum_id"] == "only"


def test_match_incompatible_grid_status_by_default() -> None:
    library, _ = fx.make_library_dataset()
    bad_query = _support.build_spectrum(fx.DEFAULT_GRID + 1000.0, np.ones_like(fx.DEFAULT_GRID), spectrum_id="bad")
    out = MatchSpectralLibrary().run(
        {"spectra": _support.spectra_collection([bad_query]), "library": library},
        _cfg(method="cosine_similarity", top_k=1),
    )
    df = _frame(out)
    assert (df["status"] == "incompatible_grid").all()  # FR-126 no silent interp


def test_match_pearson_method_records_method() -> None:
    library, truth = fx.make_library_dataset()
    query = _support.build_spectrum(fx.DEFAULT_GRID, truth["ref_500"] * 2.0 + 1.0, spectrum_id="q1")
    out = MatchSpectralLibrary().run(
        {"spectra": _support.spectra_collection([query]), "library": library},
        _cfg(method="pearson_correlation", top_k=1),
    )
    df = _frame(out)
    assert df.iloc[0]["method"] == "pearson_correlation"
    # Pearson is invariant to affine scaling -> ref_500 is still rank-1.
    assert df.iloc[0]["library_spectrum_id"] == "ref_500"
