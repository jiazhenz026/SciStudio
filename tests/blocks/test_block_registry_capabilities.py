from __future__ import annotations

from typing import Any, ClassVar

import pytest

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scieasy.blocks.io.io_block import IOBlock
from scieasy.blocks.io.simple_io import SimpleLoader
from scieasy.blocks.registry import (
    AmbiguousCapabilityError,
    BlockRegistry,
    CapabilityRegistrationError,
    MissingCapabilityError,
    _spec_from_class,
)
from scieasy.core.types.array import Array
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection


class _Image(Array):
    pass


class _FluorImage(_Image):
    pass


def _capability(
    *,
    capability_id: str,
    direction: str,
    data_type: type[DataObject],
    block_type: str,
    handler: str,
    extensions: tuple[str, ...] = ("TIF", ".TIFF"),
    format_id: str = "TIFF",
    is_default: bool = False,
    priority: int = 0,
) -> FormatCapability:
    return FormatCapability(
        id=capability_id,
        direction=direction,  # type: ignore[arg-type]
        data_type=data_type,
        format_id=format_id,
        extensions=extensions,
        label=format_id,
        block_type=block_type,
        handler=handler,
        is_default=is_default,
        priority=priority,
    )


class _ImageTiffLoader(IOBlock):
    name: ClassVar[str] = "_ImageTiffLoader"
    type_name: ClassVar[str] = "test.image_tiff_loader"
    direction: ClassVar[str] = "input"
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="data", accepted_types=[_Image])]
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        _capability(
            capability_id="tests.image.tiff.load",
            direction="load",
            data_type=_Image,
            block_type="_ImageTiffLoader",
            handler="_load_tiff",
        ),
    )

    def _load_tiff(self, path: object, config: object) -> _Image:
        return _Image()

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raise NotImplementedError

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError


class _ImagePngLoader(_ImageTiffLoader):
    name: ClassVar[str] = "_ImagePngLoader"
    type_name: ClassVar[str] = "test.image_png_loader"
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        _capability(
            capability_id="tests.image.png.load",
            direction="load",
            data_type=_Image,
            block_type="_ImagePngLoader",
            handler="_load_png",
            extensions=(".png",),
            format_id="png",
        ),
    )

    def _load_png(self, path: object, config: object) -> _Image:
        return _Image()


class _DefaultImageTiffLoader(_ImageTiffLoader):
    name: ClassVar[str] = "_DefaultImageTiffLoader"
    type_name: ClassVar[str] = "test.default_image_tiff_loader"
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        _capability(
            capability_id="tests.image.tiff.default.load",
            direction="load",
            data_type=_Image,
            block_type="_DefaultImageTiffLoader",
            handler="_load_tiff",
            is_default=True,
        ),
    )


class _SecondImageTiffLoader(_ImageTiffLoader):
    name: ClassVar[str] = "_SecondImageTiffLoader"
    type_name: ClassVar[str] = "test.second_image_tiff_loader"
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        _capability(
            capability_id="tests.image.tiff.alt.load",
            direction="load",
            data_type=_Image,
            block_type="_SecondImageTiffLoader",
            handler="_load_tiff",
        ),
    )


class _FluorImageTiffLoader(_ImageTiffLoader):
    name: ClassVar[str] = "_FluorImageTiffLoader"
    type_name: ClassVar[str] = "test.fluor_image_tiff_loader"
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="data", accepted_types=[_FluorImage])]
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        _capability(
            capability_id="tests.fluor_image.tiff.load",
            direction="load",
            data_type=_FluorImage,
            block_type="_FluorImageTiffLoader",
            handler="_load_tiff",
        ),
    )


class _ImageTiffSaver(IOBlock):
    name: ClassVar[str] = "_ImageTiffSaver"
    type_name: ClassVar[str] = "test.image_tiff_saver"
    direction: ClassVar[str] = "output"
    input_ports: ClassVar[list[InputPort]] = [InputPort(name="data", accepted_types=[_Image])]
    output_ports: ClassVar[list[Any]] = []
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        _capability(
            capability_id="tests.image.tiff.save",
            direction="save",
            data_type=_Image,
            block_type="_ImageTiffSaver",
            handler="_save_tiff",
        ),
    )

    def _save_tiff(self, obj: object, path: object, config: object) -> None:
        return None

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raise NotImplementedError

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError


def _build_registry(*classes: type) -> BlockRegistry:
    registry = BlockRegistry()
    for cls in classes:
        registry._register_spec(_spec_from_class(cls, source="test"))
    return registry


def test_block_spec_retains_normalized_format_capabilities() -> None:
    spec = _spec_from_class(_ImageTiffLoader, source="test")

    assert [capability.id for capability in spec.format_capabilities] == ["tests.image.tiff.load"]
    assert spec.format_capabilities[0].extensions == (".tif", ".tiff")


def test_list_format_capabilities_filters_by_direction_type_extension_and_format() -> None:
    registry = _build_registry(_ImageTiffLoader, _ImagePngLoader, _ImageTiffSaver)

    load_tiff = registry.list_format_capabilities(
        direction="load",
        data_type=_Image,
        extension=".TIF",
        format_id="TIFF",
    )

    assert [capability.id for capability in load_tiff] == ["tests.image.tiff.load"]


def test_find_loader_capability_returns_unique_match() -> None:
    registry = _build_registry(_ImageTiffLoader)

    capability = registry.find_loader_capability(_Image, "TIF")

    assert capability.id == "tests.image.tiff.load"


def test_find_saver_capability_accepts_subtype_for_parent_saver() -> None:
    registry = _build_registry(_ImageTiffSaver)

    capability = registry.find_saver_capability(_FluorImage, ".tiff")

    assert capability.id == "tests.image.tiff.save"


def test_explicit_capability_id_resolves_ambiguous_matches() -> None:
    registry = _build_registry(_ImageTiffLoader, _SecondImageTiffLoader)

    capability = registry.find_loader_capability(
        _Image,
        ".tif",
        capability_id="tests.image.tiff.alt.load",
    )

    assert capability.id == "tests.image.tiff.alt.load"


def test_missing_capability_raises_typed_error() -> None:
    registry = _build_registry(_ImageTiffLoader)

    with pytest.raises(MissingCapabilityError, match="No IO format capability"):
        registry.find_loader_capability(_Image, ".csv")


def test_ambiguous_capability_raises_typed_error_without_registration_order_dispatch() -> None:
    registry = _build_registry(_ImageTiffLoader, _SecondImageTiffLoader)

    with pytest.raises(AmbiguousCapabilityError) as exc_info:
        registry.find_loader_capability(_Image, ".tif")

    assert [capability.id for capability in exc_info.value.candidates] == [
        "tests.image.tiff.load",
        "tests.image.tiff.alt.load",
    ]


def test_explicit_default_wins_over_otherwise_ambiguous_matches() -> None:
    registry = _build_registry(_ImageTiffLoader, _DefaultImageTiffLoader)

    capability = registry.find_loader_capability(_Image, ".tif")

    assert capability.id == "tests.image.tiff.default.load"


def test_most_specific_type_wins_without_default() -> None:
    registry = _build_registry(_ImageTiffLoader, _FluorImageTiffLoader)

    capability = registry.find_loader_capability(_Image, ".tif")

    assert capability.id == "tests.fluor_image.tiff.load"


def test_priority_breaks_same_type_ties_after_specificity() -> None:
    class _PriorityLoader(_ImageTiffLoader):
        name: ClassVar[str] = "_PriorityLoader"
        type_name: ClassVar[str] = "test.priority_loader"
        format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
            _capability(
                capability_id="tests.image.tiff.priority.load",
                direction="load",
                data_type=_Image,
                block_type="_PriorityLoader",
                handler="_load_tiff",
                priority=10,
            ),
        )

    registry = _build_registry(_ImageTiffLoader, _PriorityLoader)

    capability = registry.find_loader_capability(_Image, ".tif")

    assert capability.id == "tests.image.tiff.priority.load"


def test_legacy_find_loader_keeps_first_registered_migration_fallback() -> None:
    registry = _build_registry(_ImageTiffLoader, _SecondImageTiffLoader)

    assert registry.find_loader(_Image, ".tif") is _ImageTiffLoader


def test_legacy_find_loader_without_dtype_keeps_registration_order() -> None:
    registry = _build_registry(_ImageTiffLoader, _DefaultImageTiffLoader)

    assert registry.find_loader(None, ".tif") is _ImageTiffLoader


def test_legacy_find_loader_falls_back_when_winning_capability_class_cannot_resolve(monkeypatch: Any) -> None:
    registry = _build_registry(_DefaultImageTiffLoader, _SecondImageTiffLoader)
    original_resolve_class = registry._resolve_class

    def _fake_resolve_class(spec: object) -> type | None:
        if getattr(spec, "class_name", "") == "_DefaultImageTiffLoader":
            return None
        return original_resolve_class(spec)  # type: ignore[arg-type]

    monkeypatch.setattr(registry, "_resolve_class", _fake_resolve_class)

    assert registry.find_loader(_Image, ".tif") is _SecondImageTiffLoader


def test_scan_time_validation_rejects_missing_handler() -> None:
    class _MissingHandlerLoader(_ImageTiffLoader):
        name: ClassVar[str] = "_MissingHandlerLoader"
        type_name: ClassVar[str] = "test.missing_handler_loader"
        format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
            _capability(
                capability_id="tests.image.tiff.missing.load",
                direction="load",
                data_type=_Image,
                block_type="_MissingHandlerLoader",
                handler="_missing_handler",
            ),
        )

    with pytest.raises(CapabilityRegistrationError, match="missing handler"):
        _spec_from_class(_MissingHandlerLoader, source="test")


def test_scan_time_validation_rejects_unqualified_capability_id() -> None:
    class _BadIdLoader(_ImageTiffLoader):
        name: ClassVar[str] = "_BadIdLoader"
        type_name: ClassVar[str] = "test.bad_id_loader"
        format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
            _capability(
                capability_id="tiff",
                direction="load",
                data_type=_Image,
                block_type="_BadIdLoader",
                handler="_load_tiff",
            ),
        )

    registry = BlockRegistry()
    with pytest.raises(CapabilityRegistrationError, match="package-qualified"):
        registry._register_spec(_spec_from_class(_BadIdLoader, source="test"))


def test_scan_time_validation_rejects_default_conflict() -> None:
    class _AnotherDefaultLoader(_ImageTiffLoader):
        name: ClassVar[str] = "_AnotherDefaultLoader"
        type_name: ClassVar[str] = "test.another_default_loader"
        format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
            _capability(
                capability_id="tests.image.tiff.another_default.load",
                direction="load",
                data_type=_Image,
                block_type="_AnotherDefaultLoader",
                handler="_load_tiff",
                is_default=True,
            ),
        )

    registry = _build_registry(_DefaultImageTiffLoader)
    with pytest.raises(CapabilityRegistrationError, match="Conflicting default"):
        registry._register_spec(_spec_from_class(_AnotherDefaultLoader, source="test"))


def test_scan_time_validation_rejects_scalar_simple_loader_extensions() -> None:
    class _ScalarExtensionLoader(SimpleLoader):
        output_type: ClassVar[type[DataObject]] = _Image
        extensions: ClassVar[str] = "tif"
        format_id: ClassVar[str] = "tiff"
        metadata_fidelity: ClassVar[MetadataFidelity] = MetadataFidelity(level="pixel_only")

        def load_file(self, path: object, config: dict[str, object]) -> DataObject:
            return _Image()

    with pytest.raises(CapabilityRegistrationError, match="scalar string"):
        _spec_from_class(_ScalarExtensionLoader, source="test")
