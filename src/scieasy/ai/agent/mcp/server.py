"""MCP server skeleton — stdio transport over local socket / named pipe.

T-ECA-201 (scaffold). Per ADR-033 §3 D2 and spec §6 T-ECA-201, the
SciEasy backend exposes a Model Context Protocol (MCP) server to the
Claude Code / Codex agent process via a local-only transport:

* **POSIX (Linux, macOS)** — Unix domain socket at
  ``{project}/.scieasy/mcp.sock``.
* **Windows** — named pipe at
  ``\\\\.\\pipe\\scieasy-mcp-{chat_id}``.

The CC binary is configured (via the generated ``mcp.json`` written by
``SessionManager``) to spawn a stdio bridge subprocess
(``scieasy mcp-bridge --socket <path>``) which proxies JSON-RPC frames
between CC's stdin/stdout and the local socket. This indirection
preserves two properties:

1. Pure-Python implementation; no non-stdlib runtime dependency.
2. The MCP server outlives any one CC subprocess: when CC restarts, the
   bridge dies but the FastAPI process and this :class:`MCPServer`
   instance survive.

The :class:`MCPServer` itself is the in-process JSON-RPC dispatcher:
the FastAPI ``lifespan`` handler (wired in T-ECA-205) creates one
instance per process, binds it to the platform-appropriate socket, and
calls :meth:`start` / :meth:`stop` around the server lifetime. Each
incoming JSON-RPC frame is routed to :meth:`dispatch`, which looks up
the requested tool by name in the union of the four ``tools_*`` modules.

This module ships only the class signature. Implementation lands in
T-ECA-205. Tool implementations land in T-ECA-202 / 203 / 204.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class MCPServer:
    """SciEasy's MCP server (skeleton).

    A single instance is owned by the FastAPI process. It binds to a
    local-only transport (Unix socket on POSIX, named pipe on Windows)
    and dispatches incoming JSON-RPC requests to the 25 registered MCP
    tools.

    The constructor stores configuration; binding and listening happen
    in :meth:`start`. This split lets the FastAPI ``lifespan`` handler
    instantiate the server early (e.g. for ``list_tools`` introspection
    during startup logging) and only open the socket after the rest of
    the app is up.

    Parameters
    ----------
    socket_path
        Filesystem path for the Unix domain socket (POSIX) or the
        named-pipe name (Windows). Must be writable by the FastAPI
        process. Convention: ``{project}/.scieasy/mcp.sock``.
    project_dir
        Project workspace root. Threaded through to tool handlers so
        they can resolve relative paths (workflows, data, docs) without
        consulting global state.

    Attributes
    ----------
    socket_path
        See *socket_path* parameter.
    project_dir
        See *project_dir* parameter.

    Notes
    -----
    The skeleton implementation does not yet hold socket state. T-ECA-205
    will add private attributes for the asyncio server handle and the
    accept-loop task.
    """

    socket_path: Path
    project_dir: Path

    def __init__(self, socket_path: Path, project_dir: Path) -> None:
        """Initialise the server with its transport and project context.

        Stores configuration only; no socket is opened. Call
        :meth:`start` to bind and begin accepting connections.

        Parameters
        ----------
        socket_path
            See class-level *socket_path*.
        project_dir
            See class-level *project_dir*.
        """
        self.socket_path = socket_path
        self.project_dir = project_dir

    async def start(self) -> None:
        """Bind the transport and start the JSON-RPC accept loop.

        On POSIX this opens an ``AF_UNIX`` socket via
        :func:`asyncio.start_unix_server` at :attr:`socket_path`. On
        Windows this creates a named pipe with the equivalent
        semantics. The accept loop runs as a background task on the
        current event loop.

        Idempotent: a second call while already started is a no-op.

        Raises
        ------
        OSError
            If the transport cannot be bound (path already in use,
            insufficient permissions, etc.).
        NotImplementedError
            Until T-ECA-205 lands.
        """
        raise NotImplementedError("MCPServer.start lands in T-ECA-205")

    async def stop(self) -> None:
        """Stop accepting connections and tear down the transport.

        Cancels the accept loop, closes the listening socket, and
        unlinks the socket file (POSIX) so a subsequent :meth:`start`
        on the same path does not collide. Idempotent.

        Raises
        ------
        NotImplementedError
            Until T-ECA-205 lands.
        """
        raise NotImplementedError("MCPServer.stop lands in T-ECA-205")

    async def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        """Route one decoded JSON-RPC request to the matching tool.

        Recognised methods:

        * ``"initialize"`` — MCP handshake; returns server capabilities
          and the list of registered tools.
        * ``"tools/list"`` — enumerates the 25 registered tools with
          their JSON Schema.
        * ``"tools/call"`` — invokes one tool with the provided
          arguments. The tool name is matched against the union of the
          four ``tools_*`` modules.

        Parameters
        ----------
        request
            A decoded JSON-RPC request envelope with at minimum
            ``"jsonrpc"``, ``"id"``, and ``"method"`` keys, and an
            optional ``"params"`` object.

        Returns
        -------
        dict
            A decoded JSON-RPC response envelope. On success contains
            ``"result"``; on failure contains ``"error"`` with a code
            and message per the JSON-RPC 2.0 spec.

        Raises
        ------
        NotImplementedError
            Until T-ECA-205 lands. Until then the response shape is
            unspecified.
        """
        raise NotImplementedError("MCPServer.dispatch lands in T-ECA-205")
