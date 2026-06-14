from __future__ import annotations

from typing import ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.package_info import PackageInfo
from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scistudio.blocks.io.io_block import IOBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


class FirstDuplicateCapabilityLoader(IOBlock):
    name: ClassVar[str] = "PV First Duplicate Capability Loader"
    direction: ClassVar[str] = "input"
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id="pv-conflicting-capability-id-package.duplicate.load",
            direction="load",
            data_type=DataObject,
            format_id="json",
            extensions=(".json",),
            label="PV Duplicate Loader One",
            block_type="FirstDuplicateCapabilityLoader",
            handler="load",
            metadata_fidelity=MetadataFidelity(level="pixel_only"),
        ),
    )

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject:
        return DataObject()

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError("input-direction fixture")


class SecondDuplicateCapabilityLoader(IOBlock):
    name: ClassVar[str] = "PV Second Duplicate Capability Loader"
    direction: ClassVar[str] = "input"
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id="pv-conflicting-capability-id-package.duplicate.load",
            direction="load",
            data_type=DataObject,
            format_id="json",
            extensions=(".json",),
            label="PV Duplicate Loader Two",
            block_type="SecondDuplicateCapabilityLoader",
            handler="load",
            metadata_fidelity=MetadataFidelity(level="pixel_only"),
        ),
    )

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject:
        return DataObject()

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError("input-direction fixture")


def get_block_package() -> tuple[PackageInfo, list[type]]:
    return (
        PackageInfo(name="pv-conflicting-capability-id-package", version="0.1.0"),
        [FirstDuplicateCapabilityLoader, SecondDuplicateCapabilityLoader],
    )
