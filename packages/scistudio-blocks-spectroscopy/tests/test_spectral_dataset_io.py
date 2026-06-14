from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pandas.testing as pdt
from helpers import dataset_meta, make_dataset
from scistudio_blocks_spectroscopy._tables import to_pandas_frame
from scistudio_blocks_spectroscopy.blocks.utilities import LoadSpectralDataset, SaveSpectralDataset

from scistudio.blocks.base.config import BlockConfig


def test_manifest_json_roundtrip_writes_two_slot_sidecars(tmp_path: Path) -> None:
    dataset = make_dataset(dataset_name="roundtrip")
    target = tmp_path / "roundtrip.spectraldataset.json"

    SaveSpectralDataset().save(dataset, BlockConfig(params={"path": str(target)}))

    manifest = json.loads(target.read_text(encoding="utf-8"))
    assert manifest["type"] == "SpectralDataset"
    assert manifest["slots"] == {
        "index": "roundtrip.spectraldataset.index.csv",
        "spectra": "roundtrip.spectraldataset.spectra.csv",
    }
    assert (tmp_path / manifest["slots"]["index"]).is_file()
    assert (tmp_path / manifest["slots"]["spectra"]).is_file()
    assert not list(tmp_path.glob("*.zip"))

    loaded = LoadSpectralDataset().load(BlockConfig(params={"path": str(target)}))
    assert dataset_meta(loaded).dataset_name == "roundtrip"
    assert loaded.user["source_file"] == target.name
    pdt.assert_frame_equal(to_pandas_frame(loaded.index), to_pandas_frame(dataset.index))
    pdt.assert_frame_equal(to_pandas_frame(loaded.spectra), to_pandas_frame(dataset.spectra))


def test_spc_dataset_save_and_pseudo_text_load(tmp_path: Path) -> None:
    dataset = make_dataset(ids=("a", "b"), materials=("cell", "media"), dataset_name="spc")
    target = tmp_path / "dataset.spc"

    SaveSpectralDataset().save(dataset, BlockConfig(params={"path": str(target)}))
    loaded = LoadSpectralDataset().load(BlockConfig(params={"path": str(target)}))

    assert dataset_meta(loaded).dataset_name == "dataset"
    assert to_pandas_frame(loaded.index)["spectrum_id"].tolist() == ["a", "b"]
    assert set(to_pandas_frame(loaded.index)["material"]) == {"cell", "media"}
    assert len(to_pandas_frame(loaded.spectra)) == 4


def test_two_csv_tables_load_into_required_slots(tmp_path: Path) -> None:
    index = tmp_path / "index.csv"
    spectra = tmp_path / "spectra.csv"
    pd.DataFrame({"spectrum_id": ["s1"], "sample": ["A"]}).to_csv(index, index=False)
    pd.DataFrame({"spectrum_id": ["s1"], "lambda": [500.0], "intensity": [2.0]}).to_csv(spectra, index=False)

    dataset = LoadSpectralDataset().load(
        BlockConfig(
            params={
                "index_path": str(index),
                "spectra_path": str(spectra),
                "dataset_name": "from tables",
            }
        )
    )

    assert set(dataset.slots) == {"index", "spectra"}
    assert dataset_meta(dataset).dataset_name == "from tables"
    assert to_pandas_frame(dataset.index)["sample"].tolist() == ["A"]
