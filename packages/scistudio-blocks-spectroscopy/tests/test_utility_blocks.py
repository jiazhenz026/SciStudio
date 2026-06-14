"""Utility block contract tests (SC-008..SC-014).

Covers the nine utility blocks of FR-032:

- SC-008: exactly the nine utility blocks are registered.
- SC-009: ``LoadSpectrum`` mints a unique ``spectrum_id`` and keeps
  ``source_file`` separate from the id (FR-035/FR-036).
- SC-010: ``SpectrumToSpectralDataset`` joins metadata by ``spectrum_id`` and by
  ``source_file``/``filename``.
- SC-011: ``SpectralDatasetToSpectrum`` round-trips index-row metadata onto the
  emitted spectra, and the dataset<->spectra conversion preserves spectrum_id.
- SC-012: ``FilterSpectralDataset`` filters both slots by spectrum_id without
  changing spectral values.
- SC-013: ``MergeSpectralDataset`` rejects duplicate ids by default and respects
  explicit duplicate-id policies.
- SC-014: ``AttachFeaturesToSpectralDataset`` joins flat feature tables onto
  ``index`` by spectrum_id, rejects a missing join key, and leaves ``spectra``
  unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks import utilities
from scistudio_blocks_spectroscopy.blocks.utilities import (
    AttachFeaturesToSpectralDataset,
    FilterSpectralDataset,
    LoadSpectrum,
    MergeSpectralDataset,
    SpectralDatasetToSpectrum,
    SpectrumToSpectralDataset,
)
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio.testing import BlockTestHarness

_UTILITY_BLOCK_NAMES = {
    "LoadSpectrum",
    "SaveSpectrum",
    "LoadSpectralDataset",
    "SaveSpectralDataset",
    "SpectrumToSpectralDataset",
    "SpectralDatasetToSpectrum",
    "FilterSpectralDataset",
    "MergeSpectralDataset",
    "AttachFeaturesToSpectralDataset",
}


def _config(**params: Any) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _spectrum(
    sid: str | None = None,
    *,
    lam: Any = (1.0, 2.0, 3.0),
    inten: Any = (10.0, 20.0, 30.0),
    source_file: str | None = None,
    sample_label: str | None = None,
) -> Spectrum:
    meta = Spectrum.Meta(
        lambda_unit="nm",
        intensity_unit="au",
        lambda_kind="wavelength",
        modality="raman",
        spectrum_id=sid,
        source_file=source_file,
        sample_label=sample_label,
    )
    return _support.build_spectrum(np.asarray(lam, dtype=float), np.asarray(inten, dtype=float), meta=meta)


def _to_dataset(spectra: list[Spectrum], **config: Any) -> SpectralDataset:
    out = SpectrumToSpectralDataset().run({"spectra": _support.spectra_collection(spectra)}, _config(**config))
    return next(iter(out["dataset"]))


def _index_table(dataset: SpectralDataset) -> Any:
    index, _ = _support.dataset_frames(dataset)
    return index


def _spectra_table(dataset: SpectralDataset) -> Any:
    _, spectra = _support.dataset_frames(dataset)
    return spectra


# ---------------------------------------------------------------------------
# SC-008: roster
# ---------------------------------------------------------------------------


def test_exactly_nine_utility_blocks() -> None:
    names = {b.__name__ for b in utilities.BLOCKS}
    assert names == _UTILITY_BLOCK_NAMES
    assert len(utilities.BLOCKS) == 9


def test_utility_blocks_pass_harness() -> None:
    for cls in utilities.BLOCKS:
        assert not BlockTestHarness(cls).validate_block(), cls.__name__


# ---------------------------------------------------------------------------
# SC-009: LoadSpectrum id minting + source_file separation
# ---------------------------------------------------------------------------


def test_load_spectrum_mints_unique_ids(tmp_path: Path) -> None:
    from scistudio_blocks_spectroscopy.blocks.utilities import SaveSpectrum

    # Distinctive stems so the "id not derived from filename" check is meaningful.
    a = tmp_path / "alpha_sample.csv"
    b = tmp_path / "beta_sample.csv"
    SaveSpectrum().save(Collection([_spectrum("orig_a")], item_type=Spectrum), _config(path=str(a)))
    SaveSpectrum().save(Collection([_spectrum("orig_b")], item_type=Spectrum), _config(path=str(b)))
    result = LoadSpectrum().load(_config(path=[str(a), str(b)]))
    assert isinstance(result, Collection)
    ids = [s.spectrum_id for s in result]
    # FR-035: each loaded spectrum has a fresh, unique, non-None id.
    assert all(i is not None for i in ids)
    assert len(set(ids)) == 2
    # FR-036: ids are not derived from the filename; source_file kept separate.
    for spectrum, path in zip(result, (a, b), strict=True):
        assert path.stem not in (spectrum.spectrum_id or "")
        meta = spectrum.meta
        assert isinstance(meta, Spectrum.Meta)
        assert meta.source_file == str(path)


# ---------------------------------------------------------------------------
# SC-010: SpectrumToSpectralDataset metadata join
# ---------------------------------------------------------------------------


def test_spectrum_to_dataset_join_by_spectrum_id() -> None:
    spectra = [_spectrum("id1"), _spectrum("id2")]
    metadata = _support.dataframe_from_rows(
        [{"spectrum_id": "id1", "material": "gold"}, {"spectrum_id": "id2", "material": "silver"}]
    )
    out = SpectrumToSpectralDataset().run(
        {"spectra": _support.spectra_collection(spectra), "metadata": Collection([metadata], item_type=DataFrame)},
        _config(metadata_join_key="spectrum_id"),
    )
    index = _index_table(next(iter(out["dataset"])))
    assert "material" in index.column_names
    pairs = dict(zip(index.column("spectrum_id").to_pylist(), index.column("material").to_pylist(), strict=True))
    assert pairs == {"id1": "gold", "id2": "silver"}


def test_spectrum_to_dataset_join_by_source_file() -> None:
    spectra = [
        _spectrum("id1", source_file="/data/one.csv"),
        _spectrum("id2", source_file="/data/two.csv"),
    ]
    metadata = _support.dataframe_from_rows(
        [
            {"source_file": "/data/one.csv", "condition": "wet"},
            {"source_file": "/data/two.csv", "condition": "dry"},
        ]
    )
    out = SpectrumToSpectralDataset().run(
        {"spectra": _support.spectra_collection(spectra), "metadata": Collection([metadata], item_type=DataFrame)},
        _config(metadata_join_key="source_file"),
    )
    index = _index_table(next(iter(out["dataset"])))
    assert "condition" in index.column_names
    pairs = dict(zip(index.column("spectrum_id").to_pylist(), index.column("condition").to_pylist(), strict=True))
    assert pairs == {"id1": "wet", "id2": "dry"}


# ---------------------------------------------------------------------------
# SC-011: round-trip dataset <-> spectra
# ---------------------------------------------------------------------------


def test_dataset_to_spectrum_roundtrips_index_metadata() -> None:
    spectra = [_spectrum("id1", sample_label="A"), _spectrum("id2", sample_label="B")]
    dataset = _to_dataset(spectra)
    back = SpectralDatasetToSpectrum().run({"dataset": Collection([dataset], item_type=SpectralDataset)}, _config())
    out = list(back["spectra"])
    assert [s.spectrum_id for s in out] == ["id1", "id2"]
    labels = []
    for spectrum in out:
        meta = spectrum.meta
        assert isinstance(meta, Spectrum.Meta)
        labels.append(meta.sample_label)
    assert labels == ["A", "B"]


def test_dataset_spectra_roundtrip_preserves_payload() -> None:
    spectra = [_spectrum("id1", lam=(1.0, 2.0, 3.0), inten=(4.0, 5.0, 6.0))]
    dataset = _to_dataset(spectra)
    back = SpectralDatasetToSpectrum().run({"dataset": Collection([dataset], item_type=SpectralDataset)}, _config())
    lam, inten = _support.spectrum_arrays(next(iter(back["spectra"])))
    assert np.allclose(lam, [1.0, 2.0, 3.0])
    assert np.allclose(inten, [4.0, 5.0, 6.0])


# ---------------------------------------------------------------------------
# SC-012: FilterSpectralDataset
# ---------------------------------------------------------------------------


def test_filter_restricts_both_slots_without_changing_values() -> None:
    spectra = [_spectrum("keep", inten=(7.0, 8.0, 9.0)), _spectrum("drop", inten=(1.0, 2.0, 3.0))]
    dataset = _to_dataset(spectra)
    out = FilterSpectralDataset().run(
        {"dataset": Collection([dataset], item_type=SpectralDataset)},
        _config(predicates={"spectrum_id": "keep"}),
    )
    filtered = next(iter(out["dataset"]))
    index = _index_table(filtered)
    spectra_table = _spectra_table(filtered)
    assert index.column("spectrum_id").to_pylist() == ["keep"]
    assert set(spectra_table.column("spectrum_id").to_pylist()) == {"keep"}
    # Values for the kept spectrum are unchanged.
    kept_intensity = sorted(
        v
        for sid, v in zip(
            spectra_table.column("spectrum_id").to_pylist(),
            spectra_table.column("intensity").to_pylist(),
            strict=True,
        )
        if sid == "keep"
    )
    assert kept_intensity == [7.0, 8.0, 9.0]


# ---------------------------------------------------------------------------
# SC-013: MergeSpectralDataset duplicate-id policy
# ---------------------------------------------------------------------------


def test_merge_rejects_duplicate_ids_by_default() -> None:
    ds1 = _to_dataset([_spectrum("dup"), _spectrum("a")])
    ds2 = _to_dataset([_spectrum("dup"), _spectrum("b")])
    with pytest.raises(ValueError):
        MergeSpectralDataset().run({"datasets": Collection([ds1, ds2], item_type=SpectralDataset)}, _config())


def test_merge_remap_policy_makes_ids_unique() -> None:
    ds1 = _to_dataset([_spectrum("dup"), _spectrum("a")])
    ds2 = _to_dataset([_spectrum("dup"), _spectrum("b")])
    out = MergeSpectralDataset().run(
        {"datasets": Collection([ds1, ds2], item_type=SpectralDataset)},
        _config(duplicate_id_policy="remap"),
    )
    merged = next(iter(out["dataset"]))
    index = _index_table(merged)
    ids = index.column("spectrum_id").to_pylist()
    assert index.num_rows == 4
    assert len(set(ids)) == 4  # all unique after remap
    # spectra slot stays consistent with the remapped index ids.
    spectra_ids = set(_spectra_table(merged).column("spectrum_id").to_pylist())
    assert spectra_ids <= set(ids)


# ---------------------------------------------------------------------------
# SC-014: AttachFeaturesToSpectralDataset
# ---------------------------------------------------------------------------


def test_attach_features_joins_onto_index() -> None:
    dataset = _to_dataset([_spectrum("a"), _spectrum("b")])
    features = _support.dataframe_from_rows([{"spectrum_id": "a", "auc": 1.5}, {"spectrum_id": "b", "auc": 2.5}])
    out = AttachFeaturesToSpectralDataset().run(
        {
            "dataset": Collection([dataset], item_type=SpectralDataset),
            "features": Collection([features], item_type=DataFrame),
        },
        _config(),
    )
    result = next(iter(out["dataset"]))
    index = _index_table(result)
    assert "auc" in index.column_names
    pairs = dict(zip(index.column("spectrum_id").to_pylist(), index.column("auc").to_pylist(), strict=True))
    assert pairs == {"a": 1.5, "b": 2.5}
    # SC-014: spectra slot is unchanged.
    spectra_table = _spectra_table(result)
    assert spectra_table.column_names == ["spectrum_id", "lambda", "intensity"]


def test_attach_features_rejects_missing_join_key() -> None:
    dataset = _to_dataset([_spectrum("a")])
    bad_features = _support.dataframe_from_rows([{"wrong_key": "a", "auc": 1.0}])
    with pytest.raises(ValueError):
        AttachFeaturesToSpectralDataset().run(
            {
                "dataset": Collection([dataset], item_type=SpectralDataset),
                "features": Collection([bad_features], item_type=DataFrame),
            },
            _config(),
        )
