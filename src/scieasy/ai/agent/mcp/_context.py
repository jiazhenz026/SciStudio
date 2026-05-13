"""Runtime context for MCP tools.

T-ECA-202..205. The 25 MCP tools need to talk to SciEasy's in-process
runtime — the :class:`BlockRegistry`, :class:`TypeRegistry`, live
workflow runs, the data catalog, the lineage / metadata stores, and the
project root. The natural carrier of all those things is
:class:`scieasy.api.runtime.ApiRuntime`, but two problems prevent the
MCP tools from importing it directly:

1. **Test isolation.** Unit tests need to inject a synthetic context
   without spinning up a full FastAPI app.
2. **Layering.** ``ai/`` cannot import from ``api/`` (the import-linter
   contracts in ``pyproject.toml`` forbid it — ``api`` sits *above*
   ``ai`` in the dep graph).

Resolution: this module exposes a small typing-only
:class:`MCPContext` Protocol plus a global getter/setter pair. The
FastAPI lifespan handler in :func:`scieasy.api.app.lifespan` calls
:func:`set_context` with the live ``ApiRuntime`` (which satisfies the
Protocol structurally — no inheritance required). Tools fetch the
current context via :func:`get_context` and act on it.

For unit tests, the test fixture builds a tiny in-memory context and
calls :func:`set_context` for the duration of the test.

The Protocol is **structural**: callers only need attributes / methods
the tools actually reach for. Anything broader would create a hidden
coupling.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from scieasy.blocks.registry import BlockRegistry
    from scieasy.core.types.registry import TypeRegistry


class MCPContext(Protocol):
    """Structural Protocol every MCP tool relies on.

    Production: implemented by :class:`scieasy.api.runtime.ApiRuntime`.
    Tests: implemented by a lightweight stub.
    """

    block_registry: BlockRegistry
    type_registry: TypeRegistry
    """The two registries the tools query."""

    @property
    def project_dir(self) -> Path | None:
        """Active project workspace root, or ``None`` when no project open."""
        ...


_current_context: MCPContext | None = None


def set_context(ctx: MCPContext | None) -> None:
    """Install the global MCP runtime context.

    Called by:

    * :func:`scieasy.api.app.lifespan` on startup (passes the
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
            "Call scieasy.ai.agent.mcp._context.set_context(...) first "
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
    via the path argument.

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
        raise PermissionError(f"Path {target} resolves outside project root {root}") from exc
    return target_resolved


# Re-export for test convenience.
__all__ = [
    "MCPContext",
    "_resolve_project_root",
    "_safe_under",
    "get_context",
    "get_optional_context",
    "set_context",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - typing only
    raise AttributeError(name)
