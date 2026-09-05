"""Registry-shape tests for the finish_ai_block MCP tool (ADR-035 §3.5 path a).

ADR-040 §3.1 migration: tools are registered via FastMCP's
``@mcp.tool()`` decorator. Registry shape tests iterate
``await mcp.list_tools()`` rather than the deleted ``_registry.TOOL_REGISTRY``.

Behavioural tests live in ``tests/ai/test_finish_ai_block.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from tests.mcp_tool_expectations import EXPECTED_TOOL_COUNT


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
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


def test_registry_holds_every_expected_tool() -> None:
    """FastMCP exposes exactly the expected tool set.

    The number lives in ``tests/mcp_tool_expectations.py``, not here: this file
    is one of five that used to spell it out (ADR-054 §8.4).
    """
    from scistudio.ai.agent.mcp.server import mcp

    tools = _run(mcp.list_tools())
    assert len(tools) == EXPECTED_TOOL_COUNT


def test_finish_ai_block_handler_has_docstring() -> None:
    """Every MCP tool must carry a non-empty docstring (existing convention)."""
    from scistudio.ai.agent.mcp import tools_workflow

    assert (tools_workflow.finish_ai_block.__doc__ or "").strip()
