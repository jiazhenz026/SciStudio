"""MCP server — FastMCP-backed implementation (ADR-040 §3.1).

Owns the module-scope ``fastmcp.FastMCP`` instance the four
``tools_*.py`` modules decorate their tool functions onto, plus the
:class:`MCPServer` lifecycle wrapper preserved from the ADR-033 era so
the FastAPI lifespan in :mod:`scieasy.api.app` and the standalone
``scieasy mcp-bridge`` runtime can construct it by name.

Transport (preserved from pre-FastMCP era so the bridge protocol does
not move):

* **POSIX** — Unix domain socket at the path provided by the caller
  (default ``{project}/.scieasy/mcp.sock``). Line-delimited JSON-RPC.
* **Windows** — TCP loopback on ``127.0.0.1`` with an ephemeral port;
  the port is written to ``<socket_path>.port`` next to the sentinel
  socket-path file so the bridge subprocess can discover it.

The wrapper bridges two impedance mismatches:

1. FastMCP's native ``run_async`` blocks for the lifetime of the
   server; the FastAPI lifespan wants ``start()``/``stop()`` that
   return promptly while a background task owns the serve loop.
2. The bridge subprocess wants a single blocking ``await server.serve()``
   call. ``serve()`` is therefore the merge of ``start()`` + ``wait``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sys
from pathlib import Path

from fastmcp import FastMCP

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-scope FastMCP instance (ADR-040 §3.1).
#
# Tool modules (``tools_workflow.py`` etc.) import this and decorate their
# functions with ``@mcp.tool(name=..., tags={...})``. FastMCP auto-discovers
# them and exposes via ``await mcp.list_tools()`` (used by
# :mod:`scieasy.ai.agent.system_prompt._render_tool_catalog`).
# ---------------------------------------------------------------------------

mcp: FastMCP = FastMCP(name="scieasy-mcp", version="0.1.0")
"""Module-scope FastMCP instance (ADR-040 §3.1)."""


# JSON-RPC 2.0 error codes preserved for the line-delimited transport
# adapter below.
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603


# ---------------------------------------------------------------------------
# MCPServer lifecycle wrapper — preserved name + shape from ADR-033 era.
# ---------------------------------------------------------------------------


class MCPServer:
    """Thin lifecycle wrapper around the FastMCP server.

    Preserves the constructor signature + ``start``/``stop``/``serve``
    surface the FastAPI lifespan (:mod:`scieasy.api.app`) and the
    standalone-bridge runtime (:mod:`scieasy.ai.agent.mcp.runtime`)
    already call, while delegating dispatch + ``inputSchema`` generation
    to FastMCP.

    Transport stays line-delimited JSON-RPC over a Unix socket (POSIX)
    or TCP loopback (Windows) so the existing bridge subprocess
    (``scieasy mcp-bridge``) and Claude Code's MCP client implementation
    keep working without protocol churn.

    Parameters
    ----------
    socket_path
        Filesystem path for the Unix domain socket (POSIX). On Windows
        this is treated as a sibling sentinel file: the actual TCP port
        is written to ``<socket_path>.port`` next to it.
    project_dir
        Project workspace root. Threaded through to tool handlers via
        :func:`scieasy.ai.agent.mcp._context.set_context` so they can
        resolve relative paths without consulting global state.
    """

    socket_path: Path
    project_dir: Path

    def __init__(self, socket_path: Path, project_dir: Path) -> None:
        self.socket_path = socket_path
        self.project_dir = project_dir
        self._server: asyncio.AbstractServer | None = None
        self._port: int | None = None

    async def start(self) -> None:
        """Bind the transport and start accepting JSON-RPC requests.

        Idempotent: a second call while already started is a no-op.

        Returns after the listener is bound, so the FastAPI lifespan
        can move on to other startup work while the accept loop runs
        as a background asyncio task owned by the asyncio server.
        """
        if self._server is not None:
            return
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        if sys.platform == "win32":
            # TCP loopback fallback — asyncio's named-pipe API on
            # Windows is partial and varies by Python build.
            self._server = await asyncio.start_server(self._handle_client, host="127.0.0.1", port=0)
            sockets = self._server.sockets or ()
            if sockets:
                self._port = int(sockets[0].getsockname()[1])
                port_file = self.socket_path.with_suffix(self.socket_path.suffix + ".port")
                port_file.parent.mkdir(parents=True, exist_ok=True)
                port_file.write_text(str(self._port), encoding="utf-8")
        else:
            # Remove stale socket from a prior crashed run.
            with contextlib.suppress(OSError):
                if self.socket_path.exists():
                    os.unlink(self.socket_path)
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
            with contextlib.suppress(OSError):
                if self.socket_path.exists():
                    os.unlink(self.socket_path)
        else:
            port_file = self.socket_path.with_suffix(self.socket_path.suffix + ".port")
            with contextlib.suppress(OSError):
                if port_file.exists():
                    os.unlink(port_file)
        self._server = None
        self._port = None
        logger.info("MCPServer: stopped")

    @property
    def port(self) -> int | None:
        """Bound TCP port on Windows transport, or ``None`` on POSIX."""
        return self._port

    async def serve(self) -> None:
        """Bind transport and block until shutdown.

        Convenience entry point for the standalone-bridge ``mcp-bridge``
        subprocess, which awaits a single coroutine for its lifetime.
        Equivalent to ``await start()`` followed by waiting for the
        server's accept loop to exit (which only happens via
        ``stop()`` or process termination).
        """
        await self.start()
        if self._server is None:  # pragma: no cover - start always sets _server
            return
        try:
            await self._server.serve_forever()
        except asyncio.CancelledError:
            raise
        finally:
            await self.stop()

    # ------------------------------------------------------------------
    # Per-connection accept loop — line-delimited JSON-RPC framing.
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
    # Dispatch (the public surface tests exercise directly).
    # ------------------------------------------------------------------

    async def dispatch(self, request: dict) -> dict:
        """Route one decoded JSON-RPC request through FastMCP.

        Recognised methods:

        * ``"initialize"`` — MCP handshake; returns server capabilities.
        * ``"tools/list"`` — enumerates the registered tools.
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
                fastmcp_tools = await mcp.list_tools()
                tools = []
                for entry in fastmcp_tools:
                    tags = set(entry.tags or set())
                    category = next(
                        (t.split(":", 1)[1] for t in tags if t.startswith("category:")),
                        "uncategorised",
                    )
                    mutation = "write" if "write" in tags else "read"
                    tools.append(
                        {
                            "name": entry.name,
                            "description": entry.description or "",
                            "inputSchema": entry.parameters,
                            "_meta": {"category": category, "mutation": mutation},
                        }
                    )
                return _ok(req_id, {"tools": tools})
            if method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments") or {}
                if not isinstance(name, str):
                    return _error_response(req_id, _INVALID_PARAMS, "missing tool 'name'")
                # Pre-check tool existence so the unknown-tool error
                # surfaces as JSON-RPC METHOD_NOT_FOUND (-32601) rather
                # than INVALID_PARAMS (-32602).
                known_tools = await mcp.list_tools()
                if name not in {t.name for t in known_tools}:
                    return _error_response(req_id, _METHOD_NOT_FOUND, f"unknown tool '{name}'")
                try:
                    result = await mcp.call_tool(name, arguments)
                except Exception as exc:
                    return _error_response(
                        req_id,
                        _INVALID_PARAMS,
                        f"call_tool failed for {name}: {type(exc).__name__}: {exc}",
                    )
                content_text = json.dumps(_serialise_result(result), default=str)
                return _ok(
                    req_id,
                    {"content": [{"type": "text", "text": content_text}]},
                )

            return _error_response(req_id, _METHOD_NOT_FOUND, f"unknown method '{method}'")
        except Exception as exc:
            logger.exception("MCPServer.dispatch failed for method=%s", method)
            return _error_response(req_id, _INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")


def _ok(req_id: int | str | None, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error_response(req_id: int | str | None, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _serialise_result(result: object) -> object:
    """Coerce a FastMCP ToolResult-like object to a JSON-friendly value.

    FastMCP's ``call_tool`` returns either a ``ToolResult`` (with
    ``structured_content``) or already-coerced primitives depending on
    version. We normalise to the most informative JSON value available.
    """
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return structured
    content = getattr(result, "content", None)
    if content is not None:
        out = []
        for block in content:
            text = getattr(block, "text", None)
            if text is not None:
                try:
                    out.append(json.loads(text))
                except (json.JSONDecodeError, TypeError):
                    out.append(text)
            else:
                model_dump = getattr(block, "model_dump", None)
                out.append(model_dump() if callable(model_dump) else str(block))
        return out[0] if len(out) == 1 else out
    return result


__all__ = ["MCPServer", "mcp"]
