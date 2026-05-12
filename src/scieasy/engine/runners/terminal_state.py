"""Typed signal that a worker subprocess reported a non-DONE terminal state.

Issue #681: ``Block.transition()`` only mutates the block's in-process state;
the worker subprocess must forward terminal state changes (CANCELLED/ERROR/
SKIPPED) to the parent so the orchestrator records the correct outcome.

The worker emits a ``final_state`` field on its stdout JSON envelope when it
detects a terminal non-DONE state on the block instance after ``run()``
returns. ``LocalRunner.run()`` translates that field into this exception
so the scheduler's existing exception path can finalise the block to the
reported state without changing the public ``BlockRunner`` return contract.
"""

from __future__ import annotations

from typing import Any

from scieasy.blocks.base.state import BlockState


class BlockTerminalStateReportedError(Exception):
    """Raised by a runner when the worker reported a non-DONE terminal state.

    Attributes
    ----------
    state:
        The terminal :class:`BlockState` reported by the worker
        (typically :attr:`BlockState.CANCELLED` or
        :attr:`BlockState.ERROR`).
    outputs:
        The partial outputs the block returned, if any. Often an empty
        dict for blocks that ``return {}`` after transitioning.
    """

    def __init__(self, state: BlockState, outputs: dict[str, Any] | None = None) -> None:
        self.state = state
        self.outputs = outputs if outputs is not None else {}
        super().__init__(f"Worker reported terminal state: {state.value}")
