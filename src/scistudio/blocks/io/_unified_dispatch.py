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
    return delegated


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
    saver = saver_cls(config={"params": params})
    saver.save(obj, BlockConfig(params=params))
