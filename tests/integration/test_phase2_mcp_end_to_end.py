"""T-ECA-205: MCP server end-to-end integration (ADR-040 FastMCP).

Drives the MCP server through the FastMCP in-memory client transport
to avoid platform-specific socket setup. Verifies:

* The FastMCP catalogue surfaces all 26 tools (25 baseline + finish_ai_block).
* Reading a tool via ``mcp.call_tool`` round-trips the Pydantic result
  through the MCP content-block envelope.
* ``MCPServer.start()`` / ``.stop()`` are idempotent.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from scieasy.ai.agent.mcp import _context
from scieasy.ai.agent.mcp.server import MCPServer, mcp
from scieasy.blocks.registry import BlockRegistry
from scieasy.core.types.registry import TypeRegistry


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
def stub_ctx(tmp_path: Path) -> Iterator[_StubRuntime]:
    runtime = _StubRuntime(_project_dir=tmp_path)
    runtime.type_registry.scan_builtins()
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


def test_mcp_lists_26_tools(stub_ctx: _StubRuntime) -> None:
    """ADR-040 §3.1: 26 tools discoverable via FastMCP."""
    tools = asyncio.run(mcp.list_tools())
    assert len(tools) == 26
    names = {t.name for t in tools}
    assert "list_blocks" in names
    assert "preview_data" in names
    assert "search_docs" in names
    assert "finish_ai_block" in names


def test_mcp_call_list_types_round_trips(stub_ctx: _StubRuntime) -> None:
    """tools/call list_types must round-trip through the MCP content envelope."""
    import json

    result = asyncio.run(mcp.call_tool("list_types", {}))
    assert result.content, "missing content"
    # FastMCP serialises Pydantic result models as JSON in a text content block.
    block = result.content[0]
    assert block.type == "text"
    decoded = json.loads(block.text)
    assert "count" in decoded or "types" in decoded


def test_mcp_unknown_tool_raises_or_errors(stub_ctx: _StubRuntime) -> None:
    """Calling a non-existent tool surfaces a structured error, not a crash."""

    async def _go():
        try:
            await mcp.call_tool("no_such_tool", {})
        except Exception as exc:
            return exc
        return None

    err = asyncio.run(_go())
    assert err is not None


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "FastMCP HTTP transport on Windows uses TCP loopback rather than UDS; "
        "the lifecycle smoke test is platform-divergent. Cross-platform coverage "
        "comes from test_mcp_lists_26_tools/test_mcp_call_list_types_round_trips "
        "which exercise the in-process catalogue."
    ),
)
def test_mcp_server_start_is_idempotent(tmp_path: Path, stub_ctx: _StubRuntime) -> None:
    """Calling start() twice must not raise."""

    async def _scenario() -> None:
        server = MCPServer(socket_path=tmp_path / "mcp.sock", project_dir=tmp_path)
        try:
            await server.start()
            await server.start()  # second call no-op
        finally:
            await server.stop()
            await server.stop()  # second stop no-op

    asyncio.run(_scenario())


def test_mcp_server_lifecycle_attribute_surface(tmp_path: Path) -> None:
    """MCPServer must expose ``port``, ``start``, ``stop`` for callers."""
    server = MCPServer(socket_path=tmp_path / "mcp.sock", project_dir=tmp_path)
    assert hasattr(server, "port")
    assert callable(server.start)
    assert callable(server.stop)
