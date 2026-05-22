"""Interactive AppBlock helpers and exports for the imaging plugin."""

from __future__ import annotations

import json
import logging
import platform
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scistudio.blocks.app.app_block import AppBlock, _PopenProcessAdapter
from scistudio.blocks.app.bridge import FileExchangeBridge
from scistudio.blocks.app.watcher import FileWatcher, ProcessExitedWithoutOutputError
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, ports_from_config_dicts
from scistudio.blocks.base.state import BlockState
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.collection import Collection
from scistudio_blocks_imaging.types import Image

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from scistudio_blocks_imaging.interactive.fiji_block import FijiBlock
    from scistudio_blocks_imaging.interactive.napari_block import NapariBlock


def _resolve_exchange_dir(config: BlockConfig, *, prefix: str) -> Path:
    explicit_dir = config.get("exchange_dir")
    if explicit_dir:
        exchange_dir = Path(str(explicit_dir))
    else:
        project_dir = config.get("project_dir")
        block_id = config.get("block_id")
        if project_dir and block_id:
            exchange_dir = Path(str(project_dir)) / "data" / "exchange" / str(block_id)
        else:
            exchange_dir = Path(tempfile.mkdtemp(prefix=prefix))
    exchange_dir.mkdir(parents=True, exist_ok=True)
    (exchange_dir / "inputs").mkdir(exist_ok=True)
    (exchange_dir / "outputs").mkdir(exist_ok=True)
    return exchange_dir


def _input_images(inputs: Mapping[str, Collection | Image], port_name: str, block_name: str) -> list[Image]:
    raw = inputs.get(port_name)
    if raw is None:
        raise ValueError(f"{block_name}: missing required input port {port_name!r}")
    if isinstance(raw, Collection):
        images: list[Image] = []
        for index, item in enumerate(raw):
            if not isinstance(item, Image):
                raise ValueError(f"{block_name}: {port_name}[{index}] must be Image, got {type(item).__name__}")
            images.append(item)
        return images
    if isinstance(raw, Image):
        return [raw]
    raise ValueError(f"{block_name}: input {port_name!r} must be Image or Collection[Image], got {type(raw).__name__}")


def _prepare_image_exchange(
    images: list[Image], exchange_dir: Path, *, tool_name: str, config: BlockConfig
) -> list[Path]:
    import numpy as np
    import tifffile

    input_dir = exchange_dir / "inputs"
    paths: list[Path] = []
    for index, image in enumerate(images):
        path = input_dir / f"image_{index:04d}.tif"
        # Materialise image data (in-memory or from storage_ref).
        if image.storage_ref is None and getattr(image, "_data", None) is not None:
            data = np.asarray(image._data)  # type: ignore[attr-defined]
        else:
            data = np.asarray(image.to_memory())
        tifffile.imwrite(str(path), data, metadata={"axes": "".join(image.axes).upper()})
        paths.append(path)

    manifest = {
        "tool": tool_name,
        "input_files": [str(path) for path in paths],
        "output_dir": str(exchange_dir / "outputs"),
        "config": dict(config.params),
    }
    (exchange_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return paths


def _effective_input_ports(block: AppBlock, config: BlockConfig) -> list[InputPort]:
    configured_ports = config.get("input_ports")
    if type(block).variadic_inputs and configured_ports and isinstance(configured_ports, list):
        return ports_from_config_dicts(configured_ports, "input")  # type: ignore[return-value]
    return list(type(block).input_ports)


def _prepare_configured_input_exchange(
    block: AppBlock,
    inputs: Mapping[str, Collection | Image | Artifact],
    exchange_dir: Path,
    *,
    tool_name: str,
    config: BlockConfig,
) -> list[Path]:
    """Stage every effective input port for Fiji/Napari exchange."""
    input_dir = exchange_dir / "inputs"
    input_dir.mkdir(exist_ok=True)
    staged_image_paths: list[Path] = []
    manifest_inputs: dict[str, Any] = {}

    for port in _effective_input_ports(block, config):
        if port.name not in inputs:
            if port.required and port.default is None:
                raise ValueError(f"{type(block).__name__}: missing required input port {port.name!r}")
            continue
        value = inputs[port.name]
        items = list(value) if isinstance(value, Collection) else [value]
        item_entries: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            if isinstance(item, Image):
                image_path = _stage_image_input(
                    item,
                    input_dir,
                    port_name=port.name,
                    index=index,
                    legacy_flat_layout=port.name == "image",
                )
                staged_image_paths.append(image_path)
                item_entries.append(
                    {
                        "type": "Image",
                        "path": str(image_path),
                        "extension": image_path.suffix,
                        "format": "tiff",
                    }
                )
                continue
            if isinstance(item, Artifact):
                artifact_path = _stage_artifact_input(item, input_dir / port.name, index=index)
                item_entries.append(
                    {
                        "type": "Artifact",
                        "path": str(artifact_path),
                        "extension": artifact_path.suffix,
                        "format": "file",
                    }
                )
                continue
            raise NotImplementedError(
                f"{type(block).__name__}: input port {port.name!r} item {index} has unsupported type "
                f"{type(item).__name__}; interactive imaging exchange supports Image and Artifact inputs"
            )

        manifest_inputs[port.name] = {
            "type": "collection"
            if isinstance(value, Collection)
            else (item_entries[0]["type"] if item_entries else "empty"),
            "item_type": _collection_item_type_name(value) if isinstance(value, Collection) else None,
            "items": item_entries,
        }

    manifest = {
        "tool": tool_name,
        "input_files": [str(path) for path in staged_image_paths],
        "inputs": manifest_inputs,
        "output_dir": str(exchange_dir / "outputs"),
        "config": dict(config.params),
    }
    (exchange_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return staged_image_paths


def _stage_image_input(
    image: Image,
    input_dir: Path,
    *,
    port_name: str,
    index: int,
    legacy_flat_layout: bool,
) -> Path:
    import numpy as np
    import tifffile

    if legacy_flat_layout:
        path = input_dir / f"image_{index:04d}.tif"
    else:
        port_dir = input_dir / port_name
        port_dir.mkdir(exist_ok=True)
        path = port_dir / f"{port_name}_{index:04d}.tif"
    if image.storage_ref is None and getattr(image, "_data", None) is not None:
        data = np.asarray(image._data)  # type: ignore[attr-defined]
    else:
        data = np.asarray(image.to_memory())
    tifffile.imwrite(str(path), data, metadata={"axes": "".join(image.axes).upper()})
    return path


def _stage_artifact_input(artifact: Artifact, port_dir: Path, *, index: int) -> Path:
    source = artifact.file_path
    if source is None:
        raise ValueError("Artifact input cannot be staged because file_path is None")
    source = Path(source)
    if not source.is_file():
        raise ValueError(f"Artifact input cannot be staged because file_path does not exist: {source}")
    port_dir.mkdir(parents=True, exist_ok=True)
    target = port_dir / source.name
    if target.exists():
        target = port_dir / f"{source.stem}_{index:04d}{source.suffix}"
    shutil.copy2(source, target)
    return target


def _collection_item_type_name(value: Collection) -> str:
    item_type = getattr(value, "item_type", None)
    if item_type is not None:
        return item_type.__name__
    names = {type(item).__name__ for item in value}
    if len(names) == 1:
        return next(iter(names))
    return "mixed" if names else "unknown"


def _resolve_command(
    config: BlockConfig,
    *,
    app_command: str,
    override_key: str | None = None,
    extra_args: list[str] | None = None,
) -> str | list[str]:
    """Resolve the executable command from config or ClassVar default.

    Priority order:
    1. MRO-injected ``app_command`` config field (from AppBlock base)
    2. Legacy block-specific override key (e.g. ``fiji_path``) for backward compat
    3. ClassVar ``app_command`` default on the block class
    """
    # 1. Check the MRO-injected app_command config field
    raw_command = config.get("app_command")
    if raw_command is not None:
        if isinstance(raw_command, list):
            return [str(part) for part in raw_command]
        if isinstance(raw_command, str):
            return raw_command
        raise ValueError(f"Interactive app command must be str or list[str], got {type(raw_command).__name__}")

    # 2. Legacy: check block-specific override key (for backward compat with
    #    old configs that may still have fiji_path / napari_path)
    if override_key:
        override = config.get(override_key)
        if override:
            return [str(override), *(extra_args or [])]

    # 3. Fall back to ClassVar default
    return [app_command, *(extra_args or [])]


def _open_file_manager(path: Path) -> None:
    """Best-effort: open the OS file manager at *path*."""
    try:
        system = platform.system()
        if system == "Windows":
            import os

            os.startfile(str(path))  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass  # best-effort, never block the workflow


def _run_external_app(
    block: AppBlock,
    *,
    command: str | list[str],
    exchange_dir: Path,
    patterns: list[str],
    config: BlockConfig,
    launch_args: list[str] | None = None,
) -> list[Path]:
    """Launch an external application and wait for output files.

    Parameters
    ----------
    launch_args:
        When provided, these strings are appended to the validated command
        instead of the default ``str(exchange_dir)`` suffix.  Pass the staged
        TIFF file paths here for applications (e.g. Fiji native opener) that
        expect individual file paths rather than the exchange directory root
        (see issue #420).
    """
    bridge = FileExchangeBridge()
    timeout = int(config.get("watch_timeout", getattr(block, "watch_timeout", 300)))
    stability_period = float(config.get("stability_period", 0.5))
    done_marker = config.get("done_marker")

    if block.state == BlockState.RUNNING:
        block.transition(BlockState.PAUSED)

    # ADR-030 D3: use user-selected output_dir if configured.
    custom_output_dir = config.get("output_dir")
    output_dir = Path(str(custom_output_dir)) if custom_output_dir else exchange_dir / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Waiting for external application output. Save files to: %s", output_dir)

    proc = bridge.launch(command, exchange_dir, argv_override=launch_args)
    watcher = FileWatcher(
        directory=output_dir,
        patterns=patterns,
        timeout=timeout,
        process_handle=_PopenProcessAdapter(proc),
        stability_period=stability_period,
        done_marker=str(done_marker) if done_marker is not None else None,
    )
    watcher.start()
    try:
        output_files = watcher.wait_for_output()
    except ProcessExitedWithoutOutputError:
        if block.state == BlockState.PAUSED:
            block.transition(BlockState.CANCELLED)
        return []
    except Exception:
        if block.state == BlockState.PAUSED:
            block.transition(BlockState.ERROR)
        raise
    finally:
        watcher.stop()
        with suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)

    if block.state == BlockState.PAUSED:
        block.transition(BlockState.RUNNING)
    if block.state == BlockState.RUNNING:
        block.transition(BlockState.DONE)
    return output_files


# Issue #680: per-plugin output classification heuristics
# (``_collect_outputs`` / ``_guess_output_port``) were removed in favour of
# the generic extension-based binner on ``AppBlock`` itself. Subclasses now
# return ``self._bin_outputs_by_extension(output_files, config)`` after
# launching the external app. Image-specific loaders (Mask/Label/DataFrame
# constructors) are no longer needed here — downstream blocks consume the
# resulting ``Artifact`` Collections via standard load blocks.


__all__ = ["FijiBlock", "NapariBlock"]


def __getattr__(name: str) -> Any:
    if name == "FijiBlock":
        from scistudio_blocks_imaging.interactive.fiji_block import FijiBlock

        return FijiBlock
    if name == "NapariBlock":
        from scistudio_blocks_imaging.interactive.napari_block import NapariBlock

        return NapariBlock
    raise AttributeError(name)
