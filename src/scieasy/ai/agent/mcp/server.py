"""MCP server — FastMCP-backed implementation (ADR-040 §3.1, skeleton).

S40a skeleton. The hand-rolled asyncio JSON-RPC 2.0 server that lived
here in the ADR-033 era is gone (deleted in this PR). FastMCP 3.x owns
the transport, framing, ``inputSchema`` generation, and dispatch.

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
2. FastMCP's native ``serve()`` is blocking; the FastAPI lifespan needs
   an async ``start()`` that returns after the listener is bound, plus a
   non-blocking ``stop()`` for graceful shutdown. The wrapper provides
   that lifecycle shape.

Transport choice (preserved from the hand-rolled era):

* **POSIX** — Unix domain socket at the path provided by the caller
  (default ``{project}/.scieasy/mcp.sock``).
* **Windows** — TCP loopback (``127.0.0.1``, ephemeral port); the port
  is written to ``<socket_path>.port`` next to the socket-path sentinel
  so the bridge can discover it.

I40a (Phase 2a) replaces ``serve()`` with the real FastMCP wiring,
including JSON-RPC initialize / tools/list / tools/call. The S40a
skeleton emits a clear :class:`NotImplementedError` so any accidental
runtime use during the cascade is loud rather than silent.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-scope FastMCP instance — placeholder for S40a.
# ---------------------------------------------------------------------------
#
# TODO(#1012): replace with the real FastMCP instance per ADR-040 §3.1.
#   ```python
#   from fastmcp import FastMCP
#   mcp = FastMCP(name="scieasy-mcp", version="0.1.0")
#   ```
#   Tool modules (``tools_workflow.py`` etc.) import ``mcp`` from this
#   module and decorate their functions with ``@mcp.tool(name=...)``.
#   FastMCP auto-discovers them and exposes via ``mcp.list_tools()``
#   (used by :mod:`scieasy.ai.agent.system_prompt`).
#
#   For S40a skeleton, we expose a sentinel placeholder that tool
#   modules can use as the decorator target. The placeholder mimics the
#   FastMCP decorator API surface so module import succeeds without the
#   real dependency installed during early CI. I40a swaps this out.
#
#   Followup: open as part of ADR-040 Phase 2a I40a impl.
# ---------------------------------------------------------------------------


class _MCPPlaceholder:
    """Skeleton stand-in for :class:`fastmcp.FastMCP`.

    Provides the ``@mcp.tool(...)`` decorator API surface so tool
    modules can be imported during S40a without a real FastMCP dep
    install. The decorator records nothing — bodies raise
    :class:`NotImplementedError` regardless.

    # TODO(#1012): Replace with ``fastmcp.FastMCP(...)`` in I40a Phase 2a.
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    """

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        """No-op decorator factory that returns the wrapped function unchanged."""

        def _decorator(fn: Any) -> Any:
            return fn

        return _decorator

    def list_tools(self) -> list[dict[str, Any]]:
        """Placeholder for FastMCP's tools enumeration.

        # TODO(#1012): I40a replaces this with the real
        #   ``fastmcp.FastMCP.list_tools()`` surface. The renderer in
        #   :mod:`scieasy.ai.agent.system_prompt` iterates the returned
        #   shape and builds the catalogue block.
        """
        raise NotImplementedError(
            "S40a skeleton — FastMCP list_tools() lands in I40a Phase 2a. "
            "TODO(#1012): wire real fastmcp.FastMCP instance per ADR-040 §3.1."
        )


mcp: Any = _MCPPlaceholder()
"""Module-scope FastMCP instance (placeholder in S40a skeleton).

Tool modules import this and decorate their functions:
``@mcp.tool(name="list_blocks") async def list_blocks(...) -> ...``.
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

    The FastMCP migration replaces the hand-rolled asyncio server here
    with a FastMCP runtime, but the call-sites remain unchanged.

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

    async def start(self) -> None:
        """Bind the FastMCP transport and start accepting requests.

        Idempotent: a second call while already started must be a no-op.

        # TODO(#1012): wire fastmcp.FastMCP serve loop per ADR-040 §3.1.
        #   Reference impl plan:
        #     1. POSIX: ``mcp.run_async(transport='unix_socket', path=str(self.socket_path))``
        #        (or equivalent FastMCP API once docs are confirmed).
        #     2. Windows: TCP loopback fallback as in the ADR-033 era;
        #        bind to 127.0.0.1:0, capture port from socket, write
        #        ``<socket_path>.port`` sentinel for the bridge to read.
        #     3. Update ``self._port`` for Windows.
        #     4. Honour ``logger.info("MCPServer: listening on ...")``
        #        for parity with existing operational logs.
        #
        #   Existing callsites:
        #     - ``src/scieasy/api/app.py`` lifespan (FastAPI prod).
        #     - ``src/scieasy/ai/agent/mcp/runtime.py::start_inprocess_server``
        #       (standalone bridge).
        #
        #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
        #   Followup: #1012.
        """
        # Skeleton-phase hygiene (audit F1030-1): NotImplementedError leaked
        # into api/app.py lifespan + standalone mcp-bridge subprocess, breaking
        # backend boot. Behave as a no-op + warn so runtime stays alive; I40a
        # wires the real FastMCP serve loop.
        logger.warning(
            "MCPServer.start() is a S40a skeleton no-op — FastMCP serve loop "
            "lands in I40a Phase 2a per ADR-040 §3.1. TODO(#1012)."
        )

    async def stop(self) -> None:
        """Stop accepting connections and tear down the FastMCP transport.

        # TODO(#1012): wire fastmcp.FastMCP shutdown per ADR-040 §3.1.
        #   Reference impl plan:
        #     1. Cancel the FastMCP serve task.
        #     2. POSIX: ``os.unlink(self.socket_path)`` if present.
        #     3. Windows: remove ``<socket_path>.port`` sentinel.
        #     4. Reset ``self._port`` to None.
        #
        #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
        #   Followup: #1012.
        """
        # Skeleton-phase hygiene (audit F1030-1 companion): symmetric no-op
        # so lifespan shutdown doesn't crash.
        logger.warning(
            "MCPServer.stop() is a S40a skeleton no-op — FastMCP shutdown "
            "lands in I40a Phase 2a per ADR-040 §3.1. TODO(#1012)."
        )

    @property
    def port(self) -> int | None:
        """Bound TCP port on Windows transport, or ``None`` on POSIX."""
        return self._port

    async def serve(self) -> None:
        """Bind transport and block until shutdown (FastMCP-native).

        Convenience entry point for the standalone-bridge ``mcp-bridge``
        subprocess, which wants to block on a single ``await``. Equivalent
        to ``await start()`` followed by waiting for the serve task to
        exit.

        # TODO(#1012): wire fastmcp.FastMCP.run_async per ADR-040 §3.1.
        #   The standalone-bridge subprocess (``scieasy mcp-bridge``)
        #   calls this. I40a wires it as:
        #     ```python
        #     await self.start()
        #     await self._serve_task
        #     ```
        #   or directly:
        #     ```python
        #     await mcp.run_async(transport=...)
        #     ```
        #
        #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
        #   Followup: #1012.
        """
        # Skeleton-phase hygiene (audit F1030-1 companion): the standalone
        # mcp-bridge subprocess awaits serve() and would crash hard on
        # NotImplementedError. Block forever returning no responses; bridge
        # clients see a non-functional MCP but the process stays alive.
        # I40a wires the real blocking serve loop.
        logger.warning(
            "MCPServer.serve() is a S40a skeleton no-op (sleeping forever) — "
            "real FastMCP serve loop lands in I40a Phase 2a per ADR-040 §3.1. "
            "TODO(#1012)."
        )
        await asyncio.Event().wait()
