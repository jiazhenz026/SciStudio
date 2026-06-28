"""Typed exceptions a block raises to tell the engine it reached a terminal state.

The worker subprocess catches these and reports the outcome to the engine on its
result envelope. The engine, not the block, owns the authoritative run-state
machine, so a block signals an outcome by raising rather than by setting state.
"""

from __future__ import annotations

from scistudio.stability import provisional


@provisional(since="0.3.1")
class BlockCancelledByAppError(Exception):
    """Raised when a block's external application exits without producing output.

    A block that launches a separate desktop application raises this from its
    ``run`` method when the application closes before writing any result. The
    worker reports it to the engine as a cancellation, so the run is recorded as
    cancelled rather than failed.
    """
