"""Reusable MCP runtime setup, shared by the FastAPI lifespan and the standalone bridge.

T-ECA-205 + #787; adapted for ADR-040 FastMCP migration (S40a skeleton).

The FastAPI process and the standalone ``scieasy mcp-bridge`` (used by
external CLIs like ``claude`` and ``codex``) both need to:

1. Build a :class:`scieasy.blocks.registry.BlockRegistry` scoped to the
   active project (plus the user-wide ``~/.scieasy/blocks`` and the
   monorepo when ``SCIEASY_DEV=1``).
2. Build a :class:`scieasy.core.types.registry.TypeRegistry` populated
   with builtins (and plugins).
3. Install a :class:`MCPContext` against ``_context.set_context`` so the
   26 MCP tools can reach those registries plus the project root.
4. Stand up an :class:`MCPServer` (FastMCP-backed per ADR-040 §3.1)
   listening on the project-local socket.

Previously this lived inline inside ``api/app.py::lifespan``. Issue #787
extracted it here so the standalone bridge can do exactly the same setup
without depending on FastAPI / uvicorn.

Important layering note: this module sits inside the AI layer and must
not import from ``scieasy.api`` (the import-linter contracts forbid
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
    from scieasy.ai.agent.mcp.server import MCPServer
    from scieasy.blocks.registry import BlockRegistry
    from scieasy.core.types.registry import TypeRegistry

logger = logging.getLogger(__name__)


@dataclass
class StandaloneMCPRuntime:
    """Minimal :class:`MCPContext` implementation for the standalone bridge.

    Satisfies the structural Protocol declared in
    :mod:`scieasy.ai.agent.mcp._context`:

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

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir

    def start_workflow(self, workflow_id: str) -> object:
        # Standalone bridges intentionally don't host the scheduler.
        # Users who need execution should run the SciEasy backend.
        raise RuntimeError(
            "run_workflow is only available when the SciEasy backend is running. "
            "Start the backend (`scieasy gui` or `scieasy serve`) and re-launch "
            "the bridge; it will reconnect to the live backend."
        )


def _build_block_registry(project_dir: Path | None) -> BlockRegistry:
    """Scan project-local + user-wide blocks (and monorepo in dev)."""
    from scieasy.blocks.registry import BlockRegistry

    registry = BlockRegistry()
    if project_dir is not None:
        registry.add_scan_dir(project_dir / "blocks")
    registry.add_scan_dir(Path.home() / ".scieasy" / "blocks")
    registry.scan(include_monorepo=os.environ.get("SCIEASY_DEV") == "1")
    return registry


def _build_type_registry() -> TypeRegistry:
    """Scan builtin + plugin types (and monorepo in dev)."""
    from scieasy.core.types.registry import TypeRegistry

    registry = TypeRegistry()
    registry.scan_all(include_monorepo=os.environ.get("SCIEASY_DEV") == "1")
    return registry


def make_mcp_runtime(project_dir: Path | None) -> StandaloneMCPRuntime:
    """Build a populated :class:`StandaloneMCPRuntime`.

    Equivalent to the inline setup the FastAPI lifespan performs (block
    + type registry scans, optional monorepo inclusion via
    ``SCIEASY_DEV``). Does *not* install the global context — callers
    are responsible for that so they can also tear it down.

    Parameters
    ----------
    project_dir
        Active project root, or ``None`` when no project is open. When
        ``None``, project-scoped MCP tools (most of them) will fail
        with a clear "no project open" error from
        :func:`scieasy.ai.agent.mcp._context._resolve_project_root`.

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
    ``~/.scieasy/.scieasy/mcp.sock`` — same fallback the lifespan uses.
    """
    base = project_dir if project_dir is not None else Path.home() / ".scieasy"
    return base / ".scieasy" / "mcp.sock"


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

    from scieasy.ai.agent.mcp import _context
    from scieasy.ai.agent.mcp.server import MCPServer

    runtime = make_mcp_runtime(project_dir)
    _context.set_context(runtime)

    if socket_path is None:
        # Per-process socket under the project's .scieasy/ dir when a
        # project is open, or a temp dir otherwise. Suffix with the PID
        # so concurrent standalone bridges don't fight over the path.
        if project_dir is not None:
            base = project_dir / ".scieasy"
            base.mkdir(parents=True, exist_ok=True)
            socket_path = base / f"mcp-bridge-{os.getpid()}.sock"
        else:
            socket_path = Path(tempfile.gettempdir()) / f"scieasy-mcp-bridge-{os.getpid()}.sock"

    server = MCPServer(
        socket_path=socket_path,
        project_dir=project_dir if project_dir is not None else Path.home() / ".scieasy",
    )
    await server.start()
    logger.info("Standalone MCP runtime started for project_dir=%s", project_dir)
    return server, runtime


async def stop_inprocess_server(server: MCPServer) -> None:
    """Stop the server started by :func:`start_inprocess_server` and clear context."""
    from scieasy.ai.agent.mcp import _context

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
