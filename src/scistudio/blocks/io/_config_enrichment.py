"""Shared dynamic config-schema enrichment for the core IO blocks.

The core ``Load`` / ``Save`` blocks (``load_data`` / ``save_data``) declare a
*static* ``core_type`` enum listing only the six built-in core ``DataObject``
types. At runtime the type registry also carries package-registered subtypes
(e.g. ``Spectrum`` from spectroscopy, ``Image`` from imaging) that have a load
or save capability and are loadable/saveable through the unified dispatch
(:mod:`scistudio.blocks.io._unified_dispatch`).

Historically only the HTTP block API recomputed the ``core_type`` enum from the
live registry, while the MCP ``get_block_schema`` / ``list_blocks`` tools served
the raw static enum. That made the AI agent believe core ``Load`` could not emit
``Spectrum`` even though the GUI dropdown and ``validate_workflow`` accepted it —
a three-way contract inconsistency. This module is the single source of truth so
every consumer (HTTP API, MCP tools, validation) sees the same enum.
"""

from __future__ import annotations

import copy
from typing import Any

_CORE_TYPE_ORDER = ["Array", "DataFrame", "Series", "Text", "Artifact", "CompositeData"]

_DYNAMIC_ENUM_BLOCKS = {"load_data", "save_data"}


def io_capable_type_names(registry: Any, type_registry: Any, *, direction: str) -> list[str]:
    """Return registered type names, IO-capable (``direction``) types ordered first.

    ``direction`` is ``"load"`` or ``"save"``. Core types keep their canonical
    order; package types that own a capability for ``direction`` come next; any
    remaining registered types follow so the enum never silently drops a type.
    """
    registered = set(type_registry.all_types().keys())
    capable = {capability.data_type.__name__ for capability in registry.list_format_capabilities(direction=direction)}
    ordered = [name for name in _CORE_TYPE_ORDER if name in registered]
    ordered.extend(sorted(capable - set(ordered)))
    ordered.extend(sorted(registered - set(ordered)))
    return ordered


def enrich_io_config_schema(spec: Any, registry: Any = None, type_registry: Any = None) -> dict[str, Any]:
    """Return *spec*'s ``config_schema`` with a dynamic ``core_type`` enum.

    No-op (returns the spec's static schema) for non core-IO blocks, for package
    IO blocks (which carry their own schema), and when either registry is
    unavailable.
    """
    schema = spec.config_schema or {"type": "object", "properties": {}}
    if registry is None or type_registry is None:
        return schema
    if getattr(spec, "type_name", None) not in _DYNAMIC_ENUM_BLOCKS:
        return schema

    direction = "load" if spec.type_name == "load_data" else "save"
    merged = copy.deepcopy(schema)
    properties = merged.setdefault("properties", {})
    properties.pop("allow_pickle", None)
    type_names = io_capable_type_names(registry, type_registry, direction=direction)
    properties["core_type"] = {
        **properties.get("core_type", {}),
        "title": "Type",
        "enum": type_names,
        "default": "DataFrame" if "DataFrame" in type_names else (type_names[0] if type_names else ""),
        "ui_priority": 1,
    }
    if "path" in properties:
        properties["path"]["title"] = "Path"
        properties["path"]["ui_priority"] = 0
        properties["path"]["ui_widget"] = "file_browser" if spec.type_name == "load_data" else "directory_browser"
    merged["required"] = ["path", "core_type"]
    return merged
