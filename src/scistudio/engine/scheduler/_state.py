"""State machine helpers for :class:`DAGScheduler`.

ADR-046 §5: byte-identical relocation of three state machine helpers
from the original ``engine/scheduler.py`` god-file. These functions are
governed by the :mod:`tests.engine.test_scheduler_state_machine_contract`
contract test (issue #1449); any semantic change requires a separate ADR
and an update to that contract. This module is structural-move only.

Each function is a free function whose first parameter is ``self`` —
they are bound onto :class:`DAGScheduler` in
``scheduler/__init__.py`` via class-body static assignment so griffe
emits the canonical ``scistudio.engine.scheduler.DAGScheduler.<method>``
fact (see ADR-042 + the doc/closure audit walker).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scistudio.blocks.base.state import BlockState
from scistudio.engine.events import BLOCK_SKIPPED, EngineEvent

if TYPE_CHECKING:
    from . import DAGScheduler


async def _propagate_skip(self: DAGScheduler, failed_id: str, reason: str) -> None:
    """Breadth-first skip propagation downstream from *failed_id*."""
    queue = list(self._dag.adjacency.get(failed_id, []))

    while queue:
        node_id = queue.pop(0)
        if self._block_states[node_id] in (
            BlockState.DONE,
            BlockState.ERROR,
            BlockState.CANCELLED,
            BlockState.SKIPPED,
        ):
            continue

        predecessors = self._dag.reverse_adjacency.get(node_id, [])
        all_satisfied = all(self._block_states[p] == BlockState.DONE for p in predecessors)

        if not all_satisfied:
            self._block_states[node_id] = BlockState.SKIPPED
            self.skip_reasons[node_id] = f"upstream {failed_id} {reason}"
            await self._event_bus.emit(
                EngineEvent(
                    event_type=BLOCK_SKIPPED,
                    block_id=node_id,
                    data=self._build_block_terminal_data(node_id=node_id),
                )
            )
            queue.extend(self._dag.adjacency.get(node_id, []))


def _check_readiness(self: DAGScheduler, node_id: str) -> bool:
    """Return True if all predecessors of *node_id* are in DONE state."""
    predecessors = self._dag.reverse_adjacency.get(node_id, [])
    return all(self._block_states[p] == BlockState.DONE for p in predecessors)


def _check_completion(self: DAGScheduler) -> None:
    """Set the completed event when every block has reached a terminal
    state **and** no dispatched task is still running.

    The ``_active_tasks`` guard (ADR-018 Addendum 1) prevents
    ``execute()`` from returning before the final
    ``_run_and_finalize`` coroutine has finished its cleanup.
    """
    terminal = {BlockState.DONE, BlockState.ERROR, BlockState.CANCELLED, BlockState.SKIPPED}
    if all(s in terminal for s in self._block_states.values()) and not self._active_tasks:
        self._completed_event.set()
