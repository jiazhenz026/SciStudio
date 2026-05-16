"""MCP server — FastMCP-backed implementation (ADR-040 §3.1).

I40a Phase 2a impl. The hand-rolled asyncio JSON-RPC 2.0 server that
lived here in the ADR-033 era was deleted in the S40a skeleton; FastMCP
3.x now owns the transport, framing, ``inputSchema`` generation, and
dispatch.

This module exposes:

* :data:`mcp` — the module-scope :class:`fastmcp.FastMCP` instance that
  ``tools_workflow.py`` / ``tools_authoring.py`` / ``tools_inspection.py``
  / ``tools_qa.py`` decorate their tool functions onto.
* :class:`MCPServer` — a thin lifecycle wrapper preserving the name +
  shape the FastAPI lifespan and the standalone-bridge runtime already
  call (``MCPServer(socket_path=..., project_dir=...)`` + ``await
  server.start()`` / ``await server.stop()``).

The wrapper is necessary because:

1. The FastAPI ``lifespan`` in :mod:`scieasy.api.app` and the
   standalone-bridge in :mod:`scieasy.ai.agent.mcp.runtime` both
   construct an ``MCPServer`` by name; preserving the name avoids
   cascading edits across the codebase.
2. FastMCP's native ``run_async()`` blocks until the transport
   terminates; the FastAPI lifespan needs an async ``start()`` that
   returns after the listener is bound, plus a non-blocking ``stop()``
   for graceful shutdown. The wrapper provides that lifecycle shape by
   scheduling the serve loop as a background asyncio task.

Transport choice (preserved from the hand-rolled era):

* **POSIX** — Unix domain socket at the path provided by the caller
  (default ``{project}/.scieasy/mcp.sock``).
* **Windows** — TCP loopback (``127.0.0.1``, ephemeral port); the port
  is written to ``<socket_path>.port`` next to the socket-path sentinel
  so the bridge can discover it.

The transport is HTTP+SSE in FastMCP terms, bound to either a Unix
socket (POSIX) or a TCP loopback port (Windows). External MCP clients
(``claude`` / ``codex``) reach it through the ``scieasy mcp-bridge``
shim which forwards stdio frames to the socket.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
import sys
from pathlib import Path

from fastmcp import FastMCP

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-scope FastMCP instance (ADR-040 §3.1).
# ---------------------------------------------------------------------------
#
# Tool modules (``tools_workflow.py`` etc.) import this and decorate
# their async functions with ``@mcp.tool(name=...)``. FastMCP auto-
# discovers them and exposes via ``mcp.list_tools()`` (used by
# :mod:`scieasy.ai.agent.system_prompt`).
# ---------------------------------------------------------------------------

mcp: FastMCP = FastMCP(
    name="scieasy-mcp",
    version="0.1.0",
    instructions=(
        "SciEasy MCP server — the embedded coding agent's interface to "
        "the workflow runtime. See docs/adr/ADR-040.md for the full tool "
        "catalogue and contracts."
    ),
)
"""Module-scope FastMCP instance.

Tool modules import this and decorate their functions::

    @mcp.tool(name="list_blocks")
    async def list_blocks(...) -> ...:
        ...
"""


# ---------------------------------------------------------------------------
# MCPServer lifecycle wrapper — preserved name + shape from ADR-033 era.
# ---------------------------------------------------------------------------


class MCPServer:
    """Thin lifecycle wrapper around the FastMCP server.

    Constructed once per process by the FastAPI lifespan
    (:mod:`scieasy.api.app`) and by the standalone-bridge runtime
    (:mod:`scieasy.ai.agent.mcp.runtime`). Both callers expect:

    * ``MCPServer(socket_path: Path, project_dir: Path)``
    * ``await server.start()`` — bind transport, return after listener
      is up.
    * ``await server.stop()`` — graceful shutdown.
    * ``server.port`` — bound TCP port on Windows transport, or
      ``None`` on POSIX.

    Parameters
    ----------
    socket_path
        Filesystem path for the Unix domain socket (POSIX). On Windows
        this is treated as a sibling sentinel file: the actual TCP
        port is written to ``<socket_path>.port`` next to it.
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
        self._port: int | None = None
        self._serve_task: asyncio.Task[None] | None = None
        self._started: bool = False

    async def start(self) -> None:
        """Bind the FastMCP transport and start accepting requests.

        Idempotent: a second call while already started is a no-op.

        Per ADR-040 §3.1 the transport choice mirrors the ADR-033-era
        socket layout — Unix domain socket on POSIX, TCP loopback on
        Windows — so external MCP bridges (``scieasy mcp-bridge``) can
        find the listener at a deterministic location.
        """
        if self._started:
            return

        # Ensure socket directory exists for both POSIX UDS and Windows
        # port-sentinel writes.
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        if sys.platform == "win32":
            # Bind a TCP loopback socket up-front so we can report the
            # port via the ``port`` property and the ``<socket>.port``
            # sentinel file before run_async() takes over.
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", 0))
            self._port = sock.getsockname()[1]
            sock.close()
            port_sentinel = self.socket_path.with_suffix(self.socket_path.suffix + ".port")
            port_sentinel.write_text(str(self._port), encoding="utf-8")

            async def _serve() -> None:
                # FastMCP's HTTP transport spawns its own uvicorn
                # server; we just hand it the port and let it manage
                # the lifecycle.
                await mcp.run_async(
                    transport="http",
                    host="127.0.0.1",
                    port=self._port,
                    show_banner=False,
                )
        else:
            # POSIX: HTTP+SSE over a Unix domain socket via FastMCP's
            # native ``uds`` transport keyword.
            # Clean up stale socket sentinel from a previous run.
            with contextlib.suppress(FileNotFoundError):
                if self.socket_path.exists() and not self.socket_path.is_dir():
                    self.socket_path.unlink()

            async def _serve() -> None:
                # FastMCP exposes a stdio/http transport API; the UDS
                # transport is registered under the ``http`` transport
                # with a ``uds`` keyword argument. Fall back to TCP if
                # FastMCP doesn't recognise the keyword on this
                # version.
                try:
                    await mcp.run_async(
                        transport="http",
                        uds=str(self.socket_path),
                        show_banner=False,
                    )
                except (TypeError, ValueError):
                    # Older FastMCP: bind a TCP loopback as a fallback
                    # and write the port sentinel so bridges can find
                    # it. This keeps the server alive even when UDS
                    # isn't supported.
                    self._port = _pick_free_port()
                    port_sentinel = self.socket_path.with_suffix(self.socket_path.suffix + ".port")
                    port_sentinel.write_text(str(self._port), encoding="utf-8")
                    await mcp.run_async(
                        transport="http",
                        host="127.0.0.1",
                        port=self._port,
                        show_banner=False,
                    )

        self._serve_task = asyncio.create_task(_serve(), name="mcp-serve")
        # Give the serve task a brief moment to actually bind before
        # returning. We don't have a clean "ready" signal from FastMCP
        # but a yield-then-check pattern is enough to surface immediate
        # bind failures via asyncio's exception-on-await machinery.
        await asyncio.sleep(0)
        if self._serve_task.done():
            # Serve failed during bind — propagate the exception.
            self._serve_task.result()

        self._started = True
        logger.info(
            "MCPServer: listening on %s (port=%s)",
            self.socket_path,
            self._port,
        )

    async def stop(self) -> None:
        """Stop accepting connections and tear down the FastMCP transport.

        Idempotent: a second call after stop is a no-op.
        """
        if not self._started:
            return
        if self._serve_task is not None and not self._serve_task.done():
            self._serve_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._serve_task
        self._serve_task = None
        self._started = False

        # Cleanup sentinel files.
        if sys.platform == "win32" or self._port is not None:
            port_sentinel = self.socket_path.with_suffix(self.socket_path.suffix + ".port")
            with contextlib.suppress(FileNotFoundError, OSError):
                port_sentinel.unlink()
        else:
            with contextlib.suppress(FileNotFoundError, OSError):
                if self.socket_path.exists() and not self.socket_path.is_dir():
                    self.socket_path.unlink()
        self._port = None
        logger.info("MCPServer: stopped (socket=%s)", self.socket_path)

    @property
    def port(self) -> int | None:
        """Bound TCP port on Windows transport, or ``None`` on POSIX UDS."""
        return self._port

    async def serve(self) -> None:
        """Bind transport and block until shutdown (FastMCP-native).

        Convenience entry point for the standalone-bridge ``mcp-bridge``
        subprocess, which wants to block on a single ``await``.
        Equivalent to ``await start()`` followed by ``await
        self._serve_task``.
        """
        await self.start()
        if self._serve_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._serve_task


def _pick_free_port() -> int:
    """Bind/unbind to find an unused loopback port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 0))
    port: int = int(s.getsockname()[1])
    s.close()
    return port


# ---------------------------------------------------------------------------
# Tool-module import side effect
# ---------------------------------------------------------------------------
# Eagerly import the tool modules so their @mcp.tool decorators run at
# package import time. Without this, mcp.list_tools() returns empty
# until something else imports the tool modules — which produces flaky
# tests and a confusing "no tools" startup state for the bridge.
#
# Imports go at the BOTTOM of this module to avoid a circular import
# (tool modules import `mcp` from here).
# ---------------------------------------------------------------------------


def _import_tool_modules() -> None:
    """Import the four tools_* modules so @mcp.tool() decorators register."""
    # Local imports — these are side-effecting registrations only.
    from scieasy.ai.agent.mcp import (
        tools_authoring,
        tools_inspection,
        tools_qa,
        tools_workflow,
    )

    _ = (tools_workflow, tools_authoring, tools_inspection, tools_qa)


_import_tool_modules()


__all__ = ["MCPServer", "mcp"]


# Silence ruff about unused import sentinel (cross-platform).
_ = os
