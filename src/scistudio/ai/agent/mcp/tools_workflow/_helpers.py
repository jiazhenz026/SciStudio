"""Shared helpers for the ``tools_workflow`` sub-package."""
# Maintainer context (kept outside generated API documentation):
# Shared helpers for the ``tools_workflow`` sub-package.
#
# ADR-040 §3.1 FastMCP migration. Extracted from the original single-file
# ``tools_workflow.py`` (#1431, umbrella #1427) so each sub-module stays
# below the 750 LOC god-file threshold. No behavior change.
#
# Public surface preserved at ``scistudio.ai.agent.mcp.tools_workflow``
# via the package ``__init__`` re-exports.
# Development references: #1427, #1431, ADR-040.

from __future__ import annotations

import contextlib
import dataclasses
import os
import tempfile
from pathlib import Path
from typing import Any

from scistudio.ai.agent.mcp._context import get_context

_LOCK_TIMEOUT_SECONDS: float = 10.0
"""File lock timeout for atomic-write tools."""
# Development references: ADR-033.


def _spec_to_dict(spec: Any) -> dict[str, Any]:
    """Serialise a :class:`BlockSpec` (dataclass) to a JSON-safe dict.

    ``input_ports`` and ``output_ports`` carry :class:`Port` instances
    that are not natively JSON-serialisable; we project them to a
    minimal {name, type, required} envelope.
    """
    if dataclasses.is_dataclass(spec) and not isinstance(spec, type):
        raw = dataclasses.asdict(spec)
    else:  # pragma: no cover - non-dataclass spec
        raw = dict(spec.__dict__)
    raw["input_ports"] = [_port_to_dict(p) for p in (spec.input_ports or [])]
    raw["output_ports"] = [_port_to_dict(p) for p in (spec.output_ports or [])]
    return raw


def _port_to_dict(port: Any) -> dict[str, Any]:
    """Project a :class:`Port` to a JSON-safe dict.

    ``type`` renders the port's ``accepted_types`` exactly as the
    ``list_blocks`` signature does (``A|B``, ``Any``, a ``[]`` suffix for
    collection ports). Ports have no ``.type`` attribute; reading one made
    every type an empty string.
    """
    # Development references: #2315.
    if isinstance(port, dict):
        return port
    return {
        "name": getattr(port, "name", ""),
        "type": _render_port_type(port),
        "required": bool(getattr(port, "required", False)),
    }


def _render_port_type(port: Any) -> str:
    """Render a port's accepted type(s) for a catalog signature.

    SciStudio ports declare their type via ``accepted_types`` (a list of type
    classes); an empty list means "accept/emit any data object" and renders as
    ``Any``. Multiple accepted types render as ``A|B``; collection ports get a
    ``[]`` suffix.
    """
    if isinstance(port, dict):
        accepted = port.get("accepted_types") or []
        is_collection = bool(port.get("is_collection"))
    else:
        accepted = getattr(port, "accepted_types", None) or []
        is_collection = bool(getattr(port, "is_collection", False))
    names = [getattr(t, "__name__", str(t)) for t in accepted]
    rendered = "|".join(names) if names else "Any"
    return f"{rendered}[]" if is_collection else rendered


def _spec_signature(spec: Any) -> str:
    """Render a one-line I/O signature for a block's catalog entry.

    Example: ``image:Image, mask?:Array → result:Image``. Port types come from
    each port's ``accepted_types`` (``Any`` when none is declared); optional
    ports carry a ``?`` suffix; collection ports a ``[]`` suffix; an empty side
    renders as ``()``. Variadic sides append a ``*:<Type|Type>`` element (after
    any fixed seed ports) to signal that more ports of those types may be
    added — ``*:Any`` when no allowed types are declared.

    This is the only I/O detail ``list_blocks`` carries — enough for the
    agent to judge wiring compatibility during selection without fetching
    the full per-block schema. Call ``get_block_schema`` for exact port
    names/types and the config_schema.
    """

    def _port_name(port: Any) -> str:
        if isinstance(port, dict):
            return port.get("name") or "?"
        return getattr(port, "name", "") or "?"

    def _port_required(port: Any) -> bool:
        if isinstance(port, dict):
            return bool(port.get("required", True))
        return bool(getattr(port, "required", True))

    def _fmt_side(ports: Any, variadic: bool, allowed: Any) -> str:
        rendered = []
        for port in ports or []:
            optional = "" if _port_required(port) else "?"
            rendered.append(f"{_port_name(port)}{optional}:{_render_port_type(port)}")
        if variadic:
            allowed_types = [str(a) for a in (allowed or [])]
            rendered.append("*:" + ("|".join(allowed_types) if allowed_types else "Any"))
        return ", ".join(rendered) if rendered else "()"

    inputs = _fmt_side(
        spec.input_ports,
        bool(getattr(spec, "variadic_inputs", False)),
        getattr(spec, "allowed_input_types", None),
    )
    outputs = _fmt_side(
        spec.output_ports,
        bool(getattr(spec, "variadic_outputs", False)),
        getattr(spec, "allowed_output_types", None),
    )
    return f"{inputs} → {outputs}"


# ---------------------------------------------------------------------------
# Core-IO steering (#1900): flag package-specific IO blocks whose data the
# core Load/Save block already covers via its dynamic ``core_type`` enum.
# ---------------------------------------------------------------------------


_PACKAGE_MODULE_PREFIX = "scistudio_blocks_"


def _is_package_io_block(spec: Any) -> bool:
    """True for an IO block contributed by a ``scistudio_blocks_*`` plugin package.

    The core Load/Save block (``load_data`` / ``save_data``) already covers every
    loadable/saveable package type through its dynamic ``core_type`` enum and
    delegates to the owning package under the hood (see
    ``blocks.io._config_enrichment``). A package's own IO block is therefore
    redundant and yields a different, inconsistent canvas node for the same data.

    Detection keys off the block's importable ``module_path`` (plugin packages
    live under the ``scistudio_blocks_*`` install module). ``package_name`` is
    not used because core blocks registered via entry points carry the entry-point
    name there (e.g. ``load_data``), so it is not a reliable core-vs-package
    signal. User drop-in ``.py`` blocks are intentionally excluded — they may
    handle a type the core block does not cover.
    """
    if getattr(spec, "base_category", "") != "io":
        return False
    return str(getattr(spec, "module_path", "") or "").startswith(_PACKAGE_MODULE_PREFIX)


def _first_port_type_name(port: Any) -> str | None:
    """Return the first accepted-type name of *port*, or ``None``."""
    if isinstance(port, dict):
        accepted = port.get("accepted_types") or []
    else:
        accepted = getattr(port, "accepted_types", None) or []
    names = [getattr(t, "__name__", str(t)) for t in accepted]
    return names[0] if names else None


def _core_io_equivalent(spec: Any) -> tuple[str, str | None]:
    """Return ``(core_block_type, core_type_value)`` for a package IO block.

    ``core_block_type`` is ``"load_data"`` for a loader (reads a file, exposes an
    output port) or ``"save_data"`` for a saver (writes a file, exposes an input
    port). ``core_type_value`` is the concrete data type the block handles (e.g.
    ``"Image"``), read from the relevant port's accepted types, or ``None`` when
    it cannot be determined.
    """
    direction = getattr(spec, "direction", "") or ""
    input_ports = getattr(spec, "input_ports", None) or []
    output_ports = getattr(spec, "output_ports", None) or []
    is_saver = direction == "output" or (bool(input_ports) and not output_ports)
    if is_saver:
        core_block, ports = "save_data", input_ports
    else:
        core_block, ports = "load_data", output_ports
    core_type: str | None = None
    for port in ports:
        core_type = _first_port_type_name(port)
        if core_type:
            break
    return core_block, core_type


def _io_redirect_hint(spec: Any) -> str | None:
    """Build a 'use the core block instead' hint for a package IO block.

    Returns ``None`` for core blocks and non-IO blocks.
    """
    if not _is_package_io_block(spec):
        return None
    core_block, core_type = _core_io_equivalent(spec)
    if core_type:
        return (
            f"Do not use this package IO block. Use the core '{core_block}' block "
            f"with core_type='{core_type}' instead — it delegates to the same "
            f"package loader/saver and keeps one consistent GUI node."
        )
    return (
        f"Do not use this package IO block. Use the core '{core_block}' block "
        f"configured with the matching core_type instead."
    )


# ---------------------------------------------------------------------------
# Core-IO steering warnings (#2376): one advisory source shared by every
# workflow-authoring MCP tool (write_workflow, edit_workflow,
# update_block_config, validate_workflow). Warnings never block a write.
# ---------------------------------------------------------------------------


_CORE_IO_BLOCK_TYPES = frozenset({"load_data", "save_data"})


def _core_io_covered_types(registry: Any, type_registry: Any, *, direction: str) -> frozenset[str]:
    """Return the type names the core Load/Save block can actually handle.

    Reuses the core block's own enum builder
    (:func:`~scistudio.blocks.io._config_enrichment.io_capable_type_names`) and
    keeps only the entries backed by a registered format capability for
    *direction* (the same capability table
    :func:`~scistudio.blocks.io._config_enrichment.format_extensions_by_type`
    groups). The enum also lists registered types with no capability so it
    never drops a type; the core block cannot load or save those, so they are
    not "covered". Returns an empty set when either registry is unavailable.
    """
    if registry is None or type_registry is None:
        return frozenset()
    from scistudio.blocks.io._config_enrichment import format_extensions_by_type, io_capable_type_names

    try:
        enum_names = io_capable_type_names(registry, type_registry, direction=direction)
        capable = format_extensions_by_type(registry, direction=direction)
    except Exception:  # pragma: no cover - defensive: registry not ready
        return frozenset()
    return frozenset(name for name in enum_names if name in capable)


def _node_field(node: Any, key: str) -> Any:
    """Read *key* from a workflow node given as a model, dataclass, or mapping."""
    if isinstance(node, dict):
        return node.get(key)
    return getattr(node, key, None)


def _core_type_unset(config: Any) -> bool:
    """True when a node config carries no usable ``core_type`` value.

    The core Load/Save block declares ``core_type`` required, but its runtime
    silently falls back to ``DataFrame`` when the key is absent, so a missing,
    null, or blank value is treated as unconfigured.
    """
    if not isinstance(config, dict):
        return True
    value = config.get("core_type")
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _core_io_node_warning(
    node_id: str,
    block_type: str,
    config: Any,
    spec: Any,
    covered: Any,
) -> str | None:
    """Return the steering warning for one node, or ``None``.

    ``covered`` is a callable ``direction -> frozenset[str]`` so the capability
    table is only read when a custom IO block needs it.
    """
    prefix = f"node '{node_id}':"
    if block_type in _CORE_IO_BLOCK_TYPES:
        if _core_type_unset(config):
            return (
                f"{prefix} core '{block_type}' has no core_type configured, so the runtime "
                f"silently treats the data as DataFrame. Set config.core_type to the data "
                f"type this node handles (get_block_schema('{block_type}') lists the valid values)."
            )
        return None
    if getattr(spec, "base_category", "") != "io":
        return None
    core_block, core_type = _core_io_equivalent(spec)
    if _is_package_io_block(spec):
        core_hint = (
            f"'{core_block}' with core_type='{core_type}'"
            if core_type
            else f"'{core_block}' with the matching core_type"
        )
        return (
            f"{prefix} block_type '{block_type}' is a package-specific "
            f"IO block. Prefer the core {core_hint} — it delegates to the same "
            f"package loader/saver and keeps one consistent GUI node."
        )
    if not core_type:
        return None
    direction = "save" if core_block == "save_data" else "load"
    if core_type not in covered(direction):
        return None
    return (
        f"{prefix} block_type '{block_type}' is a custom IO block for {core_type}, which the "
        f"core '{core_block}' block already handles. Prefer core '{core_block}' with "
        f"core_type='{core_type}' so the canvas keeps one consistent Load/Save node."
    )


def _core_io_steering_warnings(
    nodes: Any,
    registry: Any = None,
    type_registry: Any = None,
) -> list[str]:
    """Return non-blocking core-IO steering warnings for workflow *nodes*.

    Covers three agent mistakes:

    1. A package-specific IO block (``scistudio_blocks_*``) the core Load/Save
       block already covers.
    2. A custom (project drop-in or scaffolded) IO block whose data type the
       core Load/Save ``core_type`` enum covers with a registered format
       capability. A custom IO block for a type the core block cannot handle,
       or whose type cannot be determined, is legitimate and not flagged.
    3. A core ``load_data`` / ``save_data`` node with no ``core_type``.

    *nodes* may be pydantic node models, ``NodeDef`` dataclasses, or plain
    mappings. Unregistered block types are skipped (callers report those).
    Registries default to the active MCP context's.
    """
    # Development references: #1900, #2376.
    if registry is None or type_registry is None:
        try:
            context = get_context()
        except Exception:
            context = None
        registry = registry if registry is not None else getattr(context, "block_registry", None)
        type_registry = type_registry if type_registry is not None else getattr(context, "type_registry", None)
    if registry is None:
        return []
    try:
        specs = registry.all_specs()
    except Exception:  # pragma: no cover - defensive: registry not ready
        return []
    by_type_name = {spec.type_name: spec for spec in (specs or {}).values() if spec.type_name}

    cache: dict[str, frozenset[str]] = {}

    def covered(direction: str) -> frozenset[str]:
        if direction not in cache:
            cache[direction] = _core_io_covered_types(registry, type_registry, direction=direction)
        return cache[direction]

    warnings: list[str] = []
    for node in nodes or []:
        block_type = str(_node_field(node, "block_type") or "")
        spec = by_type_name.get(block_type)
        if spec is None and block_type not in _CORE_IO_BLOCK_TYPES:
            continue
        message = _core_io_node_warning(
            str(_node_field(node, "id") or ""),
            block_type,
            _node_field(node, "config"),
            spec,
            covered,
        )
        if message is not None:
            warnings.append(message)
    return warnings


def _scaffold_io_steering_warning(
    input_ports: dict[str, Any],
    output_ports: dict[str, Any],
    registry: Any = None,
    type_registry: Any = None,
) -> str | None:
    """Return a core-IO steering warning for an ``io`` block about to be scaffolded.

    The declared ports decide direction the way :func:`_core_io_equivalent`
    does (only input ports: saver; otherwise loader) and the first port type
    on that side is the data type. A type the core block covers yields a
    concrete redirect; a type it does not cover yields ``None`` (a custom IO
    block is legitimate there); an undeclared type yields a generic reminder
    to check the core block first.
    """
    # Development references: #2376.
    is_saver = bool(input_ports) and not output_ports
    core_block = "save_data" if is_saver else "load_data"
    side = input_ports if is_saver else output_ports
    core_type = next(
        (str(spec.get("type")) for spec in (side or {}).values() if isinstance(spec, dict) and spec.get("type")),
        None,
    )
    if core_type is None:
        return (
            f"Scaffolding an IO block: first check whether the core '{core_block}' block "
            f"with a core_type already handles this data (get_block_schema('{core_block}') "
            f"lists the valid core_type values). Prefer it over a custom IO block."
        )
    if registry is None or type_registry is None:
        try:
            context = get_context()
        except Exception:
            context = None
        registry = registry if registry is not None else getattr(context, "block_registry", None)
        type_registry = type_registry if type_registry is not None else getattr(context, "type_registry", None)
    direction = "save" if is_saver else "load"
    if core_type not in _core_io_covered_types(registry, type_registry, direction=direction):
        return None
    return (
        f"Scaffolding an IO block for {core_type}, which the core '{core_block}' block "
        f"already handles. Prefer core '{core_block}' with core_type='{core_type}' in the "
        f"workflow instead of a custom IO block."
    )


def _atomic_write_text(path: Path, text: str) -> int:
    """Write *text* to *path* via tempfile + rename. Returns bytes written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return len(text.encode("utf-8"))


def _diff_summary(old: str, new: str) -> str:
    """Compact diff summary used in INFO log + return envelope."""
    old_lines = old.splitlines() if old else []
    new_lines = new.splitlines()
    added = max(0, len(new_lines) - len(old_lines))
    removed = max(0, len(old_lines) - len(new_lines))
    return f"+{added}/-{removed} lines, {len(new.encode('utf-8'))} bytes"


def _looks_like_inline_yaml(s: str) -> bool:
    """Heuristic: starts with ``name:`` or contains ``nodes:`` ⇒ inline."""
    stripped = s.lstrip()
    if stripped.startswith(("name:", "workflow:", "id:", "version:")):
        return True
    return "nodes:" in s and "\n" in s


def _get_workflow_runtime() -> Any:
    """Locate a runtime that knows how to start workflows."""
    ctx = get_context()
    if not hasattr(ctx, "start_workflow"):
        raise RuntimeError(
            "Active MCPContext does not expose start_workflow(); run_workflow requires a full ApiRuntime."
        )
    return ctx


def _resolve_ai_block_run_dir() -> Path | None:
    """Locate the active AI Block run dir from MCP context or env var.

    Resolution order (first hit wins):

      1. ``MCPContext.ai_block_run_dir`` attribute, when present.
      2. ``SCISTUDIO_AI_BLOCK_RUN_DIR`` environment variable.

    Returns ``None`` when neither is configured.
    """
    try:
        ctx = get_context()
    except Exception:
        ctx = None
    if ctx is not None:
        run_dir = getattr(ctx, "ai_block_run_dir", None)
        if run_dir is not None:
            return Path(run_dir)
    raw = os.environ.get("SCISTUDIO_AI_BLOCK_RUN_DIR")
    if raw:
        candidate = Path(raw)
        if candidate.is_dir():
            return candidate
    return None


__all__ = [
    "_LOCK_TIMEOUT_SECONDS",
    "_atomic_write_text",
    "_core_io_steering_warnings",
    "_diff_summary",
    "_get_workflow_runtime",
    "_looks_like_inline_yaml",
    "_port_to_dict",
    "_render_port_type",
    "_resolve_ai_block_run_dir",
    "_spec_signature",
    "_spec_to_dict",
]
