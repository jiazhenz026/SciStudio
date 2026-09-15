"""MCP tools for block authoring helpers (5 tools)."""
# Maintainer context (kept outside generated API documentation):
# Category (b) MCP tools — block authoring helpers (5 tools).
#
# ADR-040 §3.1 FastMCP migration, I40a Phase 2a implementation.
#
# The 5 tools are:
#
# Read-class (2): ``read_block_source``, ``list_block_examples``.
# Write-class (3): ``scaffold_block``, ``reload_blocks``, ``run_block_tests``.
#
# Per ADR-040 §3.2a, ``scaffold_block`` is widened to accept
# ``input_ports`` + ``output_ports`` so the §3.2a ``warnings: list[str]``
# soft-validation can flag generic-``DataObject`` ports and unregistered
# type names.
# Development references: ADR-040.

from __future__ import annotations

import importlib
import inspect
import keyword
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, Field

from scistudio.ai.agent.mcp._context import _resolve_project_root, _safe_under, get_context, invoked_through_bridge
from scistudio.ai.agent.mcp._reload import broadcast_blocks_reloaded, refresh_context_registries
from scistudio.ai.agent.mcp.server import mcp
from scistudio.ai.agent.mcp.tools_workflow.read import list_blocks_called
from scistudio.ai.agent.mcp.tools_workspace import ToolRefusal, list_blocks_refusal
from scistudio.blocks._templates.render import PortStub, StarterSpec, render_starter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic result models.
# ---------------------------------------------------------------------------


class ReadBlockSourceResult(BaseModel):
    """Result envelope for ``read_block_source``."""

    path: str = Field(description="Absolute filesystem path of the block's source file.")
    source: str = Field(description="Full Python source text of the file.")
    language: str = Field(default="python", description="Source language (always 'python' today).")


class BlockExampleEntry(BaseModel):
    """One entry in the ``list_block_examples`` result list."""

    name: str = Field(description="Importable module path of the example block.")
    path: str = Field(description="Absolute filesystem path of the example module.")
    description: str = Field(description="First line of the module docstring.")


class ScaffoldBlockResult(BaseModel):
    """Result envelope for ``scaffold_block``.

    Includes ``warnings: list[str]`` for soft validation (generic-DataObject
    port detection, unregistered or unimportable type detection, ports the
    chosen base class ignores).
    """

    # Development references: ADR-040.

    path: str = Field(description="Absolute filesystem path of the scaffolded block file.")
    bytes_written: int = Field(description="Number of bytes written to disk.")
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Soft advisory notes the agent should review in its next turn. "
            "Per ADR-040 §3.2a: generic-DataObject port usage or unregistered "
            "type names trigger warnings here without blocking the scaffold. "
            "An io-category scaffold whose data type the core load_data/save_data "
            "block covers also warns to use that core block with core_type."
        ),
    )
    next_step: str = Field(
        default=(
            "The file already imports and registers. Fill in the part marked '>>> EDIT THIS <<<' "
            "(run(), process_item(), load_file()/save_file(), or app_command), replace every "
            "'Describe ...' label, then call mcp__scistudio__reload_blocks to register it. If "
            "warnings flagged DataObject ports or 'fill in' types, narrow them to concrete types "
            "from mcp__scistudio__list_types."
        ),
        description="Suggested next MCP call after scaffolding.",
    )
    status: str = Field(
        default="ok",
        description=(
            "'ok' when the file was written; 'refused' when a server-side rule stopped the "
            "scaffold (nothing was written; see refusal)."
        ),
    )
    refusal: ToolRefusal | None = Field(
        default=None,
        description="Why the scaffold was refused, and which tool to call instead.",
    )


class ReloadBlocksResult(BaseModel):
    """Result envelope for ``reload_blocks``."""

    reloaded: int = Field(description="Total number of block types after reload.")
    added: list[str] = Field(default_factory=list, description="Newly added block type names.")
    removed: list[str] = Field(default_factory=list, description="Removed block type names.")
    next_step: str = Field(
        default=(
            "Call mcp__scistudio__list_blocks to confirm the new block is registered, "
            "then mcp__scistudio__run_block_tests if a test file exists."
        ),
        description="Suggested next MCP call after a hot-reload.",
    )


class RunBlockTestsResult(BaseModel):
    """Result envelope for ``run_block_tests``."""

    returncode: int = Field(description="Pytest process exit code, or -1 if test file not found.")
    stdout: str = Field(default="", description="Captured stdout from pytest.")
    stderr: str = Field(default="", description="Captured stderr from pytest.")
    test_path: str = Field(description="Resolved path that was searched.")
    found: bool = Field(description="Whether the test file was found.")
    next_step: str = Field(
        default=(
            "If returncode != 0, read the stderr/stdout for failure details and fix "
            "the block source. If found=False, create tests/blocks/test_<name>.py first."
        ),
        description="Suggested next action.",
    )


# ---------------------------------------------------------------------------
# (b.1) read_block_source
# ---------------------------------------------------------------------------


@mcp.tool(name="read_block_source", tags={"category:authoring", "read"})
async def read_block_source(
    type_name: str = Field(description="Registered block type name (from list_blocks)."),
) -> ReadBlockSourceResult:
    """Return the Python source file backing a registered block type.

    Use when:
      You want to read how an existing block is implemented before
        writing a new one (reuse-first rule).
      You're diagnosing a block-level error and need to see the source.

    Do NOT use to:
      Edit a block — use ``Edit``/``Write`` on the path returned here
        (the file is in the project's ``blocks/`` dir, which the
        protect_workflow_yaml hook does NOT cover; direct edits are fine).
      Discover example patterns — use ``list_block_examples``.

    Raises ``KeyError`` if the type is not registered.
    """
    # Development references: #875.
    ctx = get_context()
    spec = ctx.block_registry.get_spec(type_name)
    if spec is None:
        raise KeyError(f"Block type '{type_name}' is not registered")

    if getattr(spec, "file_path", None):
        path = Path(str(spec.file_path))
    else:
        try:
            module = ctx.block_registry.instantiate(type_name).__class__.__module__
            mod = sys.modules.get(module)
            if mod is None:
                import importlib

                mod = importlib.import_module(module)
            path = Path(inspect.getfile(mod))
        except Exception as exc:
            raise RuntimeError(f"Could not resolve source file for '{type_name}': {exc}") from exc

    if not path.exists():
        raise FileNotFoundError(f"Block source file not found: {path}")

    return ReadBlockSourceResult(
        path=str(path),
        source=path.read_text(encoding="utf-8"),
        language="python",
    )


# ---------------------------------------------------------------------------
# (b.2) list_block_examples
# ---------------------------------------------------------------------------

_EXAMPLE_CURATION: dict[str, list[str]] = {
    "io": ["scistudio.blocks.io.loaders.load_data", "scistudio.blocks.io.savers.save_data"],
    "process": [
        "scistudio.blocks.process.builtins.merge",
        "scistudio.blocks.process.builtins.split",
        "scistudio.blocks.process.builtins.data_router",
    ],
    "code": ["scistudio.blocks.code"],
    "app": ["scistudio.blocks.app"],
    "ai": ["scistudio.blocks.ai.ai_block"],
    "subworkflow": ["scistudio.blocks.subworkflow.subworkflow_block"],
}


@mcp.tool(name="list_block_examples", tags={"category:authoring", "read"})
async def list_block_examples(
    category: str = Field(description="One of: io, process, code, app, ai, subworkflow."),
) -> list[BlockExampleEntry]:
    """List curated example blocks for a category.

    Use when:
      - You're authoring a new block and want pattern references.
      - You need to see how a specific category structures its
        ``run()`` method, ports, and config_schema.

    Do NOT use to:
      - List all registered block types — use ``list_blocks``.

    Raises ``KeyError`` if the category is not recognised.
    """
    if category not in _EXAMPLE_CURATION:
        raise KeyError(f"Unknown block category '{category}'. Known: {sorted(_EXAMPLE_CURATION)}")
    import importlib

    out: list[BlockExampleEntry] = []
    for mod_path in _EXAMPLE_CURATION[category]:
        try:
            mod = importlib.import_module(mod_path)
            path = Path(inspect.getfile(mod))
            description = (mod.__doc__ or "").strip().split("\n", 1)[0]
        except Exception as exc:  # pragma: no cover
            logger.warning("list_block_examples: could not import %s: %s", mod_path, exc)
            continue
        out.append(BlockExampleEntry(name=mod_path, path=str(path), description=description))
    return out


# ---------------------------------------------------------------------------
# (b.3) scaffold_block  (write-class)
#
# ADR-040 §3.2a widened the signature to include input_ports + output_ports
# so the §3.2a soft-validation `warnings` logic has port specs to inspect.
# #2384 renders the per-kind starter templates in ``scistudio.blocks._templates``
# (the files GET /api/blocks/template serves) instead of a private template.
# ---------------------------------------------------------------------------

_BLOCK_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_BLOCK_NAME_MAX = 64

# category -> template kind; "io" picks io_load or io_save from the ports.
_SCAFFOLD_KINDS: dict[str, str] = {"block": "basic", "process": "process", "io": "io_load", "app": "app"}

_SCAFFOLD_REFUSALS: dict[str, ToolRefusal] = {
    "code": ToolRefusal(
        code="code_block_not_subclassed",
        message=(
            "A Code Block is not written as a block class: the built-in 'code_block' runs a project "
            "script as a step. Write the script under the project (e.g. scripts/<name>.py) so it reads "
            "its inputs from $SCISTUDIO_INPUTS_DIR/<port>/ and writes results to "
            "$SCISTUDIO_OUTPUTS_DIR/<port>/, then add a 'code_block' node whose config sets script_path "
            "and the declared inputs/outputs (get_block_schema('code_block') lists the fields)."
        ),
        use_instead=["get_block_schema", "edit_workflow"],
    ),
    "ai": ToolRefusal(
        code="ai_block_not_authored",
        message=(
            "AIBlock is not an authoring surface. To put an AI step in a workflow, add the built-in "
            "AI Agent block as a node and configure its prompt and ports."
        ),
        use_instead=["get_block_schema", "edit_workflow"],
    ),
    "subworkflow": ToolRefusal(
        code="subworkflow_block_not_authored",
        message=(
            "SubWorkflowBlock is not an authoring surface. To reuse a workflow inside another, add the "
            "built-in sub-workflow block as a node and point it at the child workflow."
        ),
        use_instead=["get_block_schema", "edit_workflow"],
    ),
}


def _snake_to_camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_") if part)


def _snake_to_label(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("_") if part)


def _validate_block_name(name: str) -> None:
    """Reject a ``name`` that is not a snake_case module name (#2037)."""
    if (
        not isinstance(name, str)
        or len(name) > _BLOCK_NAME_MAX
        or not _BLOCK_NAME_RE.fullmatch(name)
        or keyword.iskeyword(name)
    ):
        raise ValueError(
            f"Invalid block name {name!r}: use snake_case letters, digits and underscores, starting with "
            f"a lowercase letter, at most {_BLOCK_NAME_MAX} characters, and not a Python keyword "
            "(e.g. 'gaussian_smooth'). The file is written to blocks/<name>.py."
        )


def _normalise_port_specs(spec_map: Any, direction: str) -> dict[str, dict[str, Any]]:
    """Check the ``{port_name: {'type': ..., 'description': ...}}`` shape."""
    if not spec_map:
        return {}
    if not isinstance(spec_map, dict):
        raise ValueError(f"{direction}_ports must be an object mapping port name to its spec")
    out: dict[str, dict[str, Any]] = {}
    for port_name, spec in spec_map.items():
        if not isinstance(port_name, str) or not port_name.strip():
            raise ValueError(f"{direction}_ports has an empty port name")
        if spec is None:
            spec = {}
        if not isinstance(spec, dict):
            raise ValueError(f"{direction} port {port_name!r}: spec must be an object like {{'type': 'Array'}}")
        type_name = spec.get("type", "")
        if not isinstance(type_name, str):
            raise ValueError(f"{direction} port {port_name!r}: 'type' must be a type name string")
        description = spec.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"{direction} port {port_name!r}: 'description' must be a string")
        out[port_name] = spec
    return out


@dataclass
class _TypeImports:
    """Imports a rendered starter needs for its port types."""

    core: set[str] = dc_field(default_factory=set)
    lines: list[str] = dc_field(default_factory=list)
    unresolved: dict[str, str] = dc_field(default_factory=dict)


def _public_core_type(type_name: str) -> type | None:
    """Return the core data type exported from ``scistudio.core.types`` as *type_name*."""
    from scistudio.core import types as core_types

    if type_name not in core_types.__all__:
        return None
    candidate = getattr(core_types, type_name, None)
    if isinstance(candidate, type) and issubclass(candidate, core_types.DataObject):
        return candidate
    return None


def _package_import_line(ctx: Any, type_name: str) -> str | None:
    """Return ``from <package> import <Type>`` when the package exports the type at its root.

    Package types are public only at their distribution's top level
    (``_agent_reference/public-api.md``); a type reachable only through a deep
    or underscore module gets no import line. A project or user-library drop-in
    type is imported by its file stem.
    """
    type_registry = getattr(ctx, "type_registry", None)
    try:
        spec = type_registry.all_types().get(type_name) if type_registry is not None else None
    except Exception:
        spec = None
    if spec is None:
        return None
    class_name = str(getattr(spec, "class_name", "") or type_name)
    if getattr(spec, "is_dropin", False):
        # ADR-053 FR-012: a drop-in block imports a drop-in type by its file stem
        # (``types/spectrum.py`` -> ``from spectrum import SpectrumData``).
        stem = Path(str(getattr(spec, "file_path", "") or "")).stem
        if stem.isidentifier() and class_name.isidentifier():
            return f"from {stem} import {class_name}"
        return None
    module_path = str(getattr(spec, "module_path", "") or "")
    root = str(getattr(spec, "package_root", "") or "") or module_path.split(".")[0]
    if not root or root == "scistudio" or not root.isidentifier() or not class_name.isidentifier():
        return None
    try:
        package = importlib.import_module(root)
        exported = getattr(package, class_name, None)
        defined = getattr(importlib.import_module(module_path), class_name, None) if module_path else exported
    except Exception:
        return None
    if exported is None or exported is not defined:
        return None
    return f"from {root} import {class_name}"


def _resolve_port_type(ctx: Any, type_name: str, imports: _TypeImports) -> tuple[str, str]:
    """Return ``(symbol to render, trailing note)`` for a declared port type.

    A type with a public import is rendered as itself and imported. Anything
    else is rendered as ``DataObject`` with a note naming the intended type, so
    the scaffolded file imports and registers unchanged.
    """
    if not type_name or type_name == "DataObject":
        imports.core.add("DataObject")
        return "DataObject", ""
    if type_name.isidentifier() and _public_core_type(type_name) is not None:
        imports.core.add(type_name)
        return type_name, ""
    line = _package_import_line(ctx, type_name) if type_name.isidentifier() else None
    if line is not None:
        if line not in imports.lines:
            imports.lines.append(line)
        return line.rsplit(" ", 1)[-1], ""
    imports.core.add("DataObject")
    if type_name not in imports.unresolved:
        imports.unresolved[type_name] = (
            f"# from <package> import {type_name}  # fill in: import {type_name} from its package's "
            "public root, then use it in place of DataObject"
        )
    return "DataObject", f"fill in: {type_name}"


def _port_stubs(
    ctx: Any, spec_map: dict[str, dict[str, Any]], direction: str, imports: _TypeImports
) -> tuple[PortStub, ...]:
    stubs = []
    for port_name, spec in spec_map.items():
        symbol, note = _resolve_port_type(ctx, spec.get("type", "") or "", imports)
        description = (spec.get("description") or "").strip() or (
            "Describe what flows into this port." if direction == "input" else "Describe what this port produces."
        )
        required = spec.get("required", True) is not False
        stubs.append(PortStub(name=port_name, type_name=symbol, description=description, required=required, note=note))
    return tuple(stubs)


def _type_registry_has(ctx: Any, type_name: str) -> bool:
    """Best-effort 'is this type registered?' check."""
    type_registry = getattr(ctx, "type_registry", None)
    if type_registry is None:
        return False
    has_fn = getattr(type_registry, "has", None)
    if callable(has_fn):
        try:
            return bool(has_fn(type_name))
        except Exception:
            pass
    try:
        return type_name in type_registry.all_types()
    except Exception:
        return False


@mcp.tool(name="scaffold_block", tags={"category:authoring", "write"})
async def scaffold_block(
    name: str = Field(
        description=(
            "Block module name in snake_case (lowercase letters, digits, underscores; starts with a letter). "
            "The file is written to blocks/<name>.py; the class is its CamelCase form."
        ),
    ),
    category: str = Field(
        description=(
            "Base class to start from: 'block' (Block, write run()), 'process' (ProcessBlock, write "
            "process_item()), 'io' (SimpleLoader, or SimpleSaver when only input_ports are given), "
            "'app' (AppBlock, declare the external command). 'code', 'ai' and 'subworkflow' are refused: "
            "those steps use built-in blocks configured as workflow nodes."
        ),
    ),
    input_ports: Annotated[
        dict[str, dict[str, Any]] | None,
        Field(
            description=(
                "Per-port input specs: {port_name: {'type': '<TypeName>', 'description': '...'}}. "
                "Each inner dict requires at least 'type' (string); 'description' is optional. "
                "ADR-040 §3.2a: 'DataObject' triggers a soft warning unless block is a generic "
                "SubWorkflowBlock / AppBlock. None is normalised to {} inside the body."
            ),
        ),
    ] = None,
    output_ports: Annotated[
        dict[str, dict[str, Any]] | None,
        Field(
            description=(
                "Per-port output specs: {port_name: {'type': '<TypeName>', 'description': '...'}}. "
                "Same shape and §3.2a soft-validation as input_ports. None is normalised to {} inside the body."
            ),
        ),
    ] = None,
    description: Annotated[
        str | None,
        Field(description="Optional one-line description shown in the palette and node header."),
    ] = None,
) -> ScaffoldBlockResult:
    """Write a starter block module for the chosen base class under ``blocks/``.

    The file comes from the same per-kind starter templates the GUI "New
    custom block" action uses, filled in with the class name, a readable
    ``name`` label, the declared ports (each with a description), labelled
    parameters, canonical ``scistudio.*`` root imports, and an import for every
    declared port type. It imports and registers as written, so
    ``reload_blocks`` picks it up before any edit.

    Use when:
      You've called ``list_blocks`` and confirmed no existing block
        matches your I/O contract (the  block-reuse rule).
      You're starting a new custom block under the project's
        ``blocks/`` directory.

    Do NOT use to:
      Modify an existing block — read its source via
        ``read_block_source`` and use ``Edit``/``Write`` directly.
      Wrap a script (Code Block), add an AI step, or nest a workflow —
        those categories are refused with what to do instead.
      Bypass the block-reuse rule — the
        enforce_list_blocks_before_block_write hook will
        block this tool call unless ``list_blocks`` was called earlier
        in the session.

    a, the result envelope's ``warnings`` field flags:
      Ports declared with the generic ``DataObject`` type.
      Ports referencing type names not registered in the active
        ``TypeRegistry``, or with no public import (rendered as
        ``DataObject`` with a note naming the intended type).
      Declared ports the chosen base class does not use.
      A ``category='io'`` scaffold when the core ``load_data`` / ``save_data`` block
        with a ``core_type`` already handles the declared data type (or the
        type is not declared yet).

    Warnings are advisory; the file is still written. Raises ``ValueError``
    for an invalid ``name``, an unknown ``category``, or malformed port specs,
    and ``FileExistsError`` if the target path already exists.
    """
    # Development references: #875, ADR-040, #2037, #2384.
    # ADR-055 Spec 2 (#2279) hook parity: a WebMCP host runs no provisioned
    # hooks, so the enforce_list_blocks_before_block_write rule is applied
    # server-side for bridge calls. Local-transport calls keep relying on the
    # host's hook, unchanged.
    if invoked_through_bridge() and not list_blocks_called():
        logger.info("scaffold_block: outcome=refused code=list_blocks_required transport=webmcp")
        return ScaffoldBlockResult(
            path="",
            bytes_written=0,
            status="refused",
            refusal=list_blocks_refusal(),
            next_step="Call list_blocks to confirm no existing block matches your I/O contract, then retry scaffold_block.",
        )

    if category in _SCAFFOLD_REFUSALS:
        refusal = _SCAFFOLD_REFUSALS[category]
        logger.info("scaffold_block: outcome=refused code=%s", refusal.code)
        return ScaffoldBlockResult(
            path="",
            bytes_written=0,
            status="refused",
            refusal=refusal,
            next_step=refusal.message,
        )
    if category not in _SCAFFOLD_KINDS:
        raise ValueError(
            f"Unknown block category {category!r}. Scaffold one of: {sorted(_SCAFFOLD_KINDS)}. "
            f"Refused (use built-in blocks instead): {sorted(_SCAFFOLD_REFUSALS)}."
        )
    _validate_block_name(name)
    inputs_norm = _normalise_port_specs(input_ports, "input")
    outputs_norm = _normalise_port_specs(output_ports, "output")

    ctx = get_context()
    root = _resolve_project_root(ctx)
    blocks_dir = root / "blocks"
    blocks_dir.mkdir(parents=True, exist_ok=True)
    # #2037: confine the write to blocks/ even though the name is already validated.
    target = _safe_under(blocks_dir, Path(f"{name}.py"))
    if target.parent != blocks_dir.resolve():
        raise PermissionError(f"{name!r} does not resolve directly inside {blocks_dir}")
    if target.exists():
        raise FileExistsError(f"{target} already exists")

    # ADR-040 §3.2a soft validation.
    # TODO(#1016): hard BlockRegistry-level rejection of generic DataObject
    #   ports + unregistered type names. Out of scope per ADR-040 §3.2a
    #   (Layer 4 only here). Followup: https://github.com/zjzcpj/SciStudio/issues/1016.
    warnings_list: list[str] = []
    for direction, spec_map in (("input", inputs_norm), ("output", outputs_norm)):
        for port_name, spec in spec_map.items():
            type_name = spec.get("type", "")
            if type_name == "DataObject":
                warnings_list.append(
                    f"{direction} port {port_name!r} uses generic DataObject. "
                    "Preview and edge-time type checking will degrade. "
                    "Confirm intentional (e.g. SubWorkflowBlock or generic AppBlock); "
                    "otherwise pick a concrete type from mcp__scistudio__list_types()."
                )
            elif type_name and not _type_registry_has(ctx, type_name):
                warnings_list.append(
                    f"{direction} port {port_name!r} references unregistered type "
                    f"{type_name!r}. Either pick from list_types() or register the new "
                    "type via the scistudio.types entry-point in this plugin."
                )

    # #2376: steer away from a custom IO block the core Load/Save block covers.
    if category == "io":
        from scistudio.ai.agent.mcp.tools_workflow._helpers import _scaffold_io_steering_warning

        io_warning = _scaffold_io_steering_warning(
            inputs_norm,
            outputs_norm,
            registry=getattr(ctx, "block_registry", None),
            type_registry=getattr(ctx, "type_registry", None),
        )
        if io_warning is not None:
            warnings_list.append(io_warning)

    kind = _SCAFFOLD_KINDS[category]
    render_inputs: dict[str, dict[str, Any]] | None = inputs_norm or None
    render_outputs: dict[str, dict[str, Any]] | None = outputs_norm or None
    if category == "io":
        # Same direction rule as the core-IO steering warning (#2376): only
        # input ports -> saver; otherwise loader.
        is_saver = bool(inputs_norm) and not outputs_norm
        kind = "io_save" if is_saver else "io_load"
        data_side, other_side = (inputs_norm, None) if is_saver else (outputs_norm, inputs_norm)
        if other_side:
            warnings_list.append(
                "A loader reads its 'path' parameter and has no data input ports; input_ports were ignored. "
                "Pass only input_ports to scaffold a saver instead."
            )
        if len(data_side) > 1:
            warnings_list.append(
                f"A {'saver writes one input' if is_saver else 'loader fills one output'} port; "
                f"only {next(iter(data_side))!r} was used. Use category='block' for several ports."
            )
            data_side = dict([next(iter(data_side.items()))])
        render_inputs, render_outputs = (data_side or None, None) if is_saver else (None, data_side or None)
    elif category == "process" and (len(inputs_norm) > 1 or len(outputs_norm) > 1):
        warnings_list.append(
            "ProcessBlock reads only the first input port and fills only the first output port. "
            "Override run() for several ports, or use category='block'."
        )

    imports = _TypeImports()
    input_stubs = _port_stubs(ctx, render_inputs, "input", imports) if render_inputs is not None else None
    output_stubs = _port_stubs(ctx, render_outputs, "output", imports) if render_outputs is not None else None
    for type_name in imports.unresolved:
        warnings_list.append(
            f"Type {type_name!r} has no public import this tool could find, so its port uses DataObject "
            "with a 'fill in' note. Import the type from its package's public root and put it back."
        )

    from scistudio.core import types as core_types

    class_name = _snake_to_camel(name)
    starter = StarterSpec(
        class_name=class_name,
        label=_snake_to_label(name),
        description=" ".join((description or "").split()) or "Describe what this block does.",
        input_ports=input_stubs,
        output_ports=output_stubs,
        core_types=frozenset(imports.core),
        extra_import_lines=(*imports.lines, *imports.unresolved.values()),
        extension=f".{name}" if kind in {"io_load", "io_save"} else None,
        format_id=name if kind in {"io_load", "io_save"} else None,
        known_types=frozenset(core_types.__all__),
    )
    text = render_starter(kind, starter)
    target.write_text(text, encoding="utf-8")
    bytes_written = len(text.encode("utf-8"))
    logger.info("scaffold_block: created %s (category=%s kind=%s)", target, category, kind)
    return ScaffoldBlockResult(
        path=str(target),
        bytes_written=bytes_written,
        warnings=warnings_list,
    )


# ---------------------------------------------------------------------------
# (b.4) reload_blocks  (write-class)
# ---------------------------------------------------------------------------


@mcp.tool(name="reload_blocks", tags={"category:authoring", "write"})
async def reload_blocks() -> ReloadBlocksResult:
    """Hot-reload the block and data-type registries.

    Use after editing or adding a custom block or drop-in data type to make it
    available without restarting the backend. Newly installed entry-point blocks
    require a backend restart.

    Rebuild through :mod:`scistudio.ai.agent.mcp._reload` and broadcast the update
    so connected clients refresh their palettes and schemas.
    """
    # Development references: #9, ADR-053, FR-059, FR-062.
    ctx = get_context()
    added, removed = refresh_context_registries(ctx)
    logger.info("reload_blocks: added=%s removed=%s", added, removed)
    await broadcast_blocks_reloaded(ctx, added=added, removed=removed)
    return ReloadBlocksResult(reloaded=len(ctx.block_registry.all_specs()), added=added, removed=removed)


# ---------------------------------------------------------------------------
# (b.5) run_block_tests  (write-class — invokes pytest subprocess)
# ---------------------------------------------------------------------------


@mcp.tool(name="run_block_tests", tags={"category:authoring", "write"})
async def run_block_tests(
    type_name: str = Field(description="Block type name. Test file is tests/blocks/test_<lower>.py."),
) -> RunBlockTestsResult:
    """Run pytest against the test module associated with a block.

    Use when:
      - You've edited a block and want to confirm tests still pass.
      - You're authoring a new block and want continuous feedback.

    Do NOT use to:
      - Run the full project test suite — this tool targets one block's
        tests only.
    """
    ctx = get_context()
    root = _resolve_project_root(ctx)
    test_path = root / "tests" / "blocks" / f"test_{type_name.lower()}.py"
    found = test_path.exists()
    if not found:
        return RunBlockTestsResult(
            returncode=-1,
            stdout="",
            stderr=f"test file not found: {test_path}",
            test_path=str(test_path),
            found=False,
        )
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_path), "--tb=short", "-q"],
        capture_output=True,
        text=True,
        cwd=str(root),
        timeout=300,
        check=False,
    )
    logger.info("run_block_tests: %s rc=%d", test_path, proc.returncode)
    return RunBlockTestsResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        test_path=str(test_path),
        found=True,
    )
