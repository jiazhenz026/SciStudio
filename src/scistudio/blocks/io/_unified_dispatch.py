"""Runtime helpers for ADR-043 unified Load/Save dispatch.

Core ``Load`` / ``Save`` remain the user-facing blocks. When their selected
capability belongs to a package IO block, these helpers resolve and invoke the
owning block while preserving the stable core block surface in workflow YAML.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.io.capabilities import FormatCapability
from scistudio.core.types.base import DataObject


def _scan_runtime_registry(
    registry: Any, *, project_child: str, home_child: str, scan_method: str, always_home: bool
) -> Any:
    """Apply runtime project/user scan paths and execute the requested scan."""
    project_dir = os.environ.get("SCISTUDIO_PROJECT_DIR")
    if project_dir:
        registry.add_scan_dir(Path(project_dir) / project_child)
    if always_home or project_dir:
        registry.add_scan_dir(Path.home() / ".scistudio" / home_child)
    getattr(registry, scan_method)(include_monorepo=os.environ.get("SCISTUDIO_DEV") == "1")
    return registry


def runtime_block_registry() -> Any:
    """Build a registry that mirrors API/worker project scan locations."""
    from scistudio.blocks.registry import BlockRegistry

    return _scan_runtime_registry(
        BlockRegistry(), project_child="blocks", home_child="blocks", scan_method="scan", always_home=False
    )


def runtime_type_registry() -> Any:
    """Build a type registry that includes core, package, and custom types."""
    from scistudio.core.types.registry import TypeRegistry

    return _scan_runtime_registry(
        TypeRegistry(), project_child="types", home_child="types", scan_method="scan_all", always_home=True
    )


def resolve_type_class(type_name: str) -> type[DataObject] | None:
    """Resolve a registered ``DataObject`` subclass by display name."""
    try:
        cls = runtime_type_registry().load_class(type_name)
    except Exception:
        return None
    if isinstance(cls, type) and issubclass(cls, DataObject):
        return cls
    return None


def capability_by_id(registry: Any, capability_id: str, *, direction: str) -> FormatCapability | None:
    """Return a registered capability by stable id and direction."""
    for capability in registry.list_format_capabilities(direction=direction):
        if capability.id == capability_id:
            return cast(FormatCapability, capability)
    return None


def capability_owner_class(registry: Any, capability: FormatCapability) -> type[Any]:
    """Load the block class that owns ``capability``."""
    block_cls = registry._resolve_capability_class(capability)
    if block_cls is None:
        raise LookupError(
            f"ADR-043 capability {capability.id!r} resolved but owner {capability.block_type!r} could not be imported."
        )
    return cast(type[Any], block_cls)


def selected_capability(
    *,
    direction: str,
    params: dict[str, Any],
    data_type: type[DataObject] | None,
) -> tuple[Any, FormatCapability | None]:
    """Resolve the selected capability from ``capability_id`` or path/type."""
    registry = runtime_block_registry()
    raw_id = params.get("capability_id")
    capability_id = raw_id if isinstance(raw_id, str) and raw_id.strip() else None
    if capability_id:
        return registry, capability_by_id(registry, capability_id, direction=direction)

    if data_type is None:
        return registry, None
    raw_path = params.get("path")
    extension = None
    if isinstance(raw_path, str) and raw_path:
        suffixes = Path(raw_path).suffixes
        extension = "".join(suffixes) if suffixes else None
    finder = registry.find_loader_capability if direction == "load" else registry.find_saver_capability
    try:
        return registry, finder(data_type, extension)
    except Exception:
        return registry, None


def delegate_params(params: dict[str, Any], capability: FormatCapability) -> dict[str, Any]:
    """Build config params for the package IO block behind a core proxy."""
    delegated = {key: value for key, value in params.items() if key != "core_type"}
    delegated["capability_id"] = capability.id
    delegated["format_id"] = capability.format_id
    delegated.setdefault("format", capability.format_id)
    return delegated


def _default_delegated_filename(data_type: type[DataObject], capability: FormatCapability) -> str | None:
    if not capability.extensions:
        return None
    return f"{data_type.__name__.lower()}{capability.extensions[0]}"


def _source_filename(obj: DataObject) -> str | None:
    raw_file_path = getattr(obj, "file_path", None)
    if raw_file_path:
        return Path(str(raw_file_path)).name
    framework = getattr(obj, "framework", None)
    source = getattr(framework, "source", "")
    if isinstance(source, str) and source:
        return Path(source).name
    return None


def _filename_config(params: dict[str, Any]) -> str | None:
    raw = params.get("filename")
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError(f"SaveData: config['filename'] must be a string or omitted, got {type(raw).__name__}")
    cleaned = raw.strip()
    if not cleaned:
        return None
    name = Path(cleaned).name
    if name in {"", ".", ".."}:
        raise ValueError("SaveData: filename must be a file name, not a directory path.")
    return name


def _filename_with_extension(name: str, capability: FormatCapability) -> str:
    if not capability.extensions:
        return name
    path = Path(name)
    supported = {extension.lower() for extension in capability.extensions}
    if path.suffix.lower() in supported:
        return path.name
    stem = path.stem if path.suffix else path.name
    return f"{stem}{capability.extensions[0]}"


def _delegated_filename(
    params: dict[str, Any],
    *,
    obj: DataObject,
    data_type: type[DataObject],
    capability: FormatCapability,
) -> str:
    configured = _filename_config(params)
    if configured is not None:
        return _filename_with_extension(configured, capability)
    source_name = _source_filename(obj)
    if source_name:
        return _filename_with_extension(source_name, capability)
    default = _default_delegated_filename(data_type, capability)
    if default is not None and not Path(str(params.get("path", ""))).is_dir():
        return default
    raise ValueError(
        "SaveData cannot infer an output filename because the input object has no source filename. "
        "Set the Save block filename field."
    )


def _resolve_delegated_save_path(
    params: dict[str, Any],
    *,
    obj: DataObject,
    data_type: type[DataObject],
    capability: FormatCapability,
) -> None:
    raw_path = params.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return
    path = Path(raw_path)
    original_path = path
    if path.is_dir():
        path = path / _delegated_filename(params, obj=obj, data_type=data_type, capability=capability)
    elif not path.suffix and capability.extensions:
        path = path.with_suffix(capability.extensions[0])
    if path != original_path:
        params["path"] = str(path)
    if path.exists() and not bool(params.get("overwrite", False)):
        raise ValueError(
            f"SaveData refuses to overwrite existing output {str(path)!r}. Choose an empty folder or a new output path."
        )


def delegate_load(
    *,
    config: BlockConfig,
    output_dir: str,
    core_type: str,
) -> DataObject:
    """Load through the package block selected by a core Load capability."""
    data_type = resolve_type_class(core_type)
    registry, capability = selected_capability(direction="load", params=dict(config.params), data_type=data_type)
    if capability is None:
        raise ValueError(f"Load: no ADR-043 load capability is registered for type {core_type!r}.")
    if capability.block_type == "LoadData":
        raise ValueError(f"Load: selected capability {capability.id!r} did not resolve to a package loader.")
    loader_cls = capability_owner_class(registry, capability)
    params = delegate_params(dict(config.params), capability)
    loader = loader_cls(config={"params": params})
    return cast(DataObject, loader.load(BlockConfig(params=params), output_dir))


def delegate_save(
    *,
    obj: DataObject,
    config: BlockConfig,
    core_type: str,
) -> None:
    """Save through the package block selected by a core Save capability."""
    data_type = resolve_type_class(core_type) or type(obj)
    registry, capability = selected_capability(direction="save", params=dict(config.params), data_type=data_type)
    if capability is None:
        raise ValueError(f"Save: no ADR-043 save capability is registered for type {core_type!r}.")
    if capability.block_type == "SaveData":
        raise ValueError(f"Save: selected capability {capability.id!r} did not resolve to a package saver.")
    saver_cls = capability_owner_class(registry, capability)
    params = delegate_params(dict(config.params), capability)
    _resolve_delegated_save_path(params, obj=obj, data_type=data_type, capability=capability)
    if params.get("path") != config.params.get("path"):
        config.params["path"] = params["path"]
    saver = saver_cls(config={"params": params})
    saver.save(obj, BlockConfig(params=params))
