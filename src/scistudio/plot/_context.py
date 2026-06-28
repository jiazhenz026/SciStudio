"""Injected runtime context for the plot engine.

The plot engine is a first-class feature (``scistudio.plot``) and must not depend
on the AI-agent layer. Instead of reaching for a global context, each caller
hands the engine a small object that satisfies :class:`PlotRuntimeContext`:

- the REST route passes its ``ApiRuntime`` (which exposes ``project_dir`` plus
  the registries / runs / plot-artifact registrar);
- the plot tools pass the live in-process agent context.

The engine reads only the members declared here, and the path-safety helpers
(:func:`safe_under`, :func:`resolve_project_root`, :func:`resolve_project_path`)
are pure, so nothing under ``scistudio.plot`` depends on the AI layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PlotRuntimeContext(Protocol):
    """The small set of services the plot engine needs from its caller.

    A caller (the REST API runtime or the in-process agent context) passes one of
    these into every plot entry point so the engine never reaches a global. Both
    the FastAPI ``ApiRuntime`` and the in-process agent context satisfy this
    structurally — there is nothing to subclass. Members are read defensively
    with ``getattr`` where one may be absent (for example a lightweight test
    stub), so a context can omit the parts it does not use.
    """

    @property
    def project_dir(self) -> Path | None:
        """Active project workspace root.

        Returns:
            The open project's root directory, or ``None`` when no project is
            open. The path-safety helpers raise when it is ``None``.
        """
        ...

    block_registry: Any
    """Block registry used to resolve a block type's output ports for target discovery."""
    type_registry: Any
    """Type registry used to fold recorded types to core base types for the render input."""
    workflow_runs: Any
    """Mapping of run id to run, whose recorded block outputs hold the bound output."""
    register_plot_artifact: Any
    """Optional callable that registers a produced artifact so callers get a preview target.

    Read defensively (the engine calls it via ``getattr``); when a context does
    not provide it, artifact registration is simply skipped.
    """


def resolve_project_root(ctx: PlotRuntimeContext) -> Path:
    """Return the open project's root directory.

    Use this before any plot file operation to get the workspace root that all
    paths are confined under.

    Args:
        ctx: The injected runtime context.

    Returns:
        The active project root directory.

    Raises:
        RuntimeError: When no project is currently open.

    Example:
        >>> root = resolve_project_root(ctx)  # doctest: +SKIP
        >>> (root / "plots").is_dir()  # doctest: +SKIP
        True
    """
    root = ctx.project_dir
    if root is None:
        raise RuntimeError("No project is currently open. Open a project before running plot operations.")
    return root


def safe_under(root: Path, target: Path) -> Path:
    """Resolve ``target`` against ``root`` and reject paths that escape it.

    A path-confinement guard: it joins a (possibly relative) target onto the
    project root, fully resolves both sides (following symlinks via ``realpath``),
    and only returns the result if it still lives inside the root. This keeps a
    user- or manifest-supplied path from reaching files outside the project. Both
    sides are normalised so the comparison is correct on macOS (``/tmp`` resolves
    to ``/private/tmp``, and Unicode forms are reconciled).

    Args:
        root: The project root the target must stay inside.
        target: A relative or absolute path to confine under ``root``.

    Returns:
        The fully resolved, confined path.

    Raises:
        PermissionError: When ``target`` resolves outside ``root``.

    Example:
        >>> from pathlib import Path
        >>> safe_under(Path("/proj"), Path("plots/p1")).name
        'p1'
    """
    root_resolved = root.resolve()
    target_resolved = (root_resolved / target).resolve() if not target.is_absolute() else target.resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PermissionError(f"Path {target} resolves outside project root {root}") from exc
    return target_resolved


def resolve_project_path(ctx: PlotRuntimeContext, target: str | Path) -> Path:
    """Resolve a user-supplied path against the project root, rejecting traversal.

    A convenience wrapper that combines :func:`resolve_project_root` (raises if no
    project is open) and :func:`safe_under` (resolves and rejects escapes). Reach
    for this whenever a path comes from outside the engine, such as a manifest
    field or a tool argument.

    Args:
        ctx: The injected runtime context.
        target: A relative or absolute path supplied by the caller.

    Returns:
        The fully resolved path, confined under the project root.

    Raises:
        RuntimeError: When no project is currently open.
        PermissionError: When ``target`` resolves outside the project root.
    """
    root = resolve_project_root(ctx)
    return safe_under(root, Path(target))


__all__ = [
    "PlotRuntimeContext",
    "resolve_project_path",
    "resolve_project_root",
    "safe_under",
]
