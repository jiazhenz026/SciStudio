"""RunContext — thread/task-local context for the active run (ADR-038 §5.1).

Provides an opt-in side-channel that blocks (or framework helpers) can use to
discover the ``run_id`` and ``block_execution_id`` they are executing under,
without changing the block contract. Block authors do NOT need to use this —
the lineage system records everything externally per ADR-038 §3.2. It exists
for cases where the framework needs to stamp ``FrameworkMeta.lineage_id``
(Phase D38-2.3) or similar wiring.

Implemented as a :class:`contextvars.ContextVar` so it survives across
asyncio task boundaries that copy the active context (default behaviour for
``asyncio.create_task``).
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class RunContext:
    """Immutable record of the currently-active run/block execution."""

    run_id: str
    block_execution_id: str | None = None


_active: ContextVar[RunContext | None] = ContextVar("scistudio_run_context", default=None)


def get_run_context() -> RunContext | None:
    """Return the active :class:`RunContext`, or ``None`` if outside a run."""
    return _active.get()


def set_run_context(ctx: RunContext | None) -> Token[RunContext | None]:
    """Set the active :class:`RunContext` and return a reset token."""
    return _active.set(ctx)


def reset_run_context(token: Token[RunContext | None]) -> None:
    """Reset the active context to the value before the matching ``set_*`` call."""
    _active.reset(token)
