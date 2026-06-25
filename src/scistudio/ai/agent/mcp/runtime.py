"""Reusable MCP runtime setup, shared by the FastAPI lifespan and the standalone bridge.

T-ECA-205 + #787; adapted for ADR-040 FastMCP migration (S40a skeleton).

The FastAPI process and the standalone ``scistudio mcp-bridge`` (used by
external CLIs like ``claude`` and ``codex``) both need to:

1. Build a :class:`scistudio.blocks.registry.BlockRegistry` scoped to the
   active project (plus the user-wide ``~/.scistudio/blocks`` and
   entry-point plugin packages).
2. Build a :class:`scistudio.core.types.registry.TypeRegistry` populated
   with builtins (and plugins).
3. Install a :class:`MCPContext` against ``_context.set_context`` so the
   26 MCP tools can reach those registries plus the project root.
4. Stand up an :class:`MCPServer` (FastMCP-backed per ADR-040 §3.1)
   listening on the project-local socket.

Previously this lived inline inside ``api/app.py::lifespan``. Issue #787
extracted it here so the standalone bridge can do exactly the same setup
without depending on FastAPI / uvicorn.

Important layering note: this module sits inside the AI layer and must
not import from ``scistudio.api`` (the import-linter contracts forbid
that direction). We therefore build a thin local context class instead
of re-using ``ApiRuntime``.

ADR-040 note: S40a skeleton phase preserves the public surface
(``StandaloneMCPRuntime``, ``make_mcp_runtime``, ``start_inprocess_server``,
``stop_inprocess_server``). The underlying :class:`MCPServer` is now a
FastMCP wrapper whose ``start()``/``stop()`` raise ``NotImplementedError``;
I40a Phase 2a wires the real FastMCP transport into ``start_inprocess_server``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scistudio.ai.agent.mcp.server import MCPServer
    from scistudio.blocks.registry import BlockRegistry
    from scistudio.core.types.registry import TypeRegistry

logger = logging.getLogger(__name__)


@dataclass
class StandaloneMCPRuntime:
    """Minimal :class:`MCPContext` implementation for the standalone bridge.

    Satisfies the structural Protocol declared in
    :mod:`scistudio.ai.agent.mcp._context`:

    * ``block_registry`` and ``type_registry`` — populated by
      :func:`make_mcp_runtime`.
    * ``project_dir`` — the project root passed by the caller, or
      ``None`` when no project is open.
    * ``workflow_runs`` — empty dict; the bridge has no scheduler.

    The FastAPI variant (``ApiRuntime`` wrapped in an inline adapter)
    additionally exposes ``start_workflow``. Standalone mode doesn't
    drive execution from MCP tools, so we leave that as a no-op
    placeholder — the runtime-dependent ``run_workflow`` tool will
    surface a clear error if invoked here.

    # TODO(#1012): I40a Phase 2a may need to add ``ai_block_run_dir``
    #   here to satisfy the MCPContext Protocol surface that
    #   tools_workflow.finish_ai_block reads. Today
    #   ``_resolve_ai_block_run_dir`` falls back to the env var when the
    #   attribute is absent, so this is a NICE-TO-HAVE not a blocker.
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a. Followup: #1012.
    """

    block_registry: BlockRegistry
    type_registry: TypeRegistry
    _project_dir: Path | None = None
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    # ADR-040 Addendum 5 / #1488: satisfies the ``active_workflow_id``
    # member of the MCPContext Protocol. Standalone bridges have no
    # live GUI editor, so the value is always ``None`` — callers that
    # need the live id must run against the FastAPI ``_RuntimeAdapter``.
    active_workflow_id: str | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir

    def start_workflow(self, workflow_id: str) -> object:
        # Standalone bridges intentionally don't host the scheduler.
        # Users who need execution should run the SciStudio backend.
        raise RuntimeError(
            "run_workflow is only available when the SciStudio backend is running. "
            "Start the backend (`scistudio gui` or `scistudio serve`) and re-launch "
            "the bridge; it will reconnect to the live backend."
        )


def _build_block_registry(project_dir: Path | None) -> BlockRegistry:
    """Scan project-local + user-wide blocks plus entry-point plugins."""
    from scistudio.blocks.registry import BlockRegistry

    registry = BlockRegistry()
    if project_dir is not None:
        registry.add_scan_dir(project_dir / "blocks")
    registry.add_scan_dir(Path.home() / ".scistudio" / "blocks")
    registry.scan()
    return registry


def _build_type_registry() -> TypeRegistry:
    """Scan builtin + entry-point plugin types."""
    from scistudio.core.types.registry import TypeRegistry

    registry = TypeRegistry()
    registry.scan_all()
    return registry


def make_mcp_runtime(project_dir: Path | None) -> StandaloneMCPRuntime:
    """Build a populated :class:`StandaloneMCPRuntime`.

    Equivalent to the inline setup the FastAPI lifespan performs (block
    + type registry scans over builtins, entry-point plugins, and
    project/user drop-in dirs). Does *not* install the global context —
    callers are responsible for that so they can also tear it down.

    Parameters
    ----------
    project_dir
        Active project root, or ``None`` when no project is open. When
        ``None``, project-scoped MCP tools (most of them) will fail
        with a clear "no project open" error from
        :func:`scistudio.ai.agent.mcp._context._resolve_project_root`.

    Returns
    -------
    StandaloneMCPRuntime
        A runtime ready to be passed to ``_context.set_context``.
    """
    block_registry = _build_block_registry(project_dir)
    type_registry = _build_type_registry()
    return StandaloneMCPRuntime(
        block_registry=block_registry,
        type_registry=type_registry,
        _project_dir=project_dir,
    )


def default_socket_path(project_dir: Path | None) -> Path:
    """Return the conventional MCP socket path for *project_dir*.

    Matches the location the FastAPI lifespan writes to so the bridge's
    "is the backend already running?" probe can find a real backend's
    socket. When no project is active we fall back to
    ``~/.scistudio/.scistudio/mcp.sock`` — same fallback the lifespan uses.
    """
    base = project_dir if project_dir is not None else Path.home() / ".scistudio"
    return base / ".scistudio" / "mcp.sock"


async def start_inprocess_server(
    project_dir: Path | None,
    socket_path: Path | None = None,
) -> tuple[MCPServer, StandaloneMCPRuntime]:
    """Build a runtime, install it as the global context, and start an MCPServer.

    Intended for the standalone-bridge code path. Returns the server
    handle so the caller can ``await server.stop()`` on teardown.

    The socket path defaults to a per-process temp file rather than
    the conventional project socket — this avoids collision with a
    backend that might be on the verge of starting, and signals
    clearly that this socket belongs to a transient bridge process.
    """
    import tempfile

    from scistudio.ai.agent.mcp import _context
    from scistudio.ai.agent.mcp.server import MCPServer

    runtime = make_mcp_runtime(project_dir)
    _context.set_context(runtime)

    if socket_path is None:
        # Per-process socket under the project's .scistudio/ dir when a
        # project is open, or a temp dir otherwise. Suffix with the PID
        # so concurrent standalone bridges don't fight over the path.
        if project_dir is not None:
            base = project_dir / ".scistudio"
            base.mkdir(parents=True, exist_ok=True)
            socket_path = base / f"mcp-bridge-{os.getpid()}.sock"
        else:
            socket_path = Path(tempfile.gettempdir()) / f"scistudio-mcp-bridge-{os.getpid()}.sock"

        # AF_UNIX ``sun_path`` is capped at 108 bytes on Linux and 104 on
        # macOS. Deep project paths (CI tmp dirs, NixOS profiles, nested
        # pytest fixture trees) routinely overflow. Detect overflow and
        # fall back to a guaranteed-short temp socket. Windows uses
        # AF_INET sockets internally for ipython-style server channels
        # so the path limit doesn't apply, but the check is harmless.
        if len(str(socket_path).encode("utf-8")) > 100:
            socket_path = Path(tempfile.gettempdir()) / f"mcp-{os.getpid()}.sock"

    server = MCPServer(
        socket_path=socket_path,
        project_dir=project_dir if project_dir is not None else Path.home() / ".scistudio",
    )
    await server.start()
    logger.info("Standalone MCP runtime started for project_dir=%s", project_dir)
    return server, runtime


async def stop_inprocess_server(server: MCPServer) -> None:
    """Stop the server started by :func:`start_inprocess_server` and clear context."""
    from scistudio.ai.agent.mcp import _context

    try:
        await server.stop()
    finally:
        _context.set_context(None)


__all__ = [
    "StandaloneMCPRuntime",
    "default_socket_path",
    "make_mcp_runtime",
    "start_inprocess_server",
    "stop_inprocess_server",
]
