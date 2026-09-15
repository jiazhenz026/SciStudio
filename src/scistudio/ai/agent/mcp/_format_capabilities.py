"""Format-capability views for the MCP block tools.

An IO format capability (``FormatCapability``) is one registered way to read or
write one data type as one file format, named by a stable ``capability_id``.
The GUI's Format dropdowns pick one; this module gives the agent the same
choices and the same answer to "which one will run".

- :func:`schema_format_capabilities` lists the capabilities a block can pick,
  for ``get_block_schema``.
- :func:`node_capability_view` reports the pinned and resolved capability of a
  workflow node, for ``get_block_config``.
- :func:`capability_patch_errors` checks a config patch that sets
  ``capability_id``, for ``update_block_config``.

Two block shapes carry a ``capability_id``:

- the core ``load_data`` / ``save_data`` blocks, on the node params, with the
  capability direction fixed by the block;
- blocks with file-exchange ports (the Code Block's ``inputs`` / ``outputs``,
  the App Block's ``input_ports`` / ``output_ports``), on each port entry. An
  input port is written for the script or app, so it uses a ``save``
  capability; an output port is read back, so it uses a ``load`` capability.

Everything reads the live block registry (``list_format_capabilities`` and the
``find_loader_capability`` / ``find_saver_capability`` lookups the runtime
uses). The core Load/Save list folds every ``Artifact`` capability into one
``Any`` choice, as the block API behind the GUI Format dropdown does
(``api/routes/blocks.py``); the AI layer may not import the API layer, so the
fold is restated here.
"""

# Development references: #2435, ADR-043.

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

CORE_IO_DIRECTIONS: dict[str, str] = {"load_data": "load", "save_data": "save"}
"""Capability direction of each core IO block."""

PORT_CAPABILITY_DIRECTIONS: dict[str, str] = {"input": "save", "output": "load"}
"""Capability direction used by a file-exchange port of each direction."""

_CODE_PORT_KEYS: dict[str, str] = {"inputs": "input", "outputs": "output"}
_APP_PORT_KEYS: dict[str, str] = {"input_ports": "input", "output_ports": "output"}
_ARTIFACT_ANY_PREFIX = "core.artifact.any."
_CORE_TYPE_DEFAULT = "DataFrame"
_CORE_TYPES = frozenset({"Array", "DataFrame", "Series", "Text", "Artifact", "CompositeData"})
_CORE_IO_OWNERS = frozenset({"LoadData", "SaveData"})
_CORE_PACKAGE = "scistudio"
_PLUGIN_PACKAGE_PREFIX = "scistudio-blocks-"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _list_capabilities(registry: Any, **filters: Any) -> list[Any]:
    lister = getattr(registry, "list_format_capabilities", None)
    if not callable(lister):
        return []
    try:
        return list(lister(**filters))
    except Exception:
        return []


def _package_by_capability_id(registry: Any) -> dict[str, str | None]:
    """Map each capability id to the package that provides it."""
    packages: dict[str, str | None] = {}
    all_specs = getattr(registry, "all_specs", None)
    if not callable(all_specs):
        return packages
    for spec in all_specs().values():
        raw_package = getattr(spec, "package_name", "") or ""
        module_path = getattr(spec, "module_path", "") or ""
        if raw_package.startswith(_PLUGIN_PACKAGE_PREFIX):
            package: str | None = raw_package
        elif module_path.startswith(f"{_CORE_PACKAGE}."):
            package = _CORE_PACKAGE
        else:
            package = raw_package or None
        for capability in getattr(spec, "format_capabilities", ()) or ():
            packages.setdefault(capability.id, package)
    return packages


def _entry(capability: Any, packages: Mapping[str, str | None]) -> dict[str, Any]:
    return {
        "capability_id": capability.id,
        "direction": capability.direction,
        "data_type": capability.data_type.__name__,
        "format_id": capability.format_id,
        "extensions": list(capability.extensions),
        "label": capability.label,
        "package": packages.get(capability.id),
        "priority": capability.priority,
        "is_default": capability.is_default,
        "pinnable": True,
    }


def _artifact_any_entry(direction: str) -> dict[str, Any]:
    return {
        "capability_id": f"{_ARTIFACT_ANY_PREFIX}{direction}",
        "direction": direction,
        "data_type": "Artifact",
        "format_id": "any",
        "extensions": [],
        "label": "Any",
        "package": _CORE_PACKAGE,
        "priority": 0,
        "is_default": True,
        # The GUI shows this fold as the only Artifact choice but never stores
        # it; the runtime has no capability under this id.
        "pinnable": False,
    }


def _core_io_entries(capabilities: Iterable[Any], *, direction: str, registry: Any) -> list[dict[str, Any]]:
    """Return core Load/Save choices, every Artifact capability folded into ``Any``."""
    packages = _package_by_capability_id(registry)
    entries: list[dict[str, Any]] = []
    artifact_inserted = False
    for capability in capabilities:
        if capability.data_type.__name__ != "Artifact":
            entries.append(_entry(capability, packages))
        elif not artifact_inserted:
            entries.append(_artifact_any_entry(direction))
            artifact_inserted = True
    return entries


def _sorted_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for entry in entries:
        unique.setdefault(f"{entry['direction']}:{entry['capability_id']}", entry)
    return sorted(
        unique.values(),
        key=lambda entry: (entry["direction"], entry["data_type"], -int(entry["priority"]), entry["capability_id"]),
    )


def port_capability_style(spec: Any) -> str | None:
    """Return ``"code"`` or ``"app"`` when *spec* carries per-port capability ids."""
    properties = (getattr(spec, "config_schema", None) or {}).get("properties", {})
    if not isinstance(properties, Mapping):
        return None
    if getattr(spec, "type_name", "") == "code_block" or (
        "script_path" in properties and all(key in properties for key in _CODE_PORT_KEYS)
    ):
        return "code"
    for key in _APP_PORT_KEYS:
        items = properties.get(key, {}).get("items", {}) if isinstance(properties.get(key), Mapping) else {}
        if isinstance(items, Mapping) and "capability_id" in (items.get("properties") or {}):
            return "app"
    return None


def _port_keys(style: str) -> dict[str, str]:
    return _CODE_PORT_KEYS if style == "code" else _APP_PORT_KEYS


def _resolve_data_type(type_name: str, registry: Any, type_registry: Any) -> type | None:
    """Resolve a data type name through the type registry, then the capability table."""
    from scistudio.core.types.base import DataObject

    if not type_name:
        return None
    load_class = getattr(type_registry, "load_class", None)
    if callable(load_class):
        try:
            cls = load_class(type_name)
        except Exception:
            cls = None
        if isinstance(cls, type) and issubclass(cls, DataObject):
            return cls
    for capability in _list_capabilities(registry):
        if capability.data_type.__name__ == type_name:
            resolved: type = capability.data_type
            return resolved
    return None


def _normalize_extension(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().lower()
    return text if text.startswith(".") else f".{text}"


def _selected_id(raw: Any) -> str | None:
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


# ---------------------------------------------------------------------------
# get_block_schema
# ---------------------------------------------------------------------------


def schema_format_capabilities(spec: Any, registry: Any) -> tuple[list[dict[str, Any]], str | None]:
    """Return ``(capabilities, usage)`` for ``get_block_schema``.

    Core Load/Save get the capabilities of their direction; file-exchange port
    blocks get both directions. Every other block gets an empty list and no
    usage note.
    """
    type_name = getattr(spec, "type_name", "")
    if type_name in CORE_IO_DIRECTIONS:
        direction = CORE_IO_DIRECTIONS[type_name]
        entries = _core_io_entries(
            _list_capabilities(registry, direction=direction), direction=direction, registry=registry
        )
        usage = (
            f"Set config capability_id to one of these {direction} capability ids whose data_type matches "
            "core_type (and whose extensions match the path, when it has one). Leave it unset to let the "
            "registry choose from core_type and the path extension; get_block_config reports that choice. "
            "Entries with pinnable=false are display-only and must not be stored."
        )
        return _sorted_entries(entries), usage
    style = port_capability_style(spec)
    if style is None:
        return [], None
    packages = _package_by_capability_id(registry)
    entries = [_entry(capability, packages) for capability in _list_capabilities(registry)]
    keys = _port_keys(style)
    input_key = next(key for key, direction in keys.items() if direction == "input")
    output_key = next(key for key, direction in keys.items() if direction == "output")
    type_field = "data_type" if style == "code" else "types[0]"
    usage = (
        f"Set capability_id on a port entry in config.{input_key} (direction 'save') or config.{output_key} "
        f"(direction 'load'), choosing a capability whose data_type matches the port's {type_field} and whose "
        "extensions include the port's extension. Leave it unset to let the registry choose; "
        "get_block_config reports that choice per port."
    )
    return _sorted_entries(entries), usage


# ---------------------------------------------------------------------------
# get_block_config
# ---------------------------------------------------------------------------


def _resolve(
    *,
    registry: Any,
    direction: str,
    data_type: type | None,
    extension: str | None,
    selected: str | None,
    candidate_ids: list[str],
    pinnable_ids: set[str],
) -> dict[str, Any]:
    """Resolve one capability choice into a status record.

    ``pinned``: a stored id that is a valid choice. ``invalid``: a stored id
    that is not. ``resolved``: nothing stored and the registry picks exactly
    one. ``ambiguous``: nothing stored and several remain. ``none``: nothing
    stored and nothing matches.
    """
    from scistudio.blocks.registry import AmbiguousCapabilityError

    view: dict[str, Any] = {
        "selected_capability_id": selected,
        "resolved_capability_id": None,
        "status": "none",
    }
    if selected is not None:
        if selected in pinnable_ids:
            view.update(resolved_capability_id=selected, status="pinned")
        else:
            view.update(status="invalid", candidates=candidate_ids)
        return view
    if data_type is None:
        view["candidates"] = candidate_ids
        return view
    finder = getattr(registry, "find_loader_capability" if direction == "load" else "find_saver_capability", None)
    if not callable(finder):
        return view
    try:
        capability = finder(data_type, extension)
    except AmbiguousCapabilityError as exc:
        ambiguous = list(getattr(exc, "candidates", ()) or ())
        # Save honours the type's declared default format when the lookup is
        # ambiguous, as the runtime does (``_unified_dispatch.selected_capability``).
        default = next((cap for cap in ambiguous if cap.is_default), None) if direction == "save" else None
        if default is not None:
            view.update(resolved_capability_id=default.id, status="resolved")
        else:
            view.update(status="ambiguous", candidates=[cap.id for cap in ambiguous])
        return view
    except Exception:
        view["candidates"] = candidate_ids
        return view
    view.update(resolved_capability_id=capability.id, status="resolved")
    return view


def _ancestor_type_names(data_type: type) -> set[str]:
    """Return the names of *data_type* and its ``DataObject`` bases (the GUI's type filter)."""
    from scistudio.core.types.base import DataObject

    return {cls.__name__ for cls in data_type.__mro__ if isinstance(cls, type) and issubclass(cls, DataObject)}


def _match_extension(capabilities: list[Any], extension: str | None) -> list[Any]:
    """Return the capabilities claiming *extension*, trying compound suffixes first."""
    if extension is None:
        return []
    parts = [part for part in extension.lower().split(".") if part]
    for start in range(len(parts)):
        suffix = "." + ".".join(parts[start:])
        matched = [capability for capability in capabilities if suffix in capability.extensions]
        if matched:
            return matched
    return []


def _folded_ids(capabilities: list[Any], direction: str) -> list[str]:
    ids: list[str] = []
    for capability in capabilities:
        capability_id = (
            f"{_ARTIFACT_ANY_PREFIX}{direction}" if capability.data_type.__name__ == "Artifact" else capability.id
        )
        if capability_id not in ids:
            ids.append(capability_id)
    return ids


def _core_io_view(block_type: str, params: Mapping[str, Any], registry: Any, type_registry: Any) -> dict[str, Any]:
    """Resolve the capability of a core Load/Save node.

    The choices are the capabilities of the block's direction whose data type
    is ``core_type`` or one of its bases, as the GUI Format dropdown filters
    them. With nothing stored, the six core types are read and written by the
    core block's own capability for the path extension (Save falls back to the
    type's first core format when there is no extension); any other type goes
    through the registry lookup the unified dispatch runs.
    """
    from scistudio.blocks.io._unified_dispatch import _path_extension

    direction = CORE_IO_DIRECTIONS[block_type]
    raw_type = params.get("core_type")
    core_type = raw_type.strip() if isinstance(raw_type, str) and raw_type.strip() else _CORE_TYPE_DEFAULT
    data_type = _resolve_data_type(core_type, registry, type_registry)
    try:
        extension = _path_extension(dict(params))
    except Exception:
        extension = None
    view: dict[str, Any] = {"direction": direction, "data_type": core_type, "extension": extension}
    if data_type is None:
        view.update(selected_capability_id=_selected_id(params.get("capability_id")), resolved_capability_id=None)
        view.update(status="invalid" if view["selected_capability_id"] else "none", candidates=[])
        return view

    ancestors = _ancestor_type_names(data_type)
    by_type = [c for c in _list_capabilities(registry, direction=direction) if c.data_type.__name__ in ancestors]
    by_extension = _match_extension(by_type, extension)
    is_core_type = core_type in _CORE_TYPES
    # A package type is delegated to its owning package block; the core block's
    # own capabilities cannot serve it.
    usable = [c for c in (by_extension or by_type) if is_core_type or c.block_type not in _CORE_IO_OWNERS]
    candidate_ids = _folded_ids(usable, direction)
    pinnable = {c.id for c in usable if c.data_type.__name__ != "Artifact"}

    selected = _selected_id(params.get("capability_id"))
    if selected is not None:
        view.update(selected_capability_id=selected, resolved_capability_id=None)
        if selected in pinnable:
            view.update(resolved_capability_id=selected, status="pinned")
        else:
            view.update(status="invalid", candidates=[c for c in candidate_ids if c in pinnable])
        return view

    all_ids = _folded_ids(by_type, direction)
    if len(all_ids) == 1:
        # The GUI shows a sole choice as the one in use (for Artifact, ``Any``).
        view.update(selected_capability_id=None, resolved_capability_id=all_ids[0], status="resolved")
        return view
    if is_core_type:
        owned = [
            c
            for c in (by_extension if extension is not None else by_type)
            if c.block_type in _CORE_IO_OWNERS and c.data_type is data_type
        ]
        chosen = owned[0] if owned and (extension is not None or direction == "save") else None
        view["selected_capability_id"] = None
        if chosen is not None:
            view.update(resolved_capability_id=chosen.id, status="resolved")
        elif len(candidate_ids) > 1 and not by_extension and extension is None:
            view.update(resolved_capability_id=None, status="ambiguous", candidates=candidate_ids)
        else:
            view.update(resolved_capability_id=None, status="none", candidates=candidate_ids)
        return view
    view.update(
        _resolve(
            registry=registry,
            direction=direction,
            data_type=data_type,
            extension=extension,
            selected=None,
            candidate_ids=candidate_ids,
            pinnable_ids=pinnable,
        )
    )
    return view


def _port_type_name(entry: Mapping[str, Any], style: str) -> str:
    if style == "code":
        raw = entry.get("data_type")
        return raw.strip() if isinstance(raw, str) and raw.strip() else "DataObject"
    types = entry.get("types")
    if isinstance(types, list) and types and isinstance(types[0], str) and types[0].strip():
        return types[0].strip()
    return "DataObject"


def _port_candidates(registry: Any, *, direction: str, data_type: type | None, extension: str | None) -> list[str]:
    if data_type is None:
        return []
    filters: dict[str, Any] = {"direction": direction, "data_type": data_type}
    if extension is not None:
        filters["extension"] = extension
    return sorted({capability.id for capability in _list_capabilities(registry, **filters)})


def _port_view(
    entry: Mapping[str, Any],
    *,
    port_direction: str,
    style: str,
    registry: Any,
    type_registry: Any,
) -> dict[str, Any]:
    direction = PORT_CAPABILITY_DIRECTIONS[port_direction]
    type_name = _port_type_name(entry, style)
    data_type = _resolve_data_type(type_name, registry, type_registry)
    extension = _normalize_extension(entry.get("extension"))
    candidate_ids = _port_candidates(registry, direction=direction, data_type=data_type, extension=extension)
    view: dict[str, Any] = {
        "port": str(entry.get("name", "")),
        "port_direction": port_direction,
        "direction": direction,
        "data_type": type_name,
        "extension": extension,
    }
    view.update(
        _resolve(
            registry=registry,
            direction=direction,
            data_type=data_type,
            extension=extension,
            selected=_selected_id(entry.get("capability_id")),
            candidate_ids=candidate_ids,
            pinnable_ids=set(candidate_ids),
        )
    )
    return view


def node_capability_view(
    block_type: str,
    params: Mapping[str, Any],
    registry: Any,
    type_registry: Any,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Return ``(node view, port views)`` for ``get_block_config``.

    The node view is set for core Load/Save; the port views for blocks with
    file-exchange ports. Both are empty for every other block.
    """
    if block_type in CORE_IO_DIRECTIONS:
        return _core_io_view(block_type, params, registry, type_registry), []
    get_spec = getattr(registry, "get_spec", None)
    spec = get_spec(block_type) if callable(get_spec) else None
    style = port_capability_style(spec) if spec is not None else None
    if style is None:
        return None, []
    ports: list[dict[str, Any]] = []
    for key, port_direction in _port_keys(style).items():
        entries = params.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, Mapping):
                ports.append(
                    _port_view(
                        entry,
                        port_direction=port_direction,
                        style=style,
                        registry=registry,
                        type_registry=type_registry,
                    )
                )
    return None, ports


# ---------------------------------------------------------------------------
# update_block_config
# ---------------------------------------------------------------------------


def _merged_params(current: Any, patch: Mapping[str, Any]) -> dict[str, Any]:
    """Return the effective params after ``update_block_config`` applies *patch*.

    Mirrors that tool's write: a ``params`` key replaces ``config.params``;
    every other key lands in ``config.params`` when the node nests its params
    there (dropping the same top-level key), otherwise at the top level.
    """
    from scistudio.ai.agent.mcp.tools_workflow._helpers import _effective_node_params

    if not isinstance(current, Mapping):
        return _effective_node_params(dict(patch))
    config: dict[str, Any] = dict(current)
    if "params" in patch:
        config["params"] = patch["params"]
    nested = config.get("params")
    if isinstance(nested, Mapping):
        nested = dict(nested)
        config["params"] = nested
    for key, value in patch.items():
        if key == "params":
            continue
        if isinstance(nested, dict):
            nested[key] = value
            config.pop(key, None)
        else:
            config[key] = value
    return _effective_node_params(config)


def _patched_keys(patch: Mapping[str, Any]) -> set[str]:
    keys = {key for key in patch if key != "params"}
    nested = patch.get("params")
    if isinstance(nested, Mapping):
        keys.update(nested)
    return keys


def _type_error(raw: Any, where: str) -> str | None:
    if raw is None or isinstance(raw, str):
        return None
    return f"{where}: capability_id must be a string, or null/empty to clear it; got {type(raw).__name__}."


def _choices_text(candidate_ids: list[str]) -> str:
    return ", ".join(candidate_ids) if candidate_ids else "none registered"


def capability_patch_errors(
    block_type: str,
    current_config: Any,
    patch: Mapping[str, Any],
    registry: Any,
    type_registry: Any,
) -> list[str]:
    """Return why a config patch stores an unusable ``capability_id``.

    Only a patch that sets ``capability_id`` (on a core Load/Save node, or on
    an entry of a file-exchange port list) is checked, against the config the
    patch produces. ``null`` or an empty string clears the pin and is always
    accepted. An empty list means the patch may be written.
    """
    if not _list_capabilities(registry):
        return []
    keys = _patched_keys(patch)
    merged = _merged_params(current_config, patch)
    errors: list[str] = []
    if block_type in CORE_IO_DIRECTIONS:
        if "capability_id" not in keys:
            return []
        raw = merged.get("capability_id")
        type_error = _type_error(raw, block_type)
        if type_error is not None:
            return [type_error]
        view = _core_io_view(block_type, merged, registry, type_registry)
        if isinstance(raw, str) and raw.strip().startswith(_ARTIFACT_ANY_PREFIX):
            return [
                f"{block_type}: capability_id {raw!r} is the display-only 'Any' choice for Artifact and is not "
                "a registered capability. Leave capability_id unset (send null) for Artifact."
            ]
        if view["status"] == "invalid":
            errors.append(
                f"{block_type}: capability_id {raw!r} is not a {view['direction']} capability for "
                f"core_type {view['data_type']!r}"
                + (f" and extension {view['extension']!r}" if view["extension"] else "")
                + f". Valid choices: {_choices_text([c for c in view.get('candidates', []) if not c.startswith(_ARTIFACT_ANY_PREFIX)])}. "
                "Send null to clear it."
            )
        return errors
    get_spec = getattr(registry, "get_spec", None)
    spec = get_spec(block_type) if callable(get_spec) else None
    style = port_capability_style(spec) if spec is not None else None
    if style is None:
        return []
    for key, port_direction in _port_keys(style).items():
        if key not in keys:
            continue
        entries = merged.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping) or "capability_id" not in entry:
                continue
            where = f"{key}[{entry.get('name', '?')!s}]"
            type_error = _type_error(entry.get("capability_id"), where)
            if type_error is not None:
                errors.append(type_error)
                continue
            view = _port_view(
                entry, port_direction=port_direction, style=style, registry=registry, type_registry=type_registry
            )
            if view["status"] == "invalid":
                errors.append(
                    f"{where}: capability_id {entry.get('capability_id')!r} is not a {view['direction']} capability "
                    f"for data type {view['data_type']!r}"
                    + (f" and extension {view['extension']!r}" if view["extension"] else "")
                    + f". Valid choices: {_choices_text(view.get('candidates', []))}. Send null or '' to clear it."
                )
    return errors


__all__ = [
    "CORE_IO_DIRECTIONS",
    "PORT_CAPABILITY_DIRECTIONS",
    "capability_patch_errors",
    "node_capability_view",
    "port_capability_style",
    "schema_format_capabilities",
]
