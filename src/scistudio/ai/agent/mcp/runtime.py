"""Reusable MCP runtime setup, shared by the FastAPI lifespan and the standalone bridge.

T-ECA-205 + #787; adapted for ADR-040 FastMCP migration (S40a skeleton).

The FastAPI process and the standalone ``scistudio mcp-bridge`` (used by
external CLIs like ``claude`` and ``codex``) both need to:

1. Build a :class:`scistudio.blocks.registry.BlockRegistry` scoped to the
   active project (plus the user-wide ``~/.scistudio/blocks`` and
   entry-point plugin packages).
2. Build a :class:`scistudio.core.types.registry.TypeRegistry` populated
   with builtins, entry-point plugins, and the same project/user drop-in
   type dirs (ADR-053 FR-059; before that it saw no drop-in type at all).
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
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scistudio.ai.agent.mcp.server import MCPServer
    from scistudio.blocks.registry import BlockRegistry
    from scistudio.core.types.registry import TypeRegistry

logger = logging.getLogger(__name__)


def dropin_revision(scan_dirs: Iterable[Path]) -> tuple[tuple[str, int, int], ...]:
    """Return a cheap signature of the drop-in files *scan_dirs* would register.

    ADR-053 FR-065's cross-process half. A process that holds registries has no
    way to be *told* that another process wrote into a shared drop-in directory
    — the user library is a directory on disk, not a channel — so the signal is
    the directory content itself: every ``.py`` file's path, size, and
    modification time. Comparing two signatures answers "has anything a scan
    would read changed since I last scanned?" without importing anything.

    Name, size, and ``st_mtime_ns`` together rather than a directory mtime
    alone: adding or removing a file changes the directory's own mtime, but
    *editing* one does not, and an overwrite that keeps the byte count still
    moves the file's mtime. Reading a handful of ``stat`` results per tool call
    is cheap next to the registry scan it avoids.

    Unreadable or missing directories contribute nothing, matching both
    registries' behaviour of skipping absent scan directories.

    Two shapes beyond a plain ``<name>.py`` have to be watched, because both
    are things a scan would read (``docs/audit/2026-08-07-adr-053-spec1-write-path.md``,
    P3-9 and P3-2):

    * ``<name>/__init__.py``. A package-shaped drop-in type is a first-class
      citizen of the FR-016 guard, so it must not be invisible to the detector
      that decides whether to re-scan.
    * ``<NAME>.PY``. Windows ``glob("*.py")`` is case-insensitive, so an
      uppercase suffix is a live drop-in there, and a case-sensitive comparison
      here meant editing one never moved the signature. The product refuses to
      *create* such a file, but a user can still place one by hand.
    """
    entries: list[tuple[str, int, int]] = []
    for directory in scan_dirs:
        try:
            children = sorted(directory.iterdir())
        except OSError:
            continue
        for entry in children:
            watched = entry
            if entry.is_dir():
                watched = entry / "__init__.py"
                if not watched.is_file():
                    continue
            elif entry.suffix.lower() != ".py":
                continue
            try:
                stat = watched.stat()
            except OSError:
                continue
            entries.append((str(watched), stat.st_size, stat.st_mtime_ns))
    return tuple(entries)


@dataclass
class StandaloneMCPRuntime:
    """Minimal :class:`MCPContext` implementation for the standalone bridge.

    Satisfies the structural Protocol declared in
    :mod:`scistudio.ai.agent.mcp._context`:

    * ``block_registry`` and ``type_registry`` — populated by
      :func:`make_mcp_runtime`, and re-read through a staleness check (below).
    * ``project_dir`` — the project root passed by the caller, or
      ``None`` when no project is open.
    * ``workflow_runs`` — empty dict; the bridge has no scheduler.

    **ADR-053 FR-065 — the bridge's invalidation channel.** Under FastAPI the
    context is a read-through adapter over the live ``ApiRuntime``, so anything
    that refreshes the API's registries is immediately visible to the agent.
    The standalone bridge had no equivalent: it built its two registries once
    in :func:`make_mcp_runtime` and then held them for the whole session, so a
    block or type written by any other process — including through the user
    library endpoint — stayed invisible until the bridge was restarted.

    The two registry attributes are therefore properties that first compare a
    :func:`dropin_revision` signature of the drop-in directories against the
    one taken at the last scan, and rebuild in place when it differs. That is
    the channel: the shared directory *is* the message, and it works in both
    directions without either process knowing the other exists.

    The check is deliberately here rather than inside the registries. A
    registry is a passive container that scans when asked; deciding *when* the
    answer went stale is a property of holding one across a long-lived session,
    which is what this class does and what a per-request API handler does not.

    The FastAPI variant additionally exposes ``start_workflow``. Standalone
    mode doesn't drive execution from MCP tools, so we leave that as a no-op —
    the runtime-dependent ``run_workflow`` tool will surface a clear error if
    invoked here.

    # TODO(#1012): I40a Phase 2a may need to add ``ai_block_run_dir``
    #   here to satisfy the MCPContext Protocol surface that
    #   tools_workflow.finish_ai_block reads. Today
    #   ``_resolve_ai_block_run_dir`` falls back to the env var when the
    #   attribute is absent, so this is a NICE-TO-HAVE not a blocker.
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a. Followup: #1012.
    """

    _block_registry: BlockRegistry
    _type_registry: TypeRegistry
    _project_dir: Path | None = None
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    # ADR-040 Addendum 5 / #1488: satisfies the ``active_workflow_id``
    # member of the MCPContext Protocol. Standalone bridges have no
    # live GUI editor, so the value is always ``None`` — callers that
    # need the live id must run against the FastAPI ``_RuntimeAdapter``.
    active_workflow_id: str | None = None
    _dropin_revision: tuple[tuple[str, int, int], ...] = ()

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir

    def dropin_scan_dirs(self) -> tuple[Path, ...]:
        """Return every drop-in directory this runtime's registries read."""
        from scistudio.core.dropins import block_scan_dirs, type_scan_dirs

        return (*block_scan_dirs(self._project_dir), *type_scan_dirs(self._project_dir))

    def sync_dropins(self) -> bool:
        """Rebuild both registries when the drop-in directories have changed.

        Returns whether a rebuild happened. Idempotent and safe to call before
        every registry read: when nothing moved it is a handful of ``stat``
        calls and no scan.
        """
        current = dropin_revision(self.dropin_scan_dirs())
        if current == self._dropin_revision:
            return False
        self._dropin_revision = current
        self._block_registry.hot_reload()
        self._type_registry.rescan()
        logger.info("StandaloneMCPRuntime: drop-in change detected; registries rebuilt (FR-065)")
        return True

    @property
    def block_registry(self) -> BlockRegistry:
        self.sync_dropins()
        return self._block_registry

    @property
    def type_registry(self) -> TypeRegistry:
        self.sync_dropins()
        return self._type_registry

    def start_workflow(self, workflow_id: str) -> object:
        # Standalone bridges intentionally don't host the scheduler.
        # Users who need execution should run the SciStudio backend.
        raise RuntimeError(
            "run_workflow is only available when the SciStudio backend is running. "
            "Start the backend (`scistudio gui` or `scistudio serve`) and re-launch "
            "the bridge; it will reconnect to the live backend."
        )


def _build_block_registry(project_dir: Path | None) -> BlockRegistry:
    """Scan project + user blocks plus plugins; dirs from ``core.dropins``."""
    from scistudio.blocks.registry import BlockRegistry
    from scistudio.core.dropins import register_block_scan_dirs

    registry = BlockRegistry()
    register_block_scan_dirs(registry, project_dir)
    registry.scan()
    return registry


def _build_type_registry(project_dir: Path | None) -> TypeRegistry:
    """Scan project + user types plus plugins; dirs from ``core.dropins``.

    ADR-053 FR-059: this used to register no scan directory at all.
    """
    from scistudio.core.dropins import register_type_scan_dirs
    from scistudio.core.types.registry import TypeRegistry

    registry = TypeRegistry()
    register_type_scan_dirs(registry, project_dir)
    registry.scan_all()
    return registry


def make_mcp_runtime(project_dir: Path | None) -> StandaloneMCPRuntime:
    """Build a populated :class:`StandaloneMCPRuntime`.

    Equivalent to the setup the FastAPI lifespan performs: both registries
    scan builtins, entry-point plugins, and the project/user drop-in dirs
    resolved by :mod:`scistudio.core.dropins` (ADR-053 FR-057). Before ADR-053
    this docstring claimed drop-in coverage for both registries while
    :func:`_build_type_registry` registered no directory at all (FR-059).
    Does *not* install the global context — callers are responsible for that
    so they can also tear it down.

    Parameters
    ----------
    project_dir
        Active project root, or ``None`` when no project is open. When
        ``None``, project-scoped MCP tools (most of them) will fail
        with a clear "no project open" error from
        :func:`scistudio.ai.agent.mcp._context._resolve_project_root`. The
        user tier (``~/.scistudio/blocks`` and ``~/.scistudio/types``) is
        scanned either way (FR-060).

    Returns
    -------
    StandaloneMCPRuntime
        A runtime ready to be passed to ``_context.set_context``.
    """
    from scistudio.core.dropins import block_scan_dirs, type_scan_dirs

    block_registry = _build_block_registry(project_dir)
    type_registry = _build_type_registry(project_dir)
    return StandaloneMCPRuntime(
        _block_registry=block_registry,
        _type_registry=type_registry,
        _project_dir=project_dir,
        # ADR-053 FR-065: seed the signature from the state the two scans above
        # just read, so the first tool call does not rescan for no reason.
        _dropin_revision=dropin_revision((*block_scan_dirs(project_dir), *type_scan_dirs(project_dir))),
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
    # ADR-053 FR-065 made the two registries read-through properties, which a
    # Protocol declaring them as plain variables reads as read-only. The FastAPI
    # ``_RuntimeAdapter`` has carried the same ignore since it was written for
    # the same reason; both satisfy the surface every tool actually uses.
    _context.set_context(runtime)  # type: ignore[arg-type]

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
    "dropin_revision",
    "make_mcp_runtime",
    "start_inprocess_server",
    "stop_inprocess_server",
]
