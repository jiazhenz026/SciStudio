"""Category (b) MCP tools — block authoring helpers (5 tools).

ADR-040 §3.1 FastMCP migration. All tool functions are decorated with
``@mcp.tool(name=...)`` and declare Pydantic result models.

The 5 tools are:

Read-class (2): ``read_block_source``, ``list_block_examples``.
Write-class (3): ``scaffold_block``, ``reload_blocks``, ``run_block_tests``.

Per ADR-040 §3.2a, ``scaffold_block`` is widened from the ADR-033-era
``(name, category)`` signature to ``(name, category, input_ports,
output_ports)`` so the §3.2a ``warnings: list[str]`` soft-validation
logic has port specs to inspect. See manifest §8.6 for the design
rationale.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, Field

from scieasy.ai.agent.mcp._context import _resolve_project_root, get_context
from scieasy.ai.agent.mcp.server import mcp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic result models — ADR-040 §3.1 typed envelopes.
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

    Per ADR-040 §3.2a, includes ``warnings: list[str]`` for soft
    validation (generic-DataObject port detection, unregistered type
    detection).
    """

    path: str = Field(description="Absolute filesystem path of the scaffolded block file.")
    bytes_written: int = Field(description="Number of bytes written to disk.")
    created: bool = Field(default=True, description="Whether the file was newly created.")
    template_used: str = Field(
        default="scieasy.ai.agent.mcp.tools_authoring:_SCAFFOLD_TEMPLATE",
        description="Identifier of the template that produced the file.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Soft advisory notes the agent should review in its next turn. "
            "Per ADR-040 §3.2a: generic-DataObject port usage or unregistered "
            "type names trigger warnings here without blocking the scaffold."
        ),
    )
    next_step: str = Field(
        default=(
            "Edit the scaffolded file to implement the block's run() method, then call "
            "mcp__scieasy__reload_blocks to register it. If warnings list flagged generic "
            "DataObject ports, narrow them to concrete types from mcp__scieasy__list_types."
        ),
        description="Suggested next MCP call after scaffolding.",
    )


class ReloadBlocksResult(BaseModel):
    """Result envelope for ``reload_blocks``."""

    reloaded: int = Field(description="Total number of block types after reload.")
    added: list[str] = Field(default_factory=list, description="Newly added block type names.")
    removed: list[str] = Field(default_factory=list, description="Removed block type names.")
    next_step: str = Field(
        default=(
            "Call mcp__scieasy__list_blocks to confirm the new block is registered, "
            "then mcp__scieasy__run_block_tests if a test file exists."
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
# Helpers.
# ---------------------------------------------------------------------------


_EXAMPLE_CURATION: dict[str, list[str]] = {
    "io": ["scieasy.blocks.io.loaders.load_data", "scieasy.blocks.io.savers.save_data"],
    "process": [
        "scieasy.blocks.process.builtins.merge",
        "scieasy.blocks.process.builtins.split",
        "scieasy.blocks.process.builtins.data_router",
    ],
    "code": ["scieasy.blocks.code"],
    "app": ["scieasy.blocks.app"],
    "ai": ["scieasy.blocks.ai.ai_block"],
    "subworkflow": ["scieasy.blocks.subworkflow.subworkflow_block"],
}


_SCAFFOLD_TEMPLATE = '''"""Block scaffolded by SciEasy MCP scaffold_block.

Edit this file then call ``reload_blocks`` to register the change.
"""

from __future__ import annotations

from typing import Any

from scieasy.blocks.base.block import Block
from scieasy.blocks.base.ports import InputPort, OutputPort


class {class_name}(Block):
    """TODO: describe what this block does."""

    name = "{class_name}"
    description = "TODO: one-line description"
    version = "0.1.0"

    input_ports = [
{input_ports_lines}
    ]
    output_ports = [
{output_ports_lines}
    ]
    config_schema: dict[str, Any] = {{
        "type": "object",
        "properties": {{}},
        "required": [],
    }}

    def run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """TODO: implement."""
        raise NotImplementedError
'''


def _snake_to_camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_") if part)


def _render_port_lines(ports: dict[str, dict[str, Any]] | None, port_cls: str) -> str:
    """Render port specs as Python source lines for the scaffold template."""
    if not ports:
        return f"        # {port_cls}(name='in', type=DataObject, required=True),"
    lines: list[str] = []
    for port_name, spec in ports.items():
        type_name = spec.get("type", "DataObject")
        required = bool(spec.get("required", False))
        lines.append(f"        {port_cls}(name={port_name!r}, type={type_name}, required={required!r}),")
    return "\n".join(lines)


def _type_registered(ctx: Any, type_name: str) -> bool:
    """Return True if ``type_name`` appears in the active TypeRegistry."""
    if type_name == "DataObject":
        # Root of the hierarchy — always considered registered for the
        # purposes of soft validation (the §3.2a warning fires on
        # DataObject for a different reason).
        return True
    type_registry = getattr(ctx, "type_registry", None)
    if type_registry is None:
        return False
    has = getattr(type_registry, "has", None)
    if callable(has):
        try:
            return bool(has(type_name))
        except Exception:  # pragma: no cover - defensive
            pass
    all_types = getattr(type_registry, "all_types", None)
    if callable(all_types):
        try:
            return type_name in all_types()
        except Exception:  # pragma: no cover - defensive
            pass
    return False


# ---------------------------------------------------------------------------
# (b.1) read_block_source
# ---------------------------------------------------------------------------


@mcp.tool(name="read_block_source")
async def read_block_source(
    type_name: str = Field(description="Registered block type name (from list_blocks)."),
) -> ReadBlockSourceResult:
    """Return the Python source file backing a registered block type.

    Use when:
      - You want to read how an existing block is implemented before
        writing a new one (#875 reuse-first rule).
      - You're diagnosing a block-level error and need to see the source.

    Do NOT use to:
      - Edit a block — use ``Edit``/``Write`` on the path returned here.
      - Discover example patterns — use ``list_block_examples``.

    Raises ``KeyError`` if the type is not registered.
    """
    ctx = get_context()
    spec = ctx.block_registry.get_spec(type_name)
    if spec is None:
        raise KeyError(f"Block type '{type_name}' is not registered")

    if spec.file_path:
        path = Path(spec.file_path)
    else:
        try:
            module = ctx.block_registry.instantiate(type_name).__class__.__module__
            mod = sys.modules.get(module)
            if mod is None:
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


@mcp.tool(name="list_block_examples")
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

    out: list[BlockExampleEntry] = []
    for mod_path in _EXAMPLE_CURATION[category]:
        try:
            mod = importlib.import_module(mod_path)
            path = Path(inspect.getfile(mod))
            description = (mod.__doc__ or "").strip().split("\n", 1)[0]
        except Exception as exc:  # pragma: no cover - rare import failure
            logger.warning("list_block_examples: could not import %s: %s", mod_path, exc)
            continue
        out.append(BlockExampleEntry(name=mod_path, path=str(path), description=description))
    return out


# ---------------------------------------------------------------------------
# (b.3) scaffold_block  (write-class, §3.2a)
# ---------------------------------------------------------------------------


@mcp.tool(name="scaffold_block")
async def scaffold_block(
    name: str = Field(description="Block name in snake_case; the file will be blocks/<name>.py."),
    category: str = Field(description="One of: io, process, code, app, ai, subworkflow."),
    input_ports: Annotated[
        dict[str, dict[str, Any]] | None,
        Field(
            description=(
                "Per-port input specs: {port_name: {'type': '<TypeName>', 'description': '...'}}. "
                "Each inner dict requires 'type' (string); 'description' is optional. "
                "ADR-040 §3.2a: 'DataObject' triggers a soft warning unless block is generic. "
                "None is normalised to {} inside the body."
            ),
        ),
    ] = None,
    output_ports: Annotated[
        dict[str, dict[str, Any]] | None,
        Field(
            description=(
                "Per-port output specs: {port_name: {'type': '<TypeName>', 'description': '...'}}. "
                "Same shape and §3.2a soft-validation as input_ports."
            ),
        ),
    ] = None,
) -> ScaffoldBlockResult:
    """Render a new block module from the project's block templates.

    Use when:
      - You've called ``list_blocks`` and confirmed no existing block
        matches your I/O contract (the #875 block-reuse rule).
      - You're starting a new custom block under the project's
        ``blocks/`` directory.

    Do NOT use to:
      - Modify an existing block — read its source via
        ``read_block_source`` and use ``Edit``/``Write`` directly.
      - Bypass the block-reuse rule — the
        enforce_list_blocks_before_block_write hook (ADR-040 §3.6) will
        block this tool call unless ``list_blocks`` was called earlier
        in the session.

    Per ADR-040 §3.2a, the result envelope's ``warnings`` field flags:
      - Ports declared with the generic ``DataObject`` type (preview
        rendering and edge-time type-checking degrade — confirm
        intentional, otherwise pick a concrete type from
        ``list_types()``).
      - Ports referencing type names not registered in the active
        ``TypeRegistry``.

    Both warnings are advisory; the file is still written. Raises
    ``FileExistsError`` if the target path already exists.
    """
    ctx = get_context()
    root = _resolve_project_root(ctx)
    blocks_dir = root / "blocks"
    blocks_dir.mkdir(parents=True, exist_ok=True)
    target = blocks_dir / f"{name}.py"
    if target.exists():
        raise FileExistsError(f"{target} already exists")

    inputs_norm: dict[str, dict[str, Any]] = dict(input_ports or {})
    outputs_norm: dict[str, dict[str, Any]] = dict(output_ports or {})

    # ADR-040 §3.2a soft-validation.
    # TODO(#1016): the soft-validation here is the L4 layer; the L5
    # PostToolUse hook (enforce_concrete_port_types.py per ADR-040 §3.6)
    # is the second-layer defense for the Edit/Write bypass path. Hard
    # BlockRegistry-level rejection (the L7 escalation) is deferred to a
    # future ADR per ADR-040 §3.10.
    warnings: list[str] = []
    is_generic_block = category in {"subworkflow", "app"}
    for direction, ports in (("input", inputs_norm), ("output", outputs_norm)):
        for port_name, spec in ports.items():
            type_name = str(spec.get("type", ""))
            if type_name == "DataObject" and not is_generic_block:
                warnings.append(
                    f"{direction} port '{port_name}' uses generic DataObject. "
                    "Preview and edge-time type checking will degrade. Confirm "
                    "intentional (e.g. SubWorkflowBlock or generic AppBlock); "
                    "otherwise pick a concrete type from mcp__scieasy__list_types()."
                )
            elif type_name and not _type_registered(ctx, type_name):
                warnings.append(
                    f"{direction} port '{port_name}' references unregistered type "
                    f"'{type_name}'. Either pick from mcp__scieasy__list_types() or "
                    "register the new type via the scieasy.types entry-point in "
                    "this plugin."
                )

    class_name = _snake_to_camel(name) or "MyBlock"
    text = _SCAFFOLD_TEMPLATE.format(
        class_name=class_name,
        input_ports_lines=_render_port_lines(inputs_norm, "InputPort"),
        output_ports_lines=_render_port_lines(outputs_norm, "OutputPort"),
    )
    target.write_text(text, encoding="utf-8")
    bytes_written = len(text.encode("utf-8"))
    logger.info(
        "scaffold_block: created %s (category=%s, warnings=%d)",
        target,
        category,
        len(warnings),
    )
    return ScaffoldBlockResult(
        path=str(target),
        bytes_written=bytes_written,
        created=True,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# (b.4) reload_blocks  (write-class)
# ---------------------------------------------------------------------------


@mcp.tool(name="reload_blocks")
async def reload_blocks() -> ReloadBlocksResult:
    """Hot-reload the block registry.

    Use when:
      - You've edited a block source file (existing or scaffolded) and
        want the new code picked up without restarting the backend.

    Do NOT use to:
      - Discover new entry-point blocks — pip installs require a
        backend restart; this only rescans the in-process registry.
    """
    ctx = get_context()
    before = set(ctx.block_registry.all_specs().keys())
    ctx.block_registry.hot_reload()
    after = set(ctx.block_registry.all_specs().keys())
    added = sorted(after - before)
    removed = sorted(before - after)
    logger.info("reload_blocks: added=%s removed=%s", added, removed)
    return ReloadBlocksResult(reloaded=len(after), added=added, removed=removed)


# ---------------------------------------------------------------------------
# (b.5) run_block_tests  (write-class — invokes pytest subprocess)
# ---------------------------------------------------------------------------


@mcp.tool(name="run_block_tests")
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
    if not test_path.exists():
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
