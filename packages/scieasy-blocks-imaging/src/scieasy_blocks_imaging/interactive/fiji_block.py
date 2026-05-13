"""Fiji AppBlock wrapper for imaging workflows."""

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
from scieasy_blocks_imaging.types import Image


class FijiBlock(AppBlock):
    """Open one or more :class:`Image` instances in Fiji / ImageJ."""

    type_name: ClassVar[str] = "imaging.fiji"
    name: ClassVar[str] = "Fiji"
    description: ClassVar[str] = (
        "Open Image inputs in Fiji for interactive review / annotation. "
        "Collects exported TIFFs / ROIs from the exchange directory."
    )
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "interactive"

    app_command: ClassVar[str] = r"C:\Program Files\Fiji\fiji-windows-x64.exe"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.EXTERNAL
    output_patterns: ClassVar[list[str]] = ["*.tif", "*.tiff", "*.zip", "*.roi"]
    watch_timeout: ClassVar[int] = 1800

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], is_collection=True, description="Image(s) to open in Fiji."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="image",
            accepted_types=[Image],
            is_collection=True,
            required=False,
            description="Image(s) edited / re-saved by the user.",
        )
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "macro_path": {
                "type": ["string", "null"],
                "default": None,
                "title": "Optional Fiji macro path",
                "ui_widget": "file_browser",
            },
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        images = _input_images(inputs, "image", "FijiBlock")
        exchange_dir = _resolve_exchange_dir(config, prefix="scieasy_fiji_")
        staged_paths = _prepare_image_exchange(images, exchange_dir, tool_name=self.type_name, config=config)

        extra_args: list[str] = []
        macro_path = config.get("macro_path")
        if macro_path:
            extra_args.extend(["--headless", "-macro", str(macro_path)])
        command = _resolve_command(
            config, app_command=self.app_command, override_key="fiji_path", extra_args=extra_args
        )

        # When no macro is provided Fiji opens images from its native file-opener.
        # Pass the staged TIFF paths directly so Fiji receives individual file paths
        # rather than the exchange directory root, which it cannot open (#420).
        launch_args: list[str] | None = None
        if not macro_path:
            launch_args = [str(p) for p in staged_paths]

        # Issue #680: when the user declares output ports (with extensions)
        # via the editor, broaden the watcher patterns to include each
        # declared extension so files of those types are not missed.
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
            launch_args=launch_args,
        )
        # Issue #680: route output files into user-declared ports by
        # extension. Falls back to legacy single-Artifact-per-file behaviour
        # only when no ports are declared in config (the ClassVar
        # ``output_ports`` above is the default scaffold the user may
        # override via the port editor).
        if config.get("output_ports"):
            return self._bin_outputs_by_extension(output_files, config)
        # Backwards-compatible single-port fallback: emit every file as an
        # Artifact under the "image" output port so existing graphs keep
        # working until the user opens the port editor.
        from scieasy.blocks.app.bridge import _guess_mime
        from scieasy.core.types.artifact import Artifact

        artifacts = [Artifact(file_path=p, mime_type=_guess_mime(p), description=p.name) for p in output_files]
        if not artifacts:
            return {}
        return {"image": Collection(artifacts, item_type=Artifact)}
