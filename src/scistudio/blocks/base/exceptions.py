"""Typed exceptions raised by blocks to signal terminal states to the engine.

The worker subprocess catches these and forwards the signal to the engine via
the ``final_state`` field on its stdout JSON envelope (see
``scistudio.engine.runners.terminal_state``). The engine-owned scheduler is the
authoritative state machine (ADR-018 §8.1 ``DAGScheduler.set_state``); blocks
do not track their own state.
"""

from __future__ import annotations

from scistudio.stability import provisional


@provisional(since="0.3.1")
class BlockCancelledByAppError(Exception):
    """Block ran an external app that exited without producing output.

    Raised from :meth:`AppBlock.run` when the FileWatcher detects the external
    process terminated before any output was written. The worker translates
    this into ``final_state="cancelled"`` on the stdout envelope so the
    scheduler records the block in ``BlockState.CANCELLED`` via the existing
    ``BlockTerminalStateReportedError`` path (#681).
    """
