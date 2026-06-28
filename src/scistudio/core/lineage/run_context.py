"""RunContext — thread/task-local handle to the currently active run.

An opt-in side-channel that framework helpers can use to discover the
``run_id`` and ``block_execution_id`` they are running under, without changing
the block contract. Block authors do not need this — the lineage system records
everything externally. It exists for the few places where the framework must
stamp a data object with the run that produced it.

Implemented with :class:`contextvars.ContextVar` so the active run survives
across asyncio task boundaries that copy the current context.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class RunContext:
    """The currently-active run and block execution.

    Example:
        >>> ctx = RunContext(run_id="run-1")
        >>> ctx.run_id
        'run-1'
        >>> ctx.block_execution_id is None
        True
    """

    run_id: str
    """Identifier of the active run."""
    block_execution_id: str | None = None
    """Identifier of the active block execution, or ``None`` when not inside one."""


_active: ContextVar[RunContext | None] = ContextVar("scistudio_run_context", default=None)


def get_run_context() -> RunContext | None:
    """Return the active :class:`RunContext`, or ``None`` when outside a run.

    Returns:
        The current :class:`RunContext`, or ``None``.
    """
    return _active.get()


def set_run_context(ctx: RunContext | None) -> Token[RunContext | None]:
    """Set the active :class:`RunContext` for the current context.

    Args:
        ctx: The run context to make active, or ``None`` to clear it.

    Returns:
        A token to pass to :func:`reset_run_context` to restore the previous
        value.
    """
    return _active.set(ctx)


def reset_run_context(token: Token[RunContext | None]) -> None:
    """Restore the active context to its value before the matching ``set`` call.

    Args:
        token: The token returned by the matching :func:`set_run_context` call.
    """
    _active.reset(token)
