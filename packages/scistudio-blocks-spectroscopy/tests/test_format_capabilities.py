from __future__ import annotations

from scistudio_blocks_spectroscopy.blocks.utilities import (
    LoadSpectralDataset,
    LoadSpectrum,
    SaveSpectralDataset,
    SaveSpectrum,
)
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.blocks.io.capabilities import FormatCapability
from scistudio.blocks.io.io_block import IOBlock


def _capabilities_by_id(block: type[IOBlock]) -> dict[str, FormatCapability]:
    return {capability.id: capability for capability in block.get_format_capabilities()}


def test_spectrum_capability_matrix_matches_spec() -> None:
    load = _capabilities_by_id(LoadSpectrum)
    save = _capabilities_by_id(SaveSpectrum)

    assert set(load) == {
        "scistudio-blocks-spectroscopy.spectrum.txt.load",
        "scistudio-blocks-spectroscopy.spectrum.csv.load",
        "scistudio-blocks-spectroscopy.spectrum.tsv.load",
        "scistudio-blocks-spectroscopy.spectrum.xlsx.load",
        "scistudio-blocks-spectroscopy.spectrum.spectrum_json.load",
        "scistudio-blocks-spectroscopy.spectrum.jcamp_dx.load",
        "scistudio-blocks-spectroscopy.spectrum.spc.load",
        "scistudio-blocks-spectroscopy.spectrum.thermo_omnic_spa.load",
        "scistudio-blocks-spectroscopy.spectrum.bruker_opus.load",
        "scistudio-blocks-spectroscopy.spectrum.horiba_labspec.load",
        "scistudio-blocks-spectroscopy.spectrum.renishaw_wdf.load",
        "scistudio-blocks-spectroscopy.spectrum.andor_solis.load",
        "scistudio-blocks-spectroscopy.spectrum.princeton_spe.load",
    }
    assert set(save) == {
        "scistudio-blocks-spectroscopy.spectrum.txt.save",
        "scistudio-blocks-spectroscopy.spectrum.csv.save",
        "scistudio-blocks-spectroscopy.spectrum.tsv.save",
        "scistudio-blocks-spectroscopy.spectrum.xlsx.save",
        "scistudio-blocks-spectroscopy.spectrum.spectrum_json.save",
        "scistudio-blocks-spectroscopy.spectrum.jcamp_dx.save",
        "scistudio-blocks-spectroscopy.spectrum.spc.save",
    }
    assert all(capability.data_type is Spectrum for capability in (*load.values(), *save.values()))
    assert not any("srs" in capability.id for capability in (*load.values(), *save.values()))


def test_spectral_dataset_capability_matrix_matches_spec() -> None:
    load = _capabilities_by_id(LoadSpectralDataset)
    save = _capabilities_by_id(SaveSpectralDataset)

    assert set(load) == {
        "scistudio-blocks-spectroscopy.spectral_dataset.manifest_json.load",
        "scistudio-blocks-spectroscopy.spectral_dataset.xlsx.load",
        "scistudio-blocks-spectroscopy.spectral_dataset.spc.load",
        "scistudio-blocks-spectroscopy.spectral_dataset.thermo_omnic_spg.load",
        "scistudio-blocks-spectroscopy.spectral_dataset.renishaw_wdf.load",
        "scistudio-blocks-spectroscopy.spectral_dataset.bruker_opus.load",
        "scistudio-blocks-spectroscopy.spectral_dataset.horiba_labspec.load",
        "scistudio-blocks-spectroscopy.spectral_dataset.witec_project.load",
        "scistudio-blocks-spectroscopy.spectral_dataset.andor_solis.load",
        "scistudio-blocks-spectroscopy.spectral_dataset.princeton_spe.load",
    }
    assert set(save) == {
        "scistudio-blocks-spectroscopy.spectral_dataset.manifest_json.save",
        "scistudio-blocks-spectroscopy.spectral_dataset.xlsx.save",
        "scistudio-blocks-spectroscopy.spectral_dataset.spc.save",
    }
    assert load["scistudio-blocks-spectroscopy.spectral_dataset.manifest_json.load"].format_id == (
        "spectral_dataset_manifest_json"
    )
    assert save["scistudio-blocks-spectroscopy.spectral_dataset.manifest_json.save"].format_id == (
        "spectral_dataset_manifest_json"
    )
    assert all(capability.data_type is SpectralDataset for capability in (*load.values(), *save.values()))


def test_capabilities_are_explicit_and_handlers_exist() -> None:
    for block in (LoadSpectrum, SaveSpectrum, LoadSpectralDataset, SaveSpectralDataset):
        for capability in block.get_format_capabilities():
            assert not capability.is_synthesized
            assert getattr(block(), capability.handler)
            assert capability.block_type == block.__name__
            assert ".zip" not in capability.extensions


def test_vendor_formats_are_load_only_and_not_lossless() -> None:
    load_capabilities = {
        capability.id: capability
        for block in (LoadSpectrum, LoadSpectralDataset)
        for capability in block.get_format_capabilities()
    }
    save_ids = {
        capability.id for block in (SaveSpectrum, SaveSpectralDataset) for capability in block.get_format_capabilities()
    }

    vendor_load_ids = {
        capability_id
        for capability_id in load_capabilities
        if any(
            vendor in capability_id
            for vendor in (
                "thermo_omnic",
                "bruker_opus",
                "horiba_labspec",
                "renishaw_wdf",
                "andor_solis",
                "princeton_spe",
                "witec_project",
            )
        )
    }
    assert vendor_load_ids
    assert not any(any(vendor_id.rsplit(".", 1)[0] in save_id for save_id in save_ids) for vendor_id in vendor_load_ids)
    for capability_id in vendor_load_ids:
        capability = load_capabilities[capability_id]
        assert capability.roundtrip_group is None
        assert capability.metadata_fidelity.level != "lossless"


def test_roundtrip_capabilities_are_paired_by_group() -> None:
    load_by_group = {
        capability.roundtrip_group: capability
        for block in (LoadSpectrum, LoadSpectralDataset)
        for capability in block.get_format_capabilities()
        if capability.roundtrip_group is not None
    }
    save_by_group = {
        capability.roundtrip_group: capability
        for block in (SaveSpectrum, SaveSpectralDataset)
        for capability in block.get_format_capabilities()
        if capability.roundtrip_group is not None
    }

    assert set(save_by_group) <= set(load_by_group)
    assert load_by_group["scistudio-blocks-spectroscopy.spectrum.spectrum_json"].metadata_fidelity.level == "lossless"
    assert (
        save_by_group["scistudio-blocks-spectroscopy.spectral_dataset.manifest_json"].metadata_fidelity.level
        == "lossless"
    )
