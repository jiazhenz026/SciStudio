"""ADR-043 format-capability contract tests for the four IO blocks (skeleton-safe)."""

from __future__ import annotations

from scistudio_blocks_spectroscopy.blocks.utilities import (
    LoadSpectralDataset,
    LoadSpectrum,
    SaveSpectralDataset,
    SaveSpectrum,
)

from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity

_IO_BLOCKS = [LoadSpectrum, SaveSpectrum, LoadSpectralDataset, SaveSpectralDataset]


def test_capabilities_are_explicit_not_synthesized() -> None:
    for block in _IO_BLOCKS:
        caps = block.get_format_capabilities()
        assert caps, f"{block.__name__} declares no capabilities"
        for cap in caps:
            assert isinstance(cap, FormatCapability)
            assert isinstance(cap.metadata_fidelity, MetadataFidelity)
            assert not cap.is_synthesized, cap.id


def test_capability_ids_are_package_qualified_and_directional() -> None:
    for block in _IO_BLOCKS:
        direction = "load" if block.direction == "input" else "save"
        for cap in block.get_format_capabilities():
            assert cap.id.startswith("scistudio-blocks-spectroscopy.")
            assert cap.id.endswith(f".{direction}")
            assert cap.direction == direction
            assert cap.block_type == block.__name__


def test_handlers_resolve_on_class() -> None:
    for block in _IO_BLOCKS:
        for cap in block.get_format_capabilities():
            assert hasattr(block, cap.handler), f"{block.__name__} missing {cap.handler}"
            assert callable(getattr(block, cap.handler))


def test_vendor_load_only_formats_have_no_saver() -> None:
    load_only_format_ids = {
        "thermo_omnic_spa",
        "bruker_opus",
        "horiba_labspec",
        "renishaw_wdf",
        "andor_solis",
        "princeton_spe",
        "thermo_omnic_spg",
        "witec_project",
    }
    saver_format_ids = {
        cap.format_id for block in (SaveSpectrum, SaveSpectralDataset) for cap in block.get_format_capabilities()
    }
    assert load_only_format_ids.isdisjoint(saver_format_ids)


def test_lossless_capabilities_declare_roundtrip_group() -> None:
    for block in _IO_BLOCKS:
        for cap in block.get_format_capabilities():
            if cap.metadata_fidelity.level == "lossless":
                assert cap.roundtrip_group is not None, cap.id
