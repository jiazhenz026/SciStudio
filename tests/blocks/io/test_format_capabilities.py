from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import BaseModel

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.io.capabilities import (
    FormatCapability,
    InvalidExtensionError,
    InvalidFormatCapabilityError,
    InvalidMetadataFidelityError,
    MetadataFidelity,
    normalize_extension,
    normalize_extensions,
)
from scistudio.blocks.io.io_block import IOBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


class _ImageMeta(BaseModel):
    pixel_size: float | None = None
    channels: tuple[str, ...] = ()


class _ImageObject(DataObject):
    Meta: ClassVar[type[BaseModel] | None] = _ImageMeta


def test_normalize_extension_adds_dot_and_lowercases() -> None:
    assert normalize_extension("TIF") == ".tif"
    assert normalize_extension(" .OME.TIF ") == ".ome.tif"
    assert normalize_extensions(["TIF", ".tif", ".PNG"]) == (".tif", ".png")


def test_normalize_extension_rejects_invalid_values() -> None:
    with pytest.raises(InvalidExtensionError, match="empty"):
        normalize_extension("")
    with pytest.raises(InvalidExtensionError, match="path separators"):
        normalize_extension("dir/file.tif")
    with pytest.raises(InvalidExtensionError, match="scalar string"):
        normalize_extensions("tif")  # type: ignore[arg-type]


def test_format_capability_normalizes_explicit_declaration() -> None:
    capability = FormatCapability(
        id="pkg.image.tiff.load",
        direction="load",
        data_type=_ImageObject,
        format_id="TIFF",
        extensions=("TIF", ".TIFF"),
        label=" TIFF ",
        block_type="LoadImage",
        handler="_load_tiff",
        is_default=True,
        roundtrip_group=" imaging.image.tiff ",
        metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=("pixel_size", "channels")),
    )

    assert capability.format_id == "tiff"
    assert capability.extensions == (".tif", ".tiff")
    assert capability.label == "TIFF"
    assert capability.roundtrip_group == "imaging.image.tiff"
    assert capability.metadata_fidelity.typed_meta_fields == ("pixel_size", "channels")
    assert capability.is_synthesized is False


def test_metadata_fidelity_rejects_invalid_level() -> None:
    with pytest.raises(InvalidMetadataFidelityError, match="Unknown metadata fidelity"):
        MetadataFidelity(level="mostly_lossless")  # type: ignore[arg-type]


def test_typed_meta_fidelity_requires_declared_fields() -> None:
    with pytest.raises(InvalidMetadataFidelityError, match="must declare typed_meta"):
        MetadataFidelity(level="typed_meta")


def test_metadata_field_lists_reject_scalar_strings() -> None:
    with pytest.raises(InvalidMetadataFidelityError, match="scalar string"):
        MetadataFidelity(level="typed_meta", typed_meta_reads="pixel_size")  # type: ignore[arg-type]


def test_format_specific_fidelity_requires_format_metadata_declaration() -> None:
    with pytest.raises(InvalidMetadataFidelityError, match="must declare format_metadata"):
        MetadataFidelity(level="format_specific", typed_meta_reads=("pixel_size",))


def test_capability_rejects_missing_typed_meta_field() -> None:
    with pytest.raises(InvalidMetadataFidelityError, match="missing_field"):
        FormatCapability(
            id="pkg.image.tiff.load",
            direction="load",
            data_type=_ImageObject,
            format_id="tiff",
            extensions=(".tif",),
            label="TIFF",
            block_type="LoadImage",
            handler="_load_tiff",
            metadata_fidelity=MetadataFidelity(level="typed_meta", typed_meta_reads=("missing_field",)),
        )


def test_lossless_capability_requires_roundtrip_group() -> None:
    with pytest.raises(InvalidFormatCapabilityError, match="roundtrip_group"):
        FormatCapability(
            id="pkg.image.tiff.load",
            direction="load",
            data_type=_ImageObject,
            format_id="tiff",
            extensions=(".tif",),
            label="TIFF",
            block_type="LoadImage",
            handler="_load_tiff",
            metadata_fidelity=MetadataFidelity(
                level="lossless",
                typed_meta_reads=("pixel_size",),
                format_metadata_reads=("ome_xml",),
            ),
        )


def test_ioblock_returns_explicit_format_capabilities() -> None:
    explicit = FormatCapability(
        id="pkg.image.png.load",
        direction="load",
        data_type=_ImageObject,
        format_id="png",
        extensions=("PNG",),
        label="PNG",
        block_type="ExplicitLoader",
        handler="_load_png",
    )

    class ExplicitLoader(IOBlock):
        format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (explicit,)

        def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
            return _ImageObject()

        def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
            return None

    assert ExplicitLoader.get_format_capabilities() == (explicit,)
    assert ExplicitLoader.get_format_capabilities()[0].extensions == (".png",)


def test_legacy_supported_extensions_synthesizes_migration_capabilities() -> None:
    class LegacyLoader(IOBlock):
        direction: ClassVar[str] = "input"
        supported_extensions: ClassVar[dict[str, str]] = {
            "TIF": "TIFF",
            ".TIFF": "TIFF",
            ".png": "PNG",
        }

        def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
            return _ImageObject()

        def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
            return None

    capabilities = LegacyLoader.get_format_capabilities()

    assert [(cap.format_id, cap.extensions) for cap in capabilities] == [
        ("png", (".png",)),
        ("tiff", (".tif", ".tiff")),
    ]
    assert all(cap.direction == "load" for cap in capabilities)
    assert all(cap.data_type is DataObject for cap in capabilities)
    assert all(cap.handler == "load" for cap in capabilities)
    assert all(cap.is_synthesized and cap.migration_scaffold for cap in capabilities)
    assert all(cap.metadata_fidelity.level == "pixel_only" for cap in capabilities)
