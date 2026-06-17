"""Smoke tests for the five conversion/transport utility blocks (FR-040..FR-052,
FR-084, FR-085; scenarios SC-009..SC-014).

Each test builds synthetic inputs via ``_support`` helpers, runs the block's
``run()``, and asserts output ports, item counts, key data, and round-trip /
policy behaviour. These blocks only move data between ``Collection[Spectrum]``
and ``SpectralDataset`` shapes; they perform no scientific processing (FR-052).
"""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pandas as pd
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks.utilities import (
    AttachFeaturesToSpectralDataset,
    FilterSpectralDataset,
    MergeSpectralDataset,
    SpectralDatasetToSpectrum,
    SpectrumToSpectralDataset,
)
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.testing import BlockTestHarness

_LAM = np.linspace(400.0, 1000.0, 8)


def _config(**params: Any) -> BlockConfig:
    return BlockConfig(params=params)


def _run(block: Block, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
    """Invoke ``run`` with bare DataObject inputs (the real runtime shape).

    These blocks accept either a ``Collection`` or a bare ``DataObject`` per
    port (handled by the ``_support.coerce_*`` helpers); the cast keeps the call
    type-clean against the declared ``dict[str, Collection]`` signature.
    """
    return block.run(cast("dict[str, Collection]", inputs), config)


def _spectrum(spectrum_id: str, material: str, *, lambda_unit: str = "cm-1") -> Spectrum:
    inten = np.sin(_LAM / 100.0) + 1.0
    return _support.build_spectrum(
        _LAM,
        inten,
        meta=Spectrum.Meta(lambda_unit=lambda_unit, intensity_unit="a.u.", instrument="RamanX"),
        user={"material": material},
        spectrum_id=spectrum_id,
    )


def _spectra(*specs: Spectrum) -> Collection:
    return Collection(items=list(specs), item_type=Spectrum)


def _first(collection: Any) -> Any:
    return next(iter(collection))


def _dataset(*specs: Spectrum) -> SpectralDataset:
    out = _run(SpectrumToSpectralDataset(), {"spectra": _spectra(*specs)}, _config())
    return cast("SpectralDataset", _first(out["dataset"]))


def test_validate_block_contract() -> None:
    for cls in (
        SpectrumToSpectralDataset,
        SpectralDatasetToSpectrum,
        FilterSpectralDataset,
        MergeSpectralDataset,
        AttachFeaturesToSpectralDataset,
    ):
        assert not BlockTestHarness(cls).validate_block()


def test_spectrum_to_dataset_builds_both_slots() -> None:  # SC-009
    out = _run(
        SpectrumToSpectralDataset(),
        {"spectra": _spectra(_spectrum("s1", "gold"), _spectrum("s2", "silver"))},
        _config(),
    )
    assert set(out) == {"dataset"}
    dataset = _first(out["dataset"])
    index_tbl, spectra_tbl = _support.dataset_frames(dataset)
    # index: one row per spectrum keyed by spectrum_id, with typed + user metadata.
    assert index_tbl.num_rows == 2
    assert set(index_tbl.column("spectrum_id").to_pylist()) == {"s1", "s2"}
    assert {"material", "instrument", "lambda_unit"}.issubset(set(index_tbl.column_names))
    # spectra: long-form lambda/intensity (8 points x 2 spectra).
    assert spectra_tbl.num_rows == 16
    assert set(spectra_tbl.column_names) >= {"spectrum_id", "lambda", "intensity"}


def test_spectrum_to_dataset_metadata_join() -> None:  # SC-010
    coll = _spectra(_spectrum("s1", "gold"), _spectrum("s2", "silver"))
    meta = _support.dataframe_from_pandas(pd.DataFrame({"spectrum_id": ["s1", "s2"], "batch": ["B1", "B2"]}))
    out = _run(
        SpectrumToSpectralDataset(), {"spectra": coll, "metadata": meta}, _config(metadata_join_key="spectrum_id")
    )
    index_tbl, _ = _support.dataset_frames(_first(out["dataset"]))
    pairs = dict(zip(index_tbl.column("spectrum_id").to_pylist(), index_tbl.column("batch").to_pylist(), strict=True))
    assert pairs == {"s1": "B1", "s2": "B2"}


def test_dataset_to_spectrum_round_trip() -> None:  # SC-011
    dataset = _dataset(_spectrum("s1", "gold"), _spectrum("s2", "silver"))
    out = _run(SpectralDatasetToSpectrum(), {"dataset": dataset}, _config())
    assert set(out) == {"spectra"}
    spectra = list(out["spectra"])
    assert len(spectra) == 2
    assert {sp.spectrum_id for sp in spectra} == {"s1", "s2"}
    sp1 = next(sp for sp in spectra if sp.spectrum_id == "s1")
    assert isinstance(sp1.meta, Spectrum.Meta)
    assert sp1.meta.lambda_unit == "cm-1"
    assert sp1.meta.instrument == "RamanX"
    assert sp1.user and sp1.user.get("material") == "gold"
    lam, _inten = _support.spectrum_arrays(sp1)
    np.testing.assert_allclose(lam, _LAM)


def test_filter_dataset_restricts_both_slots() -> None:  # SC-012
    dataset = _dataset(_spectrum("s1", "gold"), _spectrum("s2", "silver"))
    out = _run(FilterSpectralDataset(), {"dataset": dataset}, _config(predicates={"material": "gold"}))
    index_tbl, spectra_tbl = _support.dataset_frames(_first(out["dataset"]))
    assert index_tbl.column("spectrum_id").to_pylist() == ["s1"]
    assert set(spectra_tbl.column("spectrum_id").to_pylist()) == {"s1"}
    assert spectra_tbl.num_rows == 8

    # list/`in` predicate form keeps both.
    out_in = _run(
        FilterSpectralDataset(),
        {"dataset": dataset},
        _config(predicates=[{"column": "material", "op": "in", "value": ["gold", "silver"]}]),
    )
    kept, _ = _support.dataset_frames(_first(out_in["dataset"]))
    assert kept.num_rows == 2


def test_merge_dataset_duplicate_and_unit_policies() -> None:  # SC-013
    ds_a = _dataset(_spectrum("s1", "a"))
    ds_b = _dataset(_spectrum("s1", "b"))

    # Default error on duplicate spectrum_id (FR-050).
    with pytest.raises(ValueError, match="duplicate spectrum_id"):
        _run(
            MergeSpectralDataset(),
            {"datasets": Collection(items=[ds_a, ds_b], item_type=SpectralDataset)},
            _config(duplicate_id_policy="error"),
        )

    # Prefix policy makes ids unique and keeps spectra slot consistent.
    out = _run(
        MergeSpectralDataset(),
        {"datasets": Collection(items=[ds_a, ds_b], item_type=SpectralDataset)},
        _config(duplicate_id_policy="prefix"),
    )
    index_tbl, spectra_tbl = _support.dataset_frames(_first(out["dataset"]))
    merged_ids = index_tbl.column("spectrum_id").to_pylist()
    assert len(merged_ids) == 2 and len(set(merged_ids)) == 2
    assert set(spectra_tbl.column("spectrum_id").to_pylist()) == set(merged_ids)

    # Unit mismatch must fail (FR-051).
    ds_nm = _dataset(_spectrum("u1", "x", lambda_unit="nm"))
    with pytest.raises(ValueError, match="incompatible lambda_unit"):
        _run(
            MergeSpectralDataset(),
            {"datasets": Collection(items=[ds_a, ds_nm], item_type=SpectralDataset)},
            _config(duplicate_id_policy="prefix"),
        )


def test_attach_features_conflict_policies() -> None:  # SC-014
    dataset = _dataset(_spectrum("s1", "gold"), _spectrum("s2", "silver"))
    _, spectra_before = _support.dataset_frames(dataset)

    # Non-colliding join adds the feature column; spectra slot unchanged (FR-084).
    feat = _support.dataframe_from_pandas(pd.DataFrame({"spectrum_id": ["s1", "s2"], "auc": [1.5, 2.5]}))
    out = _run(
        AttachFeaturesToSpectralDataset(), {"dataset": dataset, "features": feat}, _config(conflict_policy="error")
    )
    index_tbl, spectra_after = _support.dataset_frames(_first(out["dataset"]))
    assert "auc" in index_tbl.column_names
    assert dict(zip(index_tbl.column("spectrum_id").to_pylist(), index_tbl.column("auc").to_pylist(), strict=True)) == {
        "s1": 1.5,
        "s2": 2.5,
    }
    assert spectra_after.num_rows == spectra_before.num_rows

    # Colliding column under default error policy must raise (FR-085).
    feat_collide = _support.dataframe_from_pandas(pd.DataFrame({"spectrum_id": ["s1", "s2"], "material": ["X", "Y"]}))
    with pytest.raises(ValueError, match="collide"):
        _run(
            AttachFeaturesToSpectralDataset(),
            {"dataset": dataset, "features": feat_collide},
            _config(conflict_policy="error"),
        )

    # Prefix policy keeps both columns.
    out_prefix = _run(
        AttachFeaturesToSpectralDataset(),
        {"dataset": dataset, "features": feat_collide},
        _config(conflict_policy="prefix"),
    )
    cols = _support.dataset_frames(_first(out_prefix["dataset"]))[0].column_names
    assert "material" in cols and "feature_material" in cols
