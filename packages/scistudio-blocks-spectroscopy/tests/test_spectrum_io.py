from __future__ import annotations

import json
from pathlib import Path

from helpers import make_spectrum, spectrum_frame, spectrum_meta
from scistudio_blocks_spectroscopy.blocks.utilities import LoadSpectrum, SaveSpectrum
from scistudio_blocks_spectroscopy.types import Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection


def test_load_csv_spectrum_adds_stable_identity_and_source_file(tmp_path: Path) -> None:
    source = tmp_path / "example.csv"
    source.write_text(
        "# lambda_unit: cm^-1\n# intensity_unit: counts\nlambda,intensity\n100,10\n101,11\n",
        encoding="utf-8",
    )

    spectra = LoadSpectrum().load(BlockConfig(params={"path": str(source)}))

    assert isinstance(spectra, Collection)
    assert spectra.item_type is Spectrum
    assert len(spectra) == 1
    spectrum = spectra[0]
    assert spectrum_meta(spectrum).lambda_unit == "cm^-1"
    assert spectrum.user["source_file"] == "example.csv"
    assert spectrum.user["filename"] == "example.csv"
    assert spectrum.user["spectrum_id"].startswith("spectrum-")
    assert list(spectrum_frame(spectrum).columns) == ["lambda", "intensity"]


def test_spectrum_json_roundtrip_preserves_data_meta_and_user(tmp_path: Path) -> None:
    spectrum = make_spectrum("sample-a", material="cell")
    target = tmp_path / "sample.spectrum.json"

    SaveSpectrum().save(spectrum, BlockConfig(params={"path": str(target)}))
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["type"] == "Spectrum"
    assert payload["user"]["spectrum_id"] == "sample-a"

    loaded = LoadSpectrum().load(BlockConfig(params={"path": str(target)}))[0]
    assert spectrum_meta(loaded).lambda_unit == spectrum_meta(spectrum).lambda_unit
    assert loaded.user["spectrum_id"] == "sample-a"
    assert loaded.user["material"] == "cell"
    assert spectrum_frame(loaded).equals(spectrum_frame(spectrum))


def test_save_collection_uses_directory_with_safe_spectrum_ids(tmp_path: Path) -> None:
    spectra = Collection(
        items=[make_spectrum("sample/1"), make_spectrum("sample 2")],
        item_type=Spectrum,
    )
    target_dir = tmp_path / "spectra"

    SaveSpectrum().save(spectra, BlockConfig(params={"path": str(target_dir), "format": "csv"}))

    assert sorted(path.name for path in target_dir.iterdir()) == ["sample_1.csv", "sample_2.csv"]


def test_vendor_native_spectrum_capability_accepts_pseudo_text_fixture(tmp_path: Path) -> None:
    source = tmp_path / "vendor.spa"
    source.write_text(
        "# modality: ftir\n# lambda_unit: cm^-1\nlambda intensity\n900 1.5\n901 1.7\n",
        encoding="utf-8",
    )

    spectra = LoadSpectrum().load(
        BlockConfig(
            params={
                "path": str(source),
                "capability_id": "scistudio-blocks-spectroscopy.spectrum.thermo_omnic_spa.load",
            }
        )
    )

    assert len(spectra) == 1
    assert spectrum_meta(spectra[0]).modality == "ftir"
    assert spectra[0].user["source_file"] == "vendor.spa"
    assert spectrum_frame(spectra[0])["lambda"].tolist() == [900, 901]
