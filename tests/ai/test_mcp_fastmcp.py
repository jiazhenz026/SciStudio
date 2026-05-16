"""FastMCP parity tests (ADR-040 §3.1, I40a Phase 2a).

Asserts the FastMCP-backed MCP server matches the ADR-040 contract:

* 26 tools discoverable via ``await mcp.list_tools()``.
* Every write-class tool's result model has ``next_step: str``.
* ``scaffold_block`` has the widened §3.2a signature with
  ``input_ports`` + ``output_ports`` dict args and a ``warnings`` field.
* ``inputSchema`` is FastMCP-generated (no ``additionalProperties: true``
  fallback from the ADR-033-era hand-rolled JSON-RPC stub).
* §3.2a soft-validation warnings fire on generic-``DataObject`` ports
  and unregistered type names.
* ``finish_ai_block`` returns a ``FinishAIBlockOK | FinishAIBlockError``
  discriminated union.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from scieasy.ai.agent.mcp import _context, tools_authoring, tools_workflow
from scieasy.ai.agent.mcp.server import mcp
from scieasy.blocks.registry import BlockRegistry
from scieasy.core.types.registry import TypeRegistry

_EXPECTED_TOOL_NAMES = {
    # category (a) workflow
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
    # category (b) authoring
    "read_block_source",
    "list_block_examples",
    "scaffold_block",
    "reload_blocks",
    "run_block_tests",
    # category (c) inspection
    "get_block_output",
    "inspect_data",
    "preview_data",
    "get_lineage",
    "get_block_config",
    "update_block_config",
    "get_block_logs",
    # category (d) qa
    "search_docs",
    "get_doc",
    "list_data",
    "get_project_info",
}


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tool registry parity.
# ---------------------------------------------------------------------------


def test_fastmcp_lists_26_tools() -> None:
    """ADR-040 §3.1 + ADR-035: 26 tools discoverable via mcp.list_tools()."""
    tools = _run(mcp.list_tools())
    assert len(tools) == 26
    names = {t.name for t in tools}
    assert names == _EXPECTED_TOOL_NAMES, (
        f"missing: {_EXPECTED_TOOL_NAMES - names}; extra: {names - _EXPECTED_TOOL_NAMES}"
    )


def test_write_class_tools_have_next_step() -> None:
    """ADR-040 §3.2: every write-class tool's result model has next_step: str."""
    write_class = {
        "write_workflow",
        "run_workflow",
        "cancel_run",
        "finish_ai_block",
        "scaffold_block",
        "reload_blocks",
        "run_block_tests",
        "update_block_config",
    }
    tools = _run(mcp.list_tools())
    by_name = {t.name: t for t in tools}
    for name in write_class:
        tool = by_name[name]
        if name == "finish_ai_block":
            # Union[FinishAIBlockOK, FinishAIBlockError]; next_step lives on OK.
            from scieasy.ai.agent.mcp.tools_workflow import FinishAIBlockOK

            assert "next_step" in FinishAIBlockOK.model_fields, f"{name}: FinishAIBlockOK missing next_step field"
            continue
        # FastMCP records the return type — pull from inspect's signature
        # since __annotations__ may carry string forward-refs under
        # ``from __future__ import annotations``.
        sig = inspect.signature(tool.fn)
        return_ann = sig.return_annotation
        # Resolve via tool.fn module globals if still a string.
        if isinstance(return_ann, str):
            return_ann = tool.fn.__globals__.get(return_ann, return_ann)
        target = return_ann if hasattr(return_ann, "model_fields") else None
        assert target is not None, f"{name}: could not resolve return-type model"
        assert "next_step" in target.model_fields, f"{name}: result model missing next_step field"


def test_scaffold_block_signature_widened() -> None:
    """ADR-040 §3.2a (manifest §8.6): scaffold_block accepts input_ports + output_ports dicts."""
    sig = inspect.signature(tools_authoring.scaffold_block)
    params = sig.parameters
    assert "input_ports" in params
    assert "output_ports" in params


# ---------------------------------------------------------------------------
# §3.2a soft validation.
# ---------------------------------------------------------------------------


@dataclass
class _StubRuntime:
    block_registry: BlockRegistry = field(default_factory=BlockRegistry)
    type_registry: TypeRegistry = field(default_factory=TypeRegistry)
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    _project_dir: Path | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@pytest.fixture
def stub_ctx(tmp_path: Path):
    runtime = _StubRuntime(_project_dir=tmp_path)
    runtime.type_registry.scan_builtins()
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


def test_scaffold_block_warns_on_generic_dataobject_port(stub_ctx, tmp_path: Path) -> None:
    """ADR-040 §3.2a: warning text fires when a port uses generic DataObject."""
    result = _run(
        tools_authoring.scaffold_block(
            name="test_block_dataobject",
            category="process",
            input_ports={"in": {"type": "DataObject"}},
            output_ports={"out": {"type": "DataObject"}},
        )
    )
    assert result.warnings, "expected at least one warning"
    joined = " ".join(result.warnings).lower()
    assert "dataobject" in joined
    assert "list_types" in joined or "concrete type" in joined
    assert Path(result.path).exists()


def test_scaffold_block_warns_on_unregistered_type(stub_ctx, tmp_path: Path) -> None:
    """ADR-040 §3.2a: warning text fires when a port type isn't in TypeRegistry."""
    result = _run(
        tools_authoring.scaffold_block(
            name="test_block_unregistered",
            category="process",
            input_ports={"in": {"type": "ThisTypeDoesNotExist_XYZ"}},
        )
    )
    joined = " ".join(result.warnings).lower()
    assert "unregistered" in joined or "thistypedoesnotexist_xyz" in joined


# ---------------------------------------------------------------------------
# inputSchema generation.
# ---------------------------------------------------------------------------


def test_input_schema_rejects_malformed_call() -> None:
    """ADR-040 §3.1: FastMCP-generated inputSchema rejects malformed args before tool body.

    No ``additionalProperties: true`` fallback — FastMCP's strict
    inputSchema generation is the boundary contract.
    """
    tools = _run(mcp.list_tools())
    by_name = {t.name: t for t in tools}
    schema = by_name["get_block_schema"].parameters
    assert schema.get("additionalProperties") is False, (
        "ADR-040 §3.1 regression: inputSchema must reject extra fields. "
        "Got additionalProperties=" + str(schema.get("additionalProperties"))
    )
    assert "type_name" in schema.get("properties", {}), (
        f"get_block_schema inputSchema missing type_name property: {schema}"
    )
    # Calling with the wrong field name should fail validation at the boundary.
    # FastMCP raises ToolError on input-schema validation failure.
    from fastmcp.exceptions import ToolError

    with pytest.raises((ToolError, ValueError, TypeError)):
        _run(mcp.call_tool("get_block_schema", {"not_a_param": "x"}))


# ---------------------------------------------------------------------------
# finish_ai_block union return.
# ---------------------------------------------------------------------------


def test_finish_ai_block_returns_union_of_ok_or_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-035 §3.5 + ADR-040 §3.1: finish_ai_block returns OK | Error union envelope."""
    monkeypatch.delenv("SCIEASY_AI_BLOCK_RUN_DIR", raising=False)
    _context.set_context(None)
    result = _run(tools_workflow.finish_ai_block({}))
    assert result.status == "error"
    assert result.code == "not_in_ai_block_context"
