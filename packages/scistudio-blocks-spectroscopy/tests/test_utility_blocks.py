from __future__ import annotations

import pandas as pd
import pandas.testing as pdt
import pytest
from helpers import dataframe_collection, dataset_meta, make_dataset, make_spectrum, spectrum_frame, spectrum_meta
from scistudio_blocks_spectroscopy._tables import to_pandas_frame
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


def _dataset_collection(dataset: SpectralDataset) -> Collection:
    return Collection(items=[dataset], item_type=SpectralDataset)


def test_spectrum_collection_converts_to_spectral_dataset_with_metadata_join() -> None:
    spectra = Collection(
        items=[make_spectrum("s1", material="cell"), make_spectrum("s2", material="media")],
        item_type=Spectrum,
    )
    metadata = dataframe_collection(pd.DataFrame({"spectrum_id": ["s1", "s2"], "condition": ["drug", "control"]}))

    result = SpectrumToSpectralDataset().run(
        {"spectra": spectra, "metadata": metadata},
        BlockConfig(params={"dataset_name": "joined"}),
    )
    dataset = result["dataset"][0]
    index = to_pandas_frame(dataset.index)
    spectra_frame = to_pandas_frame(dataset.spectra)

    assert dataset_meta(dataset).dataset_name == "joined"
    assert index["spectrum_id"].tolist() == ["s1", "s2"]
    assert index["condition"].tolist() == ["drug", "control"]
    assert len(spectra_frame) == 6


def test_spectral_dataset_splits_back_to_spectra_with_index_metadata() -> None:
    dataset = make_dataset(ids=("s1", "s2"), materials=("cell", "media"))

    result = SpectralDatasetToSpectrum().run({"dataset": _dataset_collection(dataset)}, BlockConfig())
    spectra = result["spectra"]

    assert spectra.item_type is Spectrum
    assert [spectrum.user["spectrum_id"] for spectrum in spectra] == ["s1", "s2"]
    assert spectra[0].user["material"] == "cell"
    assert spectrum_meta(spectra[0]).lambda_unit == "cm^-1"
    assert spectrum_frame(spectra[0])["lambda"].tolist() == [100.0, 101.0]


def test_filter_dataset_keeps_matching_index_and_spectra_rows() -> None:
    dataset = make_dataset(ids=("s1", "s2"), materials=("cell", "media"))

    result = FilterSpectralDataset().run(
        {"dataset": _dataset_collection(dataset)},
        BlockConfig(params={"filters": {"material": "cell"}}),
    )
    filtered = result["dataset"][0]

    assert to_pandas_frame(filtered.index)["spectrum_id"].tolist() == ["s1"]
    assert to_pandas_frame(filtered.spectra)["spectrum_id"].unique().tolist() == ["s1"]
    assert filtered.user["filtered"] is True


def test_merge_dataset_rejects_duplicate_ids_by_default_and_can_prefix() -> None:
    left = make_dataset(ids=("s1", "s2"), materials=("cell", "media"))
    right = make_dataset(ids=("s1", "s3"), materials=("cell2", "buffer"))
    inputs = {"datasets": Collection(items=[left, right], item_type=SpectralDataset)}

    with pytest.raises(ValueError, match="duplicate spectrum_id"):
        MergeSpectralDataset().run(inputs, BlockConfig())

    result = MergeSpectralDataset().run(inputs, BlockConfig(params={"duplicate_id_policy": "prefix"}))
    merged_ids = to_pandas_frame(result["dataset"][0].index)["spectrum_id"].tolist()
    assert merged_ids == ["s1", "s2", "ds2_s1", "ds2_s3"]


def test_attach_features_joins_index_without_changing_spectra() -> None:
    dataset = make_dataset(ids=("s1", "s2"), materials=("cell", "media"))
    features = dataframe_collection(pd.DataFrame({"spectrum_id": ["s1", "s2"], "peak_area": [10.0, 12.5]}))
    original_spectra = to_pandas_frame(dataset.spectra)

    result = AttachFeaturesToSpectralDataset().run(
        {"dataset": _dataset_collection(dataset), "features": features},
        BlockConfig(),
    )
    attached = result["dataset"][0]

    assert to_pandas_frame(attached.index)["peak_area"].tolist() == [10.0, 12.5]
    pdt.assert_frame_equal(to_pandas_frame(attached.spectra), original_spectra)


def test_attach_features_requires_join_key_in_both_tables() -> None:
    dataset = make_dataset()
    features = dataframe_collection(pd.DataFrame({"sample_id": ["s1"], "peak_area": [10.0]}))

    with pytest.raises(ValueError, match="join key"):
        AttachFeaturesToSpectralDataset().run(
            {"dataset": _dataset_collection(dataset), "features": features},
            BlockConfig(),
        )
