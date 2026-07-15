"""Registry-shape tests for the finish_ai_block MCP tool (ADR-035 §3.5 path a).

ADR-040 §3.1 migration: tools are registered via FastMCP's
``@mcp.tool()`` decorator. Registry shape tests iterate
``await mcp.list_tools()`` rather than the deleted ``_registry.TOOL_REGISTRY``.

Behavioural tests live in ``tests/ai/test_finish_ai_block.py``.
"""

from __future__ import annotations

import asyncio


def _run(coro):
    return asyncio.run(coro)


def test_finish_ai_block_is_registered() -> None:
    """ADR-035 §3.5 + ADR-040 §3.1: finish_ai_block exists in FastMCP's catalogue.

    Category + mutation are encoded as FastMCP tags
    (``category:workflow`` + ``write``) per ADR-040 §3.2.
    """
    from scistudio.ai.agent.mcp.server import mcp

    tools = _run(mcp.list_tools())
    by_name = {tool.name: tool for tool in tools}
    assert "finish_ai_block" in by_name
    tags = set(by_name["finish_ai_block"].tags or set())
    assert "category:workflow" in tags
    assert "write" in tags


def test_registry_now_has_35_tools() -> None:
    """ADR-035 §3.5 + ADR-040 §3.1 + Addendum 5 + ADR-048 SPEC 2 + edit_workflow (#1912) + open_gui (#1947): FastMCP exposes 35 tools."""
    from scistudio.ai.agent.mcp.server import mcp

    tools = _run(mcp.list_tools())
    assert len(tools) == 35


def test_finish_ai_block_handler_has_docstring() -> None:
    """Every MCP tool must carry a non-empty docstring (existing convention)."""
    from scistudio.ai.agent.mcp import tools_workflow

    assert (tools_workflow.finish_ai_block.__doc__ or "").strip()
