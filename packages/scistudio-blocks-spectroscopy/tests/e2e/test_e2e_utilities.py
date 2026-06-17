"""End-to-end tests for the 5 conversion/transport utility blocks (US5, FR-040..FR-051, FR-084).

Covers SpectrumToSpectralDataset, SpectralDatasetToSpectrum, FilterSpectralDataset,
MergeSpectralDataset, AttachFeaturesToSpectralDataset. Tests assert id/metadata
round-trips, slot restriction, duplicate-id merge policies, unit-mismatch ERROR,
and feature-join conflict policies.
"""

from __future__ import annotations

import fixtures as fx
import numpy as np
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

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.testing import BlockTestHarness


def _cfg(**params: object) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _dataset(out: dict) -> SpectralDataset:
    return next(iter(out["dataset"]))


@pytest.mark.parametrize(
    "block_cls",
    [
        SpectrumToSpectralDataset,
        SpectralDatasetToSpectrum,
        FilterSpectralDataset,
        MergeSpectralDataset,
        AttachFeaturesToSpectralDataset,
    ],
)
def test_block_validates(block_cls: type) -> None:
    assert not BlockTestHarness(block_cls).validate_block()


# ---------------------------------------------------------------------------
# Spectrum <-> Dataset round-trip (FR-040..FR-046)
# ---------------------------------------------------------------------------


def test_spectrum_to_dataset_and_back_round_trips_id_and_metadata() -> None:
    specs, _ = fx.make_collection(n=3)
    coll = _support.spectra_collection(specs)

    ds_out = SpectrumToSpectralDataset().run({"spectra": coll}, _cfg())
    dataset = _dataset(ds_out)
    index_tbl, spectra_tbl = _support.dataset_frames(dataset)
    assert "spectrum_id" in index_tbl.column_names
    assert {"spectrum_id", "lambda", "intensity"}.issubset(spectra_tbl.column_names)
    assert index_tbl.num_rows == 3
    # user metadata columns (material/method/replicate) land in the index.
    assert "material" in index_tbl.column_names

    sp_out = SpectralDatasetToSpectrum().run({"dataset": dataset}, _cfg())
    back = list(sp_out["spectra"])
    assert [s.spectrum_id for s in back] == ["spec_0", "spec_1", "spec_2"]
    # numeric payload round-trips.
    lam0, in0 = _support.spectrum_arrays(specs[0])
    blam0, bin0 = _support.spectrum_arrays(back[0])
    assert np.allclose(lam0, blam0) and np.allclose(in0, bin0)
    # typed unit metadata survives.
    assert isinstance(back[0].meta, Spectrum.Meta)
    assert back[0].meta.lambda_unit == "nm"


def test_dataset_to_spectrum_attaches_index_metadata() -> None:
    index = _support.dataframe_from_rows([{"spectrum_id": "a", "material": "X", "lambda_unit": "nm"}])
    spectra = _support.dataframe_from_rows(
        [
            {"spectrum_id": "a", "lambda": 400.0, "intensity": 1.0},
            {"spectrum_id": "a", "lambda": 401.0, "intensity": 2.0},
        ]
    )
    dataset = _support.build_spectral_dataset(index, spectra, meta=SpectralDataset.Meta(modality="raman"))
    out = SpectralDatasetToSpectrum().run({"dataset": dataset}, _cfg())
    spec = next(iter(out["spectra"]))
    assert spec.spectrum_id == "a"
    assert isinstance(spec.meta, Spectrum.Meta)
    assert spec.meta.lambda_unit == "nm"
    assert spec.meta.modality == "raman"  # dataset-level default applied
    assert spec.user is not None and spec.user.get("material") == "X"


# ---------------------------------------------------------------------------
# FilterSpectralDataset (FR-047, FR-048)
# ---------------------------------------------------------------------------


def test_filter_restricts_both_slots() -> None:
    specs, _ = fx.make_collection(n=4)
    dataset = _dataset(SpectrumToSpectralDataset().run({"spectra": _support.spectra_collection(specs)}, _cfg()))
    out = FilterSpectralDataset().run({"dataset": dataset}, _cfg(predicates={"material": "polymerA"}))
    filtered = _dataset(out)
    index_tbl, spectra_tbl = _support.dataset_frames(filtered)
    kept = set(index_tbl.column("spectrum_id").to_pylist())
    # polymerA == spec_0, spec_2 (materials alternate).
    assert kept == {"spec_0", "spec_2"}
    assert set(spectra_tbl.column("spectrum_id").to_pylist()) == kept


def test_filter_empty_result() -> None:
    specs, _ = fx.make_collection(n=2)
    dataset = _dataset(SpectrumToSpectralDataset().run({"spectra": _support.spectra_collection(specs)}, _cfg()))
    out = FilterSpectralDataset().run({"dataset": dataset}, _cfg(predicates={"material": "nonexistent"}))
    index_tbl, spectra_tbl = _support.dataset_frames(_dataset(out))
    assert index_tbl.num_rows == 0 and spectra_tbl.num_rows == 0


def test_filter_unknown_column_raises() -> None:
    specs, _ = fx.make_collection(n=2)
    dataset = _dataset(SpectrumToSpectralDataset().run({"spectra": _support.spectra_collection(specs)}, _cfg()))
    with pytest.raises(ValueError, match="unknown predicate column"):
        FilterSpectralDataset().run({"dataset": dataset}, _cfg(predicates={"ghost": 1}))


# ---------------------------------------------------------------------------
# MergeSpectralDataset (FR-049, FR-050, FR-051)
# ---------------------------------------------------------------------------


def _single_dataset(ids: list[str], unit: str = "nm") -> SpectralDataset:
    index = _support.dataframe_from_rows([{"spectrum_id": sid} for sid in ids])
    spectra = _support.dataframe_from_rows([{"spectrum_id": sid, "lambda": 400.0, "intensity": 1.0} for sid in ids])
    return _support.build_spectral_dataset(index, spectra, meta=SpectralDataset.Meta(lambda_unit=unit))


def test_merge_distinct_ids_appends() -> None:
    a = _single_dataset(["a1", "a2"])
    b = _single_dataset(["b1"])
    out = MergeSpectralDataset().run(
        {"datasets": Collection([a, b], item_type=SpectralDataset)},
        _cfg(duplicate_id_policy="error"),
    )
    index_tbl, _ = _support.dataset_frames(_dataset(out))
    assert set(index_tbl.column("spectrum_id").to_pylist()) == {"a1", "a2", "b1"}


def test_merge_duplicate_id_errors_by_default() -> None:
    a = _single_dataset(["dup"])
    b = _single_dataset(["dup"])
    with pytest.raises(ValueError, match="duplicate spectrum_id"):
        MergeSpectralDataset().run(
            {"datasets": Collection([a, b], item_type=SpectralDataset)},
            _cfg(duplicate_id_policy="error"),
        )


def test_merge_duplicate_prefix_policy() -> None:
    a = _single_dataset(["dup"])
    b = _single_dataset(["dup"])
    out = MergeSpectralDataset().run(
        {"datasets": Collection([a, b], item_type=SpectralDataset)},
        _cfg(duplicate_id_policy="prefix"),
    )
    index_tbl, _ = _support.dataset_frames(_dataset(out))
    ids = index_tbl.column("spectrum_id").to_pylist()
    assert len(set(ids)) == 2  # the second 'dup' was remapped with a prefix
    assert "dup" in ids


def test_merge_duplicate_remap_policy() -> None:
    a = _single_dataset(["dup"])
    b = _single_dataset(["dup"])
    out = MergeSpectralDataset().run(
        {"datasets": Collection([a, b], item_type=SpectralDataset)},
        _cfg(duplicate_id_policy="remap"),
    )
    index_tbl, spectra_tbl = _support.dataset_frames(_dataset(out))
    ids = index_tbl.column("spectrum_id").to_pylist()
    assert len(set(ids)) == 2
    # remap applies consistently to both slots (FR-050).
    assert set(spectra_tbl.column("spectrum_id").to_pylist()) == set(ids)


def test_merge_unit_mismatch_errors() -> None:
    a = _single_dataset(["a1"], unit="nm")
    b = _single_dataset(["b1"], unit="cm-1")
    with pytest.raises(ValueError, match="incompatible lambda_unit"):
        MergeSpectralDataset().run(
            {"datasets": Collection([a, b], item_type=SpectralDataset)},
            _cfg(duplicate_id_policy="error"),
        )


# ---------------------------------------------------------------------------
# AttachFeaturesToSpectralDataset (FR-084, FR-085)
# ---------------------------------------------------------------------------


def test_attach_features_joins_by_spectrum_id() -> None:
    specs, _ = fx.make_collection(n=2)
    dataset = _dataset(SpectrumToSpectralDataset().run({"spectra": _support.spectra_collection(specs)}, _cfg()))
    features = _support.dataframe_from_rows(
        [{"spectrum_id": "spec_0", "auc": 11.0}, {"spectrum_id": "spec_1", "auc": 22.0}]
    )
    out = AttachFeaturesToSpectralDataset().run(
        {"dataset": dataset, "features": features},
        _cfg(conflict_policy="error"),
    )
    index_tbl, _ = _support.dataset_frames(_dataset(out))
    assert "auc" in index_tbl.column_names
    pdf = index_tbl.to_pandas().set_index("spectrum_id")
    assert float(pdf.loc["spec_0", "auc"]) == 11.0
    assert float(pdf.loc["spec_1", "auc"]) == 22.0


def test_attach_features_conflict_error_policy() -> None:
    specs, _ = fx.make_collection(n=2)
    dataset = _dataset(SpectrumToSpectralDataset().run({"spectra": _support.spectra_collection(specs)}, _cfg()))
    # 'material' already exists in the index -> error policy must reject the join.
    features = _support.dataframe_from_rows([{"spectrum_id": "spec_0", "material": "Z"}])
    with pytest.raises(ValueError, match="collide"):
        AttachFeaturesToSpectralDataset().run(
            {"dataset": dataset, "features": features},
            _cfg(conflict_policy="error"),
        )


def test_attach_features_conflict_prefix_policy() -> None:
    specs, _ = fx.make_collection(n=2)
    dataset = _dataset(SpectrumToSpectralDataset().run({"spectra": _support.spectra_collection(specs)}, _cfg()))
    features = _support.dataframe_from_rows([{"spectrum_id": "spec_0", "material": "Z"}])
    out = AttachFeaturesToSpectralDataset().run(
        {"dataset": dataset, "features": features},
        _cfg(conflict_policy="prefix"),
    )
    index_tbl, _ = _support.dataset_frames(_dataset(out))
    assert "feature_material" in index_tbl.column_names  # prefixed, not overwritten
    assert "material" in index_tbl.column_names  # original kept
