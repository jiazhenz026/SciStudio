from __future__ import annotations

from typing import ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.package_info import PackageInfo
from scistudio.blocks.io.io_block import IOBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


class InvalidCapabilityLoader(IOBlock):
    name: ClassVar[str] = "PV Invalid Capability Loader"
    direction: ClassVar[str] = "input"
    format_capabilities: ClassVar[tuple[object, ...]] = (  # type: ignore[assignment]
        {
            "id": "",
            "direction": "sideways",
            "data_type": "not-a-dataobject",
            "format_id": "",
            "extensions": (),
            "block_type": "WrongBlock",
            "handler": "missing",
        },
    )

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject:
        return DataObject()

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError("input-direction fixture")


def get_block_package() -> tuple[PackageInfo, list[type]]:
    return (
        PackageInfo(name="pv-invalid-io-capability-package", version="0.1.0"),
        [InvalidCapabilityLoader],
    )
