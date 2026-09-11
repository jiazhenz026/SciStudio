"""Runtime context for MCP tools.

T-ECA-202..205. The 25 MCP tools need to talk to SciStudio's in-process
runtime — the :class:`BlockRegistry`, :class:`TypeRegistry`, live
workflow runs, the data catalog, the lineage / metadata stores, and the
project root. The natural carrier of all those things is
:class:`scistudio.api.runtime.ApiRuntime`, but two problems prevent the
MCP tools from importing it directly:

1. **Test isolation.** Unit tests need to inject a synthetic context
   without spinning up a full FastAPI app.
2. **Layering.** ``ai/`` cannot import from ``api/`` (the import-linter
   contracts in ``pyproject.toml`` forbid it — ``api`` sits *above*
   ``ai`` in the dep graph).

Resolution: this module exposes a small typing-only
:class:`MCPContext` Protocol plus a global getter/setter pair. The
FastAPI lifespan handler in :func:`scistudio.api.app.lifespan` calls
:func:`set_context` with the live ``ApiRuntime`` (which satisfies the
Protocol structurally — no inheritance required). Tools fetch the
current context via :func:`get_context` and act on it.

For unit tests, the test fixture builds a tiny in-memory context and
calls :func:`set_context` for the duration of the test.

The Protocol is **structural**: callers only need attributes / methods
the tools actually reach for. Anything broader would create a hidden
coupling.

ADR-055 Spec 2 (#2279) adds two *optional capabilities* beside the core
Protocol, read through :func:`get_project_files` and
:func:`get_process_registry` so a context without them (the standalone
bridge, a unit-test stub) degrades to an explicit "unavailable" instead of an
``AttributeError``:

* ``project_files`` (:class:`ProjectFileWriter`) — the editor's shared write
  path (atomic write, ``file.changed``, block reload). Production:
  ``scistudio.api.runtime._file_writes.ProjectFileService``.
* ``process_registry`` (:class:`CommandProcessRegistry`) — the registry the
  backend's shutdown ``terminate_all`` runs on, so managed ``run_command``
  processes stop with the backend.

It also adds the bridge-call marker (:func:`bridge_call_scope` /
:func:`invoked_through_bridge`): the WebMCP route sets it around dispatch so a
tool can apply a rule to bridge calls without changing local-transport
behavior.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import Context, ContextVar, copy_context
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from scistudio.blocks.registry import BlockRegistry
    from scistudio.core.types.registry import TypeRegistry


class MCPContext(Protocol):
    """Structural Protocol every MCP tool relies on.

    Production: implemented by :class:`scistudio.api.runtime.ApiRuntime`.
    Tests: implemented by a lightweight stub.
    """

    block_registry: BlockRegistry
    type_registry: TypeRegistry
    """The two registries the tools query."""

    @property
    def project_dir(self) -> Path | None:
        """Active project workspace root, or ``None`` when no project open."""
        ...

    # ADR-040 Addendum 5 / #1488: the workflow id the GUI is currently
    # editing. ``None`` when no workflow is open or when no project is
    # active. Surfaced to the chat agent via the
    # ``get_active_workflow_context`` MCP tool so the agent has VS Code
    # Copilot-style editor awareness without per-message context bloat.
    active_workflow_id: str | None


class ProjectFileWriter(Protocol):
    """Optional capability: the shared project-file write path (ADR-055 Spec 2 FR-005).

    Every method takes absolute targets, confines them to the active project,
    and returns a plain dict whose ``status`` is ``"ok"`` or ``"conflict"``
    (with ``condition``, ``message``, and the expected/current state
    versions). Disk failures raise.
    """

    def state_version(self, target: Path) -> int | None:
        """Current state version of a project file, ``None`` outside the project."""
        ...

    async def write_text(
        self,
        target: Path,
        content: str,
        *,
        expected_state_version: int | None = None,
        create_only: bool = False,
        require_existing: bool = False,
        create_parents: bool = False,
        changed_by: str = ...,
    ) -> dict[str, Any]: ...

    async def make_directory(self, target: Path, *, parents: bool = False, changed_by: str = ...) -> dict[str, Any]: ...

    async def delete(
        self,
        target: Path,
        *,
        recursive: bool = False,
        expected_state_version: int | None = None,
        changed_by: str = ...,
    ) -> dict[str, Any]: ...

    async def move(
        self,
        source_path: Path,
        destination: Path,
        *,
        create_parents: bool = False,
        expected_state_version: int | None = None,
        changed_by: str = ...,
    ) -> dict[str, Any]: ...


class CommandProcessRegistry(Protocol):
    """Optional capability: the backend's process registry (ADR-019, ADR-055 Spec 2 FR-009).

    Structurally :class:`scistudio.engine.runners.process_handle.ProcessRegistry`.
    """

    def register(self, handle: Any) -> None: ...

    def deregister(self, workflow_id: str, block_id: str) -> None: ...

    def get_handle(self, workflow_id: str, block_id: str) -> Any: ...

    def active_handles(self) -> list[Any]: ...


def get_project_files(ctx: Any) -> ProjectFileWriter | None:
    """Return the context's shared write path, or ``None`` when it has none."""
    return getattr(ctx, "project_files", None)


def get_process_registry(ctx: Any) -> CommandProcessRegistry | None:
    """Return the context's backend process registry, or ``None`` when it has none."""
    return getattr(ctx, "process_registry", None)


_BRIDGE_CALL: ContextVar[bool] = ContextVar("scistudio_webmcp_bridge_call", default=False)


@contextmanager
def bridge_call_scope() -> Iterator[None]:
    """Mark the enclosed tool dispatch as arriving through the WebMCP bridge."""
    token = _BRIDGE_CALL.set(True)
    try:
        yield
    finally:
        _BRIDGE_CALL.reset(token)


def invoked_through_bridge() -> bool:
    """True inside a :func:`bridge_call_scope` (a WebMCP bridge dispatch)."""
    return _BRIDGE_CALL.get()


def outside_bridge_context() -> Context:
    """A copy of the current context with the bridge-call marker cleared.

    For background tasks a dispatch spawns (a ``run_command`` supervisor): they
    outlive the call and must not look like bridge calls to anything they run.
    """
    context = copy_context()
    context.run(_BRIDGE_CALL.set, False)
    return context


_current_context: MCPContext | None = None


def set_context(ctx: MCPContext | None) -> None:
    """Install the global MCP runtime context.

    Called by:

    * :func:`scistudio.api.app.lifespan` on startup (passes the
      ``ApiRuntime``).
    * Unit tests (passes a stub).
    * Teardown paths (passes ``None``).
    """
    global _current_context
    _current_context = ctx


def get_context() -> MCPContext:
    """Return the active :class:`MCPContext`.

    Raises
    ------
    RuntimeError
        If no context has been installed. This means the tool was
        invoked outside of a FastAPI request handler / test fixture —
        which is a programmer error.
    """
    if _current_context is None:
        raise RuntimeError(
            "MCP tool invoked without an active runtime context. "
            "Call scistudio.ai.agent.mcp._context.set_context(...) first "
            "(the FastAPI lifespan handler does this in production)."
        )
    return _current_context


def get_optional_context() -> MCPContext | None:
    """Return the active context or ``None`` (no exception)."""
    return _current_context


def _resolve_project_root(ctx: MCPContext) -> Path:
    """Return the project root for tools that need a workspace.

    Raises :class:`RuntimeError` when no project is open — most tools
    are project-scoped and there is no meaningful behaviour without
    one.
    """
    root = ctx.project_dir
    if root is None:
        raise RuntimeError("No project is currently open. Open a project before invoking project-scoped MCP tools.")
    return root


def _safe_under(root: Path, target: Path) -> Path:
    """Resolve *target* and reject paths that escape *root*.

    Used by tools that accept user-supplied paths (``get_doc``,
    ``get_workflow``, etc.) so the agent cannot read arbitrary files
    via the path argument. *root* is whatever the caller is confining to —
    usually the active project root, but ``promote_to_user_library`` passes the
    user library root — so the refusal names *root* rather than asserting it is
    a project (``docs/audit/2026-08-07-adr-053-spec1-write-path.md`` P3-4).

    Both *root* and *target* are normalised through :func:`os.path.realpath`
    (via :meth:`Path.resolve`) before comparison. This is critical on
    macOS where ``/tmp`` is a symlink to ``/private/tmp`` and where the
    filesystem uses NFD Unicode normalisation while strings may be NFC:
    string-comparison would treat the resolved and unresolved forms as
    different, but ``realpath`` canonicalises both sides so
    :meth:`Path.relative_to` works correctly.

    Raises
    ------
    PermissionError
        If *target* resolves outside *root*.
    """
    root_resolved = root.resolve()
    target_resolved = (root_resolved / target).resolve() if not target.is_absolute() else target.resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PermissionError(f"Path {target} resolves outside {root}") from exc
    return target_resolved


def _resolve_project_path(target: str | Path) -> Path:
    """Resolve a user-supplied path against the active project root.

    Issue #790: MCP tools that accept a ``path`` argument from the agent
    must resolve it against ``ctx.project_dir``, not the backend process's
    CWD. They must also reject any path that escapes the project root
    (path-traversal hardening — the agent could otherwise scribble onto
    ``/etc/passwd`` or ``~/.ssh/authorized_keys``).

    This helper composes the two existing primitives — :func:`_resolve_project_root`
    (raises if no project is open) and :func:`_safe_under` (resolves and
    rejects traversal) — into the single call most tools want.

    Cross-platform notes:

    * On macOS, ``Path.resolve`` calls :func:`os.path.realpath` which
      follows ``/tmp → /private/tmp`` and canonicalises NFD/NFC Unicode.
      The returned path is therefore safe to compare against other
      resolved paths.
    * On Windows, drive-letter mismatches between ``root`` and absolute
      ``target`` raise :class:`PermissionError` via the ``relative_to``
      check in :func:`_safe_under`.
    * Absolute paths under the project root are accepted as-is; anything
      else (absolute paths outside the project, ``..``-escaping relative
      paths) is rejected.

    Parameters
    ----------
    target
        The user-supplied path. May be relative (resolved against
        ``project_dir``) or absolute (must already be under ``project_dir``).

    Returns
    -------
    Path
        The absolute, fully-resolved path inside the project root.

    Raises
    ------
    RuntimeError
        If no project is currently open.
    PermissionError
        If the target resolves outside the project root.
    """
    ctx = get_context()
    root = _resolve_project_root(ctx)
    return _safe_under(root, Path(target))


# Re-export for test convenience.
__all__ = [
    "CommandProcessRegistry",
    "MCPContext",
    "ProjectFileWriter",
    "_resolve_project_path",
    "_resolve_project_root",
    "_safe_under",
    "bridge_call_scope",
    "get_context",
    "get_optional_context",
    "get_process_registry",
    "get_project_files",
    "invoked_through_bridge",
    "outside_bridge_context",
    "set_context",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - typing only
    raise AttributeError(name)
