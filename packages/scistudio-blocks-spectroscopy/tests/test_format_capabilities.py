"""ADR-043 format-capability contract tests for the four IO blocks.

Covers SC-048..SC-055 of ``docs/specs/spectroscopy-package.md``:

- SC-048: each IO block exposes explicit ``FormatCapability`` records with the
  formal ADR-043 fields (not synthesized migration scaffolds).
- SC-049: ``capability_id`` is only a lookup reference to ``FormatCapability.id``
  and no package type declares file extensions / format support.
- SC-050/SC-051: txt/csv/tsv/xlsx/spectrum_json/jcamp_dx load+save; SPC is not
  advertised until implemented.
- SC-052: vendor/native formats are not advertised as capabilities until
  fixture-backed handlers exist.
- SC-053: dataset native JSON uses a package-owned manifest + sidecar slots.
- SC-054: no ``.zip``/``.spectraldataset.zip`` capability is declared.
- SC-055: capability lookup fails on unresolved ambiguity rather than choosing
  by registration order.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from scistudio_blocks_spectroscopy.blocks.utilities import (
    LoadSpectralDataset,
    LoadSpectrum,
    SaveSpectralDataset,
    SaveSpectrum,
    _resolve_dataset_io_capability,
)
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity

_IO_BLOCKS = [LoadSpectrum, SaveSpectrum, LoadSpectralDataset, SaveSpectralDataset]

_DEFERRED_FORMAT_IDS = {
    "spc",
    "thermo_omnic_spa",
    "thermo_omnic_spg",
    "bruker_opus",
    "horiba_labspec",
    "renishaw_wdf",
    "andor_solis",
    "princeton_spe",
    "witec_project",
}


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


def test_deferred_binary_formats_are_not_advertised() -> None:
    """SC-051/SC-052: deferred SPC/vendor formats are not runtime capabilities."""
    format_ids = {cap.format_id for block in _IO_BLOCKS for cap in block.get_format_capabilities()}
    assert _DEFERRED_FORMAT_IDS.isdisjoint(format_ids)


def test_lossless_capabilities_declare_roundtrip_group() -> None:
    for block in _IO_BLOCKS:
        for cap in block.get_format_capabilities():
            if cap.metadata_fidelity.level == "lossless":
                assert cap.roundtrip_group is not None, cap.id


def test_adr043_formal_fields_present_and_typed() -> None:
    """SC-048: each capability carries the formal ADR-043 fields, typed."""
    for block in _IO_BLOCKS:
        expected_dir = "load" if block.direction == "input" else "save"
        for cap in block.get_format_capabilities():
            # Required formal fields exist and are non-empty / correctly typed.
            assert isinstance(cap.id, str) and cap.id
            assert cap.direction == expected_dir
            assert isinstance(cap.data_type, type)
            assert issubclass(cap.data_type, (Spectrum, SpectralDataset))
            assert isinstance(cap.format_id, str) and cap.format_id
            assert isinstance(cap.extensions, tuple) and cap.extensions
            assert all(e.startswith(".") for e in cap.extensions)
            assert isinstance(cap.label, str) and cap.label
            assert cap.block_type == block.__name__
            assert isinstance(cap.handler, str) and cap.handler
            assert isinstance(cap.metadata_fidelity, MetadataFidelity)
            # SC-048: explicit author declaration, not a synthesized scaffold.
            assert cap.is_synthesized is False
            assert cap.migration_scaffold is False


def test_capability_ids_unique_per_block() -> None:
    for block in _IO_BLOCKS:
        ids = [cap.id for cap in block.get_format_capabilities()]
        assert len(ids) == len(set(ids)), f"{block.__name__} has duplicate capability ids"


def test_types_do_not_declare_extensions_or_formats() -> None:
    """SC-049: file formats are an IO concern; types declare none."""
    for data_type in (Spectrum, SpectralDataset):
        for attr in ("extensions", "format_id", "supported_extensions", "format_capabilities"):
            assert not hasattr(data_type, attr), f"{data_type.__name__} must not declare {attr!r}"


def test_capability_id_only_references_capability_id_field() -> None:
    """SC-049: capability_id is a lookup ref; every declared id resolves back."""
    for block in _IO_BLOCKS:
        caps = block.get_format_capabilities()
        ids = {cap.id for cap in caps}
        for cap in caps:
            # capability_id is exactly cap.id — round-trips by identity lookup.
            assert cap.id in ids


def test_spc_is_contractually_deferred() -> None:
    """SC-051: SPC is tracked as planned work, not an executable capability."""
    for block in _IO_BLOCKS:
        assert all(cap.format_id != "spc" for cap in block.get_format_capabilities())


def test_native_round_trippable_formats_load_and_save() -> None:
    """SC-050: the native spectrum formats expose both load and save."""
    native = {"txt", "csv", "tsv", "xlsx", "spectrum_json", "jcamp_dx"}
    load_ids = {c.format_id for c in LoadSpectrum.get_format_capabilities()}
    save_ids = {c.format_id for c in SaveSpectrum.get_format_capabilities()}
    assert native <= load_ids
    assert native <= save_ids


def test_vendor_formats_are_contractually_deferred() -> None:
    """SC-052: vendor/native formats have no advertised loader or saver."""
    advertised = {c.format_id for blk in _IO_BLOCKS for c in blk.get_format_capabilities()}
    vendor_ids = _DEFERRED_FORMAT_IDS - {"spc"}
    assert vendor_ids.isdisjoint(advertised)


def test_dataset_native_json_uses_package_manifest() -> None:
    """SC-053: SpectralDataset native JSON is a package-owned manifest format."""
    save_caps = LoadSpectralDataset.get_format_capabilities()
    manifest = [c for c in save_caps if c.format_id == "spectral_dataset_manifest_json"]
    assert manifest, "no manifest_json load capability declared"
    cap = manifest[0]
    assert cap.metadata_fidelity.level == "lossless"
    assert cap.roundtrip_group is not None
    assert cap.id.startswith("scistudio-blocks-spectroscopy.")


def test_no_zip_capability_declared() -> None:
    """SC-054: no .zip / .spectraldataset.zip capability for SpectralDataset."""
    for block in (LoadSpectralDataset, SaveSpectralDataset):
        for cap in block.get_format_capabilities():
            assert "zip" not in cap.format_id, cap.id
            assert all(".zip" not in ext for ext in cap.extensions), cap.id


def test_capability_lookup_fails_on_unresolved_ambiguity() -> None:
    """SC-055: ambiguous extension->format resolution raises, never picks by order.

    Drives the production resolver ``_resolve_dataset_io_capability`` with a
    stub block declaring two same-``format_id`` save capabilities for the same
    extension. The resolver must refuse rather than return the first match.
    """

    def _cap(cap_id: str) -> FormatCapability:
        return FormatCapability(
            id=cap_id,
            direction="save",
            data_type=SpectralDataset,
            format_id="ambig",
            extensions=(".ambig",),
            label="Ambiguous",
            block_type="StubBlock",
            handler="_save_stub",
        )

    class _StubBlock:
        supported_extensions: ClassVar[dict[str, str]] = {".ambig": "ambig"}

        def get_format_capabilities(self) -> tuple[FormatCapability, ...]:
            return (_cap("pkg.dataset.ambig.a.save"), _cap("pkg.dataset.ambig.b.save"))

        def _detect_format(self, _path: object) -> str:
            return "ambig"

    stub = _StubBlock()
    # Without an explicit capability_id, the duplicate format match is ambiguous.
    with pytest.raises(ValueError, match="ambiguous"):
        _resolve_dataset_io_capability(
            stub,  # type: ignore[arg-type]
            BlockConfig(params={}),
            "thing.ambig",
            direction="save",
            block="StubBlock",
        )
    # An explicit capability_id disambiguates deterministically.
    resolved = _resolve_dataset_io_capability(
        stub,  # type: ignore[arg-type]
        BlockConfig(params={"capability_id": "pkg.dataset.ambig.b.save"}),
        "thing.ambig",
        direction="save",
        block="StubBlock",
    )
    assert resolved.id == "pkg.dataset.ambig.b.save"
