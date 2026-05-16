"""Registry-shape tests for the finish_ai_block MCP tool.

The behavioural tests live in ``tests/ai/test_finish_ai_block.py``;
this file covers FastMCP-registry-shape assertions only (ADR-040 §3.1
migration replaced the deleted ``_registry.TOOL_REGISTRY`` with
``mcp.list_tools()``).
"""

from __future__ import annotations

import asyncio


def test_finish_ai_block_is_registered() -> None:
    """Tool exists in FastMCP's tool catalogue."""
    from scieasy.ai.agent.mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    names = [tool.name for tool in tools]
    assert "finish_ai_block" in names


def test_registry_now_has_26_tools() -> None:
    """ADR-035 §3.5 + ADR-040 §3.1: FastMCP exposes 26 tools."""
    from scieasy.ai.agent.mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    assert len(tools) == 26


def test_finish_ai_block_handler_has_docstring() -> None:
    """Every MCP tool must carry a non-empty docstring."""
    from scieasy.ai.agent.mcp import tools_workflow

    assert (tools_workflow.finish_ai_block.__doc__ or "").strip()
