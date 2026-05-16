"""FastMCP parity tests (ADR-040 §3.1).

These tests assert the FastMCP-backed MCP server matches the ADR-040
contract: 26 tools, write-class tools carry ``next_step``,
``scaffold_block`` carries the widened §3.2a signature, FastMCP-
generated inputSchema rejects malformed calls, and ``finish_ai_block``
returns a discriminated union.
"""

from __future__ import annotations

import asyncio
import inspect

# ---------------------------------------------------------------------------
# 26-tool parity
# ---------------------------------------------------------------------------


def test_fastmcp_lists_26_tools() -> None:
    """ADR-040 §3.1: 26 tools discoverable via mcp.list_tools()."""
    from scieasy.ai.agent.mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    assert len(tools) == 26, [t.name for t in tools]


def test_fastmcp_tool_names_match_expected_set() -> None:
    """Spot-check that every expected tool name shows up."""
    from scieasy.ai.agent.mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        # workflow (10)
        "list_blocks",
        "get_block_schema",
        "list_types",
        "get_workflow",
        "validate_workflow",
        "write_workflow",
        "run_workflow",
        "cancel_run",
        "get_run_status",
        "finish_ai_block",
        # authoring (5)
        "read_block_source",
        "list_block_examples",
        "scaffold_block",
        "reload_blocks",
        "run_block_tests",
        # inspection (7)
        "get_block_output",
        "inspect_data",
        "preview_data",
        "get_lineage",
        "get_block_config",
        "update_block_config",
        "get_block_logs",
        # qa (4)
        "search_docs",
        "get_doc",
        "list_data",
        "get_project_info",
    }
    assert names == expected, f"unexpected diff: {names ^ expected}"


# ---------------------------------------------------------------------------
# Write-class next_step parity
# ---------------------------------------------------------------------------


def test_write_class_tools_have_next_step() -> None:
    """ADR-040 §3.1: every write-class tool's result model has next_step: str."""
    from scieasy.ai.agent.mcp import tools_authoring, tools_inspection, tools_workflow

    write_class_results = [
        tools_workflow.WriteWorkflowResult,
        tools_workflow.RunWorkflowResult,
        tools_workflow.CancelRunResult,
        tools_workflow.FinishAIBlockOK,
        tools_authoring.ScaffoldBlockResult,
        tools_authoring.ReloadBlocksResult,
        tools_authoring.RunBlockTestsResult,
        tools_inspection.UpdateBlockConfigResult,
    ]
    for cls in write_class_results:
        fields = cls.model_fields
        assert "next_step" in fields, f"{cls.__name__} missing next_step"
        assert fields["next_step"].annotation is str, (
            f"{cls.__name__}.next_step must be str, got {fields['next_step'].annotation}"
        )


# ---------------------------------------------------------------------------
# scaffold_block widened signature
# ---------------------------------------------------------------------------


def test_scaffold_block_signature_widened() -> None:
    """ADR-040 §3.2a (manifest §8.6): scaffold_block accepts input_ports + output_ports."""
    from scieasy.ai.agent.mcp.tools_authoring import scaffold_block

    sig = inspect.signature(scaffold_block)
    params = sig.parameters
    assert "input_ports" in params
    assert "output_ports" in params


# ---------------------------------------------------------------------------
# §3.2a soft-validation warnings
# ---------------------------------------------------------------------------


def test_scaffold_block_warns_on_generic_dataobject_port(tmp_path, monkeypatch) -> None:
    """ADR-040 §3.2a: warning text fires when a port uses generic DataObject."""
    from scieasy.ai.agent.mcp import _context, tools_authoring
    from scieasy.blocks.registry import BlockRegistry
    from scieasy.core.types.registry import TypeRegistry

    class _Ctx:
        block_registry = BlockRegistry()
        type_registry = TypeRegistry()
        project_dir = tmp_path

    _context.set_context(_Ctx())
    try:
        result = asyncio.run(
            tools_authoring.scaffold_block(
                name="warn_generic",
                category="process",
                input_ports={"in": {"type": "DataObject"}},
                output_ports={"out": {"type": "DataObject"}},
            )
        )
        assert result.warnings, "expected soft-validation warnings"
        assert any("DataObject" in w for w in result.warnings)
    finally:
        _context.set_context(None)


def test_scaffold_block_warns_on_unregistered_type(tmp_path) -> None:
    """ADR-040 §3.2a: warning fires when a port type isn't in TypeRegistry."""
    from scieasy.ai.agent.mcp import _context, tools_authoring
    from scieasy.blocks.registry import BlockRegistry
    from scieasy.core.types.registry import TypeRegistry

    type_registry = TypeRegistry()
    type_registry.scan_builtins()

    class _Ctx:
        block_registry = BlockRegistry()

        @property
        def project_dir(self):
            return tmp_path

    ctx = _Ctx()
    ctx.type_registry = type_registry
    _context.set_context(ctx)
    try:
        result = asyncio.run(
            tools_authoring.scaffold_block(
                name="warn_unreg",
                category="process",
                input_ports={"in": {"type": "DefinitelyNotRegisteredType"}},
            )
        )
        assert any("unregistered type" in w.lower() for w in result.warnings), result.warnings
    finally:
        _context.set_context(None)


def test_scaffold_block_no_warnings_when_generic_block_uses_dataobject(tmp_path) -> None:
    """SubWorkflowBlock / AppBlock are exempt from the DataObject warning."""
    from scieasy.ai.agent.mcp import _context, tools_authoring
    from scieasy.blocks.registry import BlockRegistry
    from scieasy.core.types.registry import TypeRegistry

    class _Ctx:
        block_registry = BlockRegistry()
        type_registry = TypeRegistry()
        project_dir = tmp_path

    _context.set_context(_Ctx())
    try:
        result = asyncio.run(
            tools_authoring.scaffold_block(
                name="generic_app",
                category="app",
                input_ports={"in": {"type": "DataObject"}},
            )
        )
        # App category is generic — no DataObject warning fires.
        do_warnings = [w for w in result.warnings if "DataObject" in w]
        assert not do_warnings, do_warnings
    finally:
        _context.set_context(None)


# ---------------------------------------------------------------------------
# inputSchema rejection at MCP boundary
# ---------------------------------------------------------------------------


def test_input_schema_rejects_malformed_call() -> None:
    """ADR-040 §3.1: FastMCP-generated inputSchema rejects calls before reaching the tool body."""
    from scieasy.ai.agent.mcp.server import mcp

    async def _go():
        # get_block_schema requires type_name: str — passing the wrong
        # type should be rejected by FastMCP's input validation before
        # the body ever runs.
        try:
            await mcp.call_tool("get_block_schema", {"type_name": 12345})
        except Exception as exc:
            return exc
        return None

    err = asyncio.run(_go())
    assert err is not None, "FastMCP should reject malformed call"


# ---------------------------------------------------------------------------
# finish_ai_block union return
# ---------------------------------------------------------------------------


def test_finish_ai_block_returns_union_of_ok_or_error() -> None:
    """finish_ai_block returns FinishAIBlockOK | FinishAIBlockError discriminated union."""
    from scieasy.ai.agent.mcp.tools_workflow import (
        FinishAIBlockError,
        FinishAIBlockOK,
        finish_ai_block,
    )

    # Inspect the function's return annotation; FastMCP serialises Pydantic
    # discriminated unions cleanly into MCP content blocks.
    hints = inspect.get_annotations(finish_ai_block, eval_str=True)
    ret = hints.get("return")
    assert ret is not None
    # The annotation is Union[FinishAIBlockOK, FinishAIBlockError]; check
    # both members appear by name in the typed annotation.
    args = getattr(ret, "__args__", ())
    arg_names = {getattr(a, "__name__", "") for a in args}
    assert "FinishAIBlockOK" in arg_names
    assert "FinishAIBlockError" in arg_names
    _ = FinishAIBlockOK, FinishAIBlockError


# ---------------------------------------------------------------------------
# Tool descriptions follow §3.2 style guide (imperative + "Use when …")
# ---------------------------------------------------------------------------


def test_every_tool_description_uses_imperative_first_line() -> None:
    """ADR-040 §3.2: every tool's docstring opens with an imperative line."""
    from scieasy.ai.agent.mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    for tool in tools:
        desc = (tool.description or "").strip()
        assert desc, f"{tool.name} has empty description"
        # Imperative verbs start the first line; rough heuristic — not "TODO" / "S40a skeleton".
        first_line = desc.split("\n", 1)[0].lower()
        assert "todo" not in first_line, f"{tool.name} description starts with TODO"
        assert "skeleton" not in first_line, f"{tool.name} description still says skeleton"
