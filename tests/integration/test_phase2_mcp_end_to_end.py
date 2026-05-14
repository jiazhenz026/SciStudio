"""T-ECA-205: MCP server end-to-end integration.

Drives the JSON-RPC dispatcher over the actual transport (Unix socket
on POSIX, TCP loopback on Windows). Verifies:

* ``initialize`` handshake returns server info.
* ``tools/list`` enumerates all 25 tools.
* ``tools/call`` for a read-only tool (``list_types``) round-trips.
* Graceful start / stop, no orphan socket files on POSIX.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scieasy.ai.agent.mcp import _context
from scieasy.ai.agent.mcp.server import MCPServer
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


async def _connect_and_call(server: MCPServer, request: dict[str, Any]) -> dict[str, Any]:
    """Open the configured transport, send one request, read one response."""
    if sys.platform == "win32":
        port = server.port
        assert port is not None
        reader, writer = await asyncio.open_connection(host="127.0.0.1", port=port)
    else:
        reader, writer = await asyncio.open_unix_connection(path=str(server.socket_path))

    try:
        writer.write((json.dumps(request) + "\n").encode("utf-8"))
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=10.0)
        return json.loads(line.decode("utf-8"))
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


def test_mcp_server_initialize_tools_list_and_call(tmp_path: Path) -> None:
    asyncio.run(_test_mcp_server_initialize_tools_list_and_call(tmp_path))


async def _test_mcp_server_initialize_tools_list_and_call(tmp_path: Path) -> None:
    runtime = _StubRuntime(_project_dir=tmp_path)
    runtime.type_registry.scan_builtins()
    _context.set_context(runtime)

    socket_path = tmp_path / ".scieasy" / "mcp.sock"
    server = MCPServer(socket_path=socket_path, project_dir=tmp_path)
    try:
        await server.start()

        # initialize handshake
        init = await _connect_and_call(server, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert "result" in init
        assert init["result"]["serverInfo"]["name"] == "scieasy-mcp"

        # tools/list — expect all 25
        listed = await _connect_and_call(server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = listed["result"]["tools"]
        assert len(tools) == 25
        names = {t["name"] for t in tools}
        assert "list_blocks" in names and "preview_data" in names and "search_docs" in names

        # tools/call list_types
        called = await _connect_and_call(
            server,
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_types", "arguments": {}}},
        )
        assert "result" in called
        # list_types returns {types, count}; surfaced under {content: [{type, data}]}
        data = called["result"]["content"][0]["data"]
        assert data["count"] >= 1

        # unknown tool
        err = await _connect_and_call(
            server,
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "no_such_tool"}},
        )
        assert "error" in err
        assert err["error"]["code"] == -32601
    finally:
        await server.stop()
        _context.set_context(None)
        if sys.platform != "win32":
            assert not socket_path.exists(), "socket file should be unlinked after stop()"


def test_mcp_server_start_is_idempotent(tmp_path: Path) -> None:
    asyncio.run(_test_mcp_server_start_is_idempotent(tmp_path))


async def _test_mcp_server_start_is_idempotent(tmp_path: Path) -> None:
    runtime = _StubRuntime(_project_dir=tmp_path)
    _context.set_context(runtime)
    server = MCPServer(socket_path=tmp_path / "mcp.sock", project_dir=tmp_path)
    try:
        await server.start()
        await server.start()  # second call must not raise
    finally:
        await server.stop()
        _context.set_context(None)


def test_mcp_dispatch_parse_error_in_request(tmp_path: Path) -> None:
    asyncio.run(_test_mcp_dispatch_parse_error_in_request(tmp_path))


async def _test_mcp_dispatch_parse_error_in_request(tmp_path: Path) -> None:
    """Malformed JSON over the wire surfaces as a JSON-RPC parse error."""
    runtime = _StubRuntime(_project_dir=tmp_path)
    _context.set_context(runtime)
    server = MCPServer(socket_path=tmp_path / "mcp.sock", project_dir=tmp_path)
    try:
        await server.start()
        if sys.platform == "win32":
            reader, writer = await asyncio.open_connection(host="127.0.0.1", port=server.port)
        else:
            reader, writer = await asyncio.open_unix_connection(path=str(server.socket_path))
        try:
            writer.write(b"{not json\n")
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
        response = json.loads(line.decode("utf-8"))
        assert response["error"]["code"] == -32700
    finally:
        await server.stop()
        _context.set_context(None)
