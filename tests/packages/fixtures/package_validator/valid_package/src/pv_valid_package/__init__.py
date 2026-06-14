from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.package_info import PackageInfo
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scistudio.blocks.io.io_block import IOBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.previewers.models import FrontendManifest, OwnerKind, PreviewerSpec


class ValidSample(DataObject):
    class Meta(BaseModel):
        model_config = ConfigDict(frozen=True)

        label: str = "control"


class ValidTransformBlock(Block):
    name: ClassVar[str] = "PV Valid Transform"
    input_ports: ClassVar[list[InputPort]] = [InputPort(name="sample", accepted_types=[ValidSample])]
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="sample", accepted_types=[ValidSample])]

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        return {"sample": inputs["sample"]}


class ValidSampleLoader(IOBlock):
    name: ClassVar[str] = "PV Valid Sample Loader"
    direction: ClassVar[str] = "input"
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="sample", accepted_types=[ValidSample])]
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id="pv-valid-package.sample.load.json",
            direction="load",
            data_type=ValidSample,
            format_id="json",
            extensions=(".json",),
            label="PV Valid Sample JSON",
            block_type="ValidSampleLoader",
            handler="load",
            metadata_fidelity=MetadataFidelity(level="pixel_only"),
        ),
    )

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject:
        return ValidSample()

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError("input-direction fixture")


def get_types() -> list[type]:
    return [ValidSample]


def get_block_package() -> tuple[PackageInfo, list[type]]:
    return (
        PackageInfo(
            name="pv-valid-package",
            description="ADR-049 valid package-validator fixture.",
            author="SciStudio tests",
            version="0.1.0",
        ),
        [ValidTransformBlock, ValidSampleLoader],
    )


def get_previewers() -> list[PreviewerSpec]:
    return [
        PreviewerSpec(
            previewer_id="pv.valid.sample",
            owner_kind=OwnerKind.PACKAGE,
            owner_name="pv-valid-package",
            target_type="ValidSample",
            priority=10,
            capabilities=("summary",),
            backend_provider=None,
            frontend_manifest=FrontendManifest(
                previewer_id="pv.valid.sample",
                module_url="/api/previews/assets/pv.valid.sample/previewer.js",
                export_name="render",
                version="0.1.0",
                asset_root="assets",
            ),
        )
    ]
