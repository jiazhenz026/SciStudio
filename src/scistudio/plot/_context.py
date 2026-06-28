"""Injected runtime context for the plot engine (#1824).

The plot engine is a first-class feature (``scistudio.plot``), not an AI-agent
concern. It must NOT import ``scistudio.ai.agent.mcp``. Instead, each caller
injects a small context object that satisfies :class:`PlotRuntimeContext`:

- the REST route passes its ``ApiRuntime`` (which exposes ``project_dir`` plus
  the registries / runs / plot-artifact registrar);
- the MCP plot tools pass the live MCP context (``mcp._context.get_context()``).

The engine reads only the members declared here, and the path-safety helpers
(:func:`safe_under`, :func:`resolve_project_root`, :func:`resolve_project_path`)
are pure — relocated from ``mcp._context`` so nothing under ``scistudio.plot``
depends on the AI layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PlotRuntimeContext(Protocol):
    """The minimal context the plot engine reads (ADR-052 §9, #1824).

    Both the FastAPI ``ApiRuntime`` and the in-process MCP context satisfy this
    structurally. Members are duck-typed: the engine reads them defensively via
    ``getattr`` where a member may be absent (e.g. a lightweight test stub).
    """

    @property
    def project_dir(self) -> Path | None:
        """Active project workspace root, or ``None`` when no project is open."""
        ...

    #: Block registry used to resolve a block type's output ports (target discovery).
    block_registry: Any
    #: Type registry used to normalise recorded core types for the harness input.
    type_registry: Any
    #: Mapping ``run_id -> run`` whose ``scheduler._block_outputs`` carry the bound output.
    workflow_runs: Any
    #: Callable registering a produced plot artifact so MCP callers get a preview
    #: target. Declared ``Any`` (not a typed method) because the engine duck-types
    #: it via ``getattr`` and callers' concrete signatures differ; it is optional
    #: in practice — registration is skipped when the context does not provide it.
    register_plot_artifact: Any


def resolve_project_root(ctx: PlotRuntimeContext) -> Path:
    """Return the project root, raising when no project is open.

    Relocated from ``mcp._context._resolve_project_root`` (#1824); takes the
    injected context instead of reaching a global singleton.
    """
    root = ctx.project_dir
    if root is None:
        raise RuntimeError("No project is currently open. Open a project before running plot operations.")
    return root


def safe_under(root: Path, target: Path) -> Path:
    """Resolve *target* against *root* and reject paths that escape it.

    Pure path-confinement (relocated verbatim from ``mcp._context._safe_under``,
    #1824). Both sides are normalised through :meth:`Path.resolve` (``realpath``)
    so the comparison is correct on macOS (``/tmp`` → ``/private/tmp``, NFD/NFC).

    Raises :class:`PermissionError` if *target* resolves outside *root*.
    """
    root_resolved = root.resolve()
    target_resolved = (root_resolved / target).resolve() if not target.is_absolute() else target.resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PermissionError(f"Path {target} resolves outside project root {root}") from exc
    return target_resolved


def resolve_project_path(ctx: PlotRuntimeContext, target: str | Path) -> Path:
    """Resolve a user-supplied path against the injected project root, rejecting traversal.

    Composes :func:`resolve_project_root` (raises if no project) and
    :func:`safe_under` (resolves + rejects escapes). Relocated from
    ``mcp._context._resolve_project_path`` to take an explicit context (#1824).
    """
    root = resolve_project_root(ctx)
    return safe_under(root, Path(target))


__all__ = [
    "PlotRuntimeContext",
    "resolve_project_path",
    "resolve_project_root",
    "safe_under",
]
