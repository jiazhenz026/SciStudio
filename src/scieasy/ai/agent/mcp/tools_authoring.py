"""Category (b) MCP tools — block authoring helpers (5 tools).

ADR-040 §3.1 FastMCP migration, S40a skeleton phase. All tool functions
are decorated with ``@mcp.tool(name=...)`` and declare Pydantic result
models. Bodies raise :class:`NotImplementedError` with a detailed
``# TODO(#1012)`` comment block describing the impl approach for I40a
Phase 2a.

The 5 tools are:

Read-class (2): ``read_block_source``, ``list_block_examples``.
Write-class (3): ``scaffold_block``, ``reload_blocks``, ``run_block_tests``.

Per ADR-040 §3.2a, ``scaffold_block`` is widened from the ADR-033-era
``(name, category)`` signature to ``(name, category, input_ports,
output_ports, ...)`` so the §3.2a ``warnings: list[str]`` soft-validation
logic has port specs to inspect. See manifest §8.6 for the design
rationale.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from pydantic import BaseModel, Field

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
    detection). ``next_step`` points the agent at the post-scaffold
    workflow.
    """

    path: str = Field(description="Absolute filesystem path of the scaffolded block file.")
    bytes_written: int = Field(description="Number of bytes written to disk.")
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
      - Edit a block — use ``Edit``/``Write`` on the path returned here
        (the file is in the project's ``blocks/`` dir, which the
        protect_workflow_yaml hook does NOT cover; direct edits are fine).
      - Discover example patterns — use ``list_block_examples``.

    Raises ``KeyError`` if the type is not registered.
    """
    # TODO(#1012): port from ADR-033-era impl. Reference:
    #   1. ctx.block_registry.get_spec(type_name); raise KeyError if None.
    #   2. Prefer spec.file_path for Tier 1 blocks; fall back to
    #      inspect.getfile(importlib.import_module(...)) for Tier 2.
    #   3. Read path.read_text("utf-8") and return ReadBlockSourceResult.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


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
    # TODO(#1012): port from ADR-033-era impl preserving the
    #   _EXAMPLE_CURATION dict (io/process/code/app/ai/subworkflow).
    #   Reference impl iterates the curation list, importlib.import_module
    #   each, inspect.getfile to get the path, and reads the first line
    #   of __doc__ for the description.
    #
    #   I40a notes:
    #   - v2 should make the curation list configurable via project
    #     settings (per ADR-033 §6 T-ECA-203). Out of scope for this
    #     migration — keep the hardcoded dict.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (b.3) scaffold_block  (write-class)
#
# ADR-040 §3.2a widens the signature to include input_ports + output_ports
# so the §3.2a soft-validation `warnings` logic has port specs to inspect.
# See manifest §8.6 for the contract-widening rationale.
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
        ``TypeRegistry`` (register the new type via the
        ``scieasy.types`` entry-point in your plugin).

    Both warnings are advisory; the file is still written. Raises
    ``FileExistsError`` if the target path already exists.
    """
    # TODO(#1012): port + extend from ADR-033-era impl. Critical changes
    #   from the prior shape:
    #   1. Signature widened per ADR-040 §3.2a (manifest §8.6) — input_ports
    #      and output_ports are now first-class args. Use them in the
    #      scaffolded template's ports list (replace the commented-out
    #      placeholder lines in _SCAFFOLD_TEMPLATE with real entries
    #      derived from the dict).
    #   2. Implement the §3.2a soft-validation logic:
    #        warnings: list[str] = []
    #        for port_name, spec in {**input_ports, **output_ports}.items():
    #            type_name = spec.get("type", "")
    #            if type_name == "DataObject":
    #                warnings.append(
    #                    f"Port '{port_name}' uses generic DataObject. Preview "
    #                    "and edge-time type checking will degrade. Confirm "
    #                    "intentional (e.g. SubWorkflowBlock or generic "
    #                    "AppBlock); otherwise pick a concrete type from "
    #                    "mcp__scieasy__list_types()."
    #                )
    #            elif not ctx.type_registry.has(type_name):
    #                warnings.append(
    #                    f"Port '{port_name}' references unregistered type "
    #                    f"'{type_name}'. Either pick from list_types() or "
    #                    "register the new type via the scieasy.types "
    #                    "entry-point in this plugin."
    #                )
    #
    #      TODO(#1016): the soft-validation here is the L4 layer; the L5
    #      PostToolUse hook (enforce_concrete_port_types.py per ADR-040
    #      §3.6) is the second-layer defense for the Edit/Write bypass
    #      path. Hard BlockRegistry-level rejection (the L7 escalation)
    #      is deferred to a future ADR.
    #
    #   3. Preserve ADR-033-era impl bones:
    #      - _resolve_project_root(ctx) → blocks_dir = root / "blocks".
    #      - blocks_dir.mkdir(parents=True, exist_ok=True).
    #      - target = blocks_dir / f"{name}.py".
    #      - if target.exists(): raise FileExistsError.
    #      - class_name = _snake_to_camel(name) or "MyBlock".
    #      - text = template.format(...) ; target.write_text(text, "utf-8").
    #      - logger.info("scaffold_block: created %s (category=%s)", target, category).
    #
    #   4. ctx.type_registry.has(name) — verify this method exists on the
    #      live TypeRegistry. If not, fall back to
    #      ``name in ctx.type_registry.all_types()``.
    #
    #   Out of scope per ADR-040 §3.2a / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


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
    # TODO(#1012): port from ADR-033-era impl. Reference:
    #     ctx = get_context()
    #     before = set(ctx.block_registry.all_specs().keys())
    #     ctx.block_registry.hot_reload()
    #     after = set(ctx.block_registry.all_specs().keys())
    #     added = sorted(after - before); removed = sorted(before - after)
    #     return ReloadBlocksResult(reloaded=len(after), added=added, removed=removed)
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


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
    # TODO(#1012): port from ADR-033-era impl. Reference:
    #   1. test_path = root / "tests" / "blocks" / f"test_{type_name.lower()}.py".
    #   2. If not test_path.exists() → return returncode=-1, found=False,
    #      stderr=f"test file not found: {test_path}".
    #   3. subprocess.run([sys.executable, "-m", "pytest", str(test_path),
    #      "--tb=short", "-q"], capture_output=True, text=True,
    #      cwd=str(root), timeout=300).
    #   4. Return RunBlockTestsResult with returncode, stdout, stderr,
    #      test_path, found=True.
    #
    #   I40a notes: pytest invocation should NOT inherit --timeout from
    #   the parent pytest if any (clean env). Verify subprocess.run env
    #   does not leak.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")
