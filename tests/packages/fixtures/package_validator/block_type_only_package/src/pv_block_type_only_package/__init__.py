from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.package_info import PackageInfo
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


class BlockOnlyType(DataObject):
    class Meta(BaseModel):
        model_config = ConfigDict(frozen=True)

        label: str = "block-only"


class BlockOnlyTransform(Block):
    name: ClassVar[str] = "PV Block Only Transform"
    input_ports: ClassVar[list[InputPort]] = [InputPort(name="item", accepted_types=[BlockOnlyType])]
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="item", accepted_types=[BlockOnlyType])]

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        return {"item": inputs["item"]}


def get_types() -> list[type]:
    return [BlockOnlyType]


def get_block_package() -> tuple[PackageInfo, list[type]]:
    return (
        PackageInfo(name="pv-block-type-only-package", version="0.1.0"),
        [BlockOnlyTransform],
    )
