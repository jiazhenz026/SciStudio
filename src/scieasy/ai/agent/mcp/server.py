"""MCP server — stdio transport over a local socket (POSIX) / TCP loopback (Windows).

T-ECA-205. The FastAPI process owns a single :class:`MCPServer`
instance (constructed in :func:`scieasy.api.app.lifespan`). The
``scieasy mcp-bridge`` subprocess proxies CC's stdin/stdout to the
listening socket; each JSON-RPC frame routed in is dispatched via
:meth:`dispatch` to one of the 25 tools registered in
``scieasy.ai.agent.mcp._registry``.

Transport choice:

* **POSIX** (Linux, macOS) — Unix domain socket at the path provided
  by the caller (default ``{project}/.scieasy/mcp.sock``).
* **Windows** — asyncio's named-pipe API is partial; rather than fight
  it, we listen on a TCP loopback (``127.0.0.1``, ephemeral port) and
  emit the chosen port via the ``socket_path``'s sibling
  ``mcp.port`` file. The bridge reads that to discover the port. This
  preserves the local-only security boundary (loopback bind) and works
  with every Python 3.11+ on Windows.

Framing: line-delimited JSON (one JSON object per line, terminated by
``\\n``). Both directions. This matches the MCP spec's stdio mode and
keeps the bridge implementation trivial.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from scieasy.ai.agent.mcp import _registry

logger = logging.getLogger(__name__)


# JSON-RPC 2.0 error codes
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603


class MCPServer:
    """SciEasy's MCP server.

    A single instance is owned by the FastAPI process. It binds to a
    local-only transport and dispatches incoming JSON-RPC requests to
    the 25 registered MCP tools.

    Parameters
    ----------
    socket_path
        Filesystem path for the Unix domain socket (POSIX). On Windows
        this is treated as a sibling sentinel file: the actual TCP
        port is written to ``<socket_path>.port`` next to it.
    project_dir
        Project workspace root. Threaded through to tool handlers so
        they can resolve relative paths without consulting global
        state.
    """

    socket_path: Path
    project_dir: Path

    def __init__(self, socket_path: Path, project_dir: Path) -> None:
        self.socket_path = socket_path
        self.project_dir = project_dir
        self._server: asyncio.AbstractServer | None = None
        self._accept_task: asyncio.Task[None] | None = None
        self._port: int | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Bind the transport and start the JSON-RPC accept loop.

        Idempotent: a second call while already started is a no-op.
        """
        if self._server is not None:
            return
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        if sys.platform == "win32":
            # TCP loopback fallback (see module docstring).
            self._server = await asyncio.start_server(self._handle_client, host="127.0.0.1", port=0)
            sockets = self._server.sockets or ()
            if sockets:
                self._port = int(sockets[0].getsockname()[1])
                port_file = self.socket_path.with_suffix(self.socket_path.suffix + ".port")
                port_file.write_text(str(self._port), encoding="utf-8")
        else:
            # Remove stale socket file from a prior crashed run.
            try:
                if self.socket_path.exists():
                    os.unlink(self.socket_path)
            except OSError:
                pass
            self._server = await asyncio.start_unix_server(self._handle_client, path=str(self.socket_path))

        logger.info(
            "MCPServer: listening on %s (project_dir=%s)",
            self._port or self.socket_path,
            self.project_dir,
        )

    async def stop(self) -> None:
        """Stop accepting connections and tear down the transport."""
        if self._server is None:
            return
        self._server.close()
        try:
            await self._server.wait_closed()
        except Exception:  # pragma: no cover - defensive
            logger.warning("MCPServer.stop: wait_closed raised", exc_info=True)
        if sys.platform != "win32":
            try:
                if self.socket_path.exists():
                    os.unlink(self.socket_path)
            except OSError:
                pass
        else:
            port_file = self.socket_path.with_suffix(self.socket_path.suffix + ".port")
            try:
                if port_file.exists():
                    os.unlink(port_file)
            except OSError:
                pass
        self._server = None
        self._port = None
        logger.info("MCPServer: stopped")

    @property
    def port(self) -> int | None:
        """Bound TCP port on Windows transport, or ``None`` on POSIX."""
        return self._port

    # ------------------------------------------------------------------
    # Per-connection accept loop
    # ------------------------------------------------------------------

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Read line-delimited JSON-RPC frames and write responses."""
        peer = writer.get_extra_info("peername") or writer.get_extra_info("sockname")
        logger.debug("MCPServer: client connected: %s", peer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    request = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError as exc:
                    response = _error_response(None, _PARSE_ERROR, f"parse error: {exc}")
                else:
                    response = await self.dispatch(request)
                writer.write((json.dumps(response) + "\n").encode("utf-8"))
                await writer.drain()
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        except Exception:
            logger.exception("MCPServer: per-client loop crashed")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            logger.debug("MCPServer: client disconnected: %s", peer)

    # ------------------------------------------------------------------
    # Dispatch (the public surface tests exercise directly)
    # ------------------------------------------------------------------

    async def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        """Route one decoded JSON-RPC request.

        Recognised methods:

        * ``"initialize"`` — MCP handshake; returns server capabilities.
        * ``"tools/list"`` — enumerates the 25 registered tools.
        * ``"tools/call"`` — invokes one tool by name + arguments.
        """
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}

        if not isinstance(method, str):
            return _error_response(req_id, _INVALID_REQUEST, "missing 'method'")

        try:
            if method == "initialize":
                return _ok(
                    req_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "scieasy-mcp", "version": "0.1.0"},
                    },
                )
            if method == "tools/list":
                tools = [
                    {
                        "name": entry.name,
                        "description": entry.description,
                        # Minimal JSON Schema; rich per-tool schemas land in a
                        # later pass once the tools are battle-tested.
                        "inputSchema": {"type": "object", "additionalProperties": True},
                        "_meta": {"category": entry.category, "mutation": entry.mutation},
                    }
                    for entry in _registry.TOOL_REGISTRY
                ]
                return _ok(req_id, {"tools": tools})
            if method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments") or {}
                if not isinstance(name, str):
                    return _error_response(req_id, _INVALID_PARAMS, "missing tool 'name'")
                entry = _registry.lookup(name)
                if entry is None:
                    return _error_response(req_id, _METHOD_NOT_FOUND, f"unknown tool '{name}'")
                try:
                    result = entry.handler(**arguments) if isinstance(arguments, dict) else entry.handler(*arguments)
                except TypeError as exc:
                    return _error_response(req_id, _INVALID_PARAMS, f"bad arguments for {name}: {exc}")
                return _ok(req_id, {"content": [{"type": "json", "data": result}]})

            return _error_response(req_id, _METHOD_NOT_FOUND, f"unknown method '{method}'")
        except Exception as exc:
            logger.exception("MCPServer.dispatch failed for method=%s", method)
            return _error_response(req_id, _INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")


def _ok(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error_response(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
