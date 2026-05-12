"""Napari AppBlock wrapper for imaging workflows."""

from __future__ import annotations

from typing import Any, ClassVar

from scieasy.blocks.app.app_block import AppBlock
from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.base.state import ExecutionMode
from scieasy.core.types.collection import Collection
from scieasy_blocks_imaging.interactive import (
    _input_images,
    _prepare_image_exchange,
    _resolve_command,
    _resolve_exchange_dir,
    _run_external_app,
)
from scieasy_blocks_imaging.types import Image, Label, Mask


class NapariBlock(AppBlock):
    """Open :class:`Image` inputs in napari for interactive review / annotation."""

    type_name: ClassVar[str] = "imaging.napari"
    name: ClassVar[str] = "Napari"
    description: ClassVar[str] = (
        "Open Image inputs in napari for interactive review. Collects exported layers from the exchange directory."
    )
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "interactive"

    app_command: ClassVar[str] = "napari"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.EXTERNAL
    output_patterns: ClassVar[list[str]] = ["*.tif", "*.tiff", "*.npy", "*.zarr"]
    watch_timeout: ClassVar[int] = 1800

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], description="Image(s) to open in napari."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image], required=False, description="Edited image."),
        OutputPort(name="mask", accepted_types=[Mask], required=False, description="Exported mask."),
        OutputPort(name="label", accepted_types=[Label], required=False, description="Exported labels."),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        images = _input_images(inputs, "image", "NapariBlock")
        exchange_dir = _resolve_exchange_dir(config, prefix="scieasy_napari_")
        staged_paths = _prepare_image_exchange(images, exchange_dir, tool_name=self.type_name, config=config)
        command = _resolve_command(config, app_command=self.app_command, override_key="napari_path")
        # Issue #680: broaden watcher patterns with each declared extension.
        patterns = list(self.output_patterns)
        configured_ports = config.get("output_ports") or []
        if isinstance(configured_ports, list):
            for entry in configured_ports:
                if isinstance(entry, dict) and entry.get("extension"):
                    ext = str(entry["extension"]).strip().lstrip(".").lower()
                    if ext and f"*.{ext}" not in patterns:
                        patterns.append(f"*.{ext}")
        output_files = _run_external_app(
            self,
            command=command,
            exchange_dir=exchange_dir,
            patterns=patterns,
            config=config,
            launch_args=[str(p) for p in staged_paths],
        )
        # Issue #680: extension-based binning (see FijiBlock for rationale).
        if config.get("output_ports"):
            return self._bin_outputs_by_extension(output_files, config)
        from scieasy.blocks.app.bridge import _guess_mime
        from scieasy.core.types.artifact import Artifact

        artifacts = [Artifact(file_path=p, mime_type=_guess_mime(p), description=p.name) for p in output_files]
        if not artifacts:
            return {}
        return {"image": Collection(artifacts, item_type=Artifact)}
