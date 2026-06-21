"""EventBus subscriber handler implementations for :class:`DAGScheduler`.

ADR-046 §3 (Event handlers group): extracted verbatim from the
original ``engine/scheduler.py`` god-file. Pure structural move per
umbrella #1427 Phase 3 — no behavior changes. ADR-018 Addendum 1
cancellation semantics and ADR-038/039 emission contracts are
preserved byte-identically.

Each function is a free function whose first parameter is ``self`` —
they are bound onto :class:`DAGScheduler` in
``scheduler/__init__.py`` via class-body static assignment so griffe
emits the canonical ``scistudio.engine.scheduler.DAGScheduler.<method>``
fact (see ADR-042 + the doc/closure audit walker).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scistudio.blocks.base.state import BlockState
from scistudio.engine.events import (
    BLOCK_CANCELLED,
    BLOCK_ERROR,
    BLOCK_SKIPPED,
    EngineEvent,
)

if TYPE_CHECKING:
    from . import DAGScheduler

logger = logging.getLogger("scistudio.engine.scheduler")


def _event_is_for_run(self: DAGScheduler, event: EngineEvent) -> bool:
    """Return True when *event* targets this scheduler's own workflow.

    #1517/#1596: ``ApiRuntime`` owns one process-global ``EventBus`` and fans
    every event out to every live scheduler. A scheduler must only react to
    events for its own ``workflow_id``; otherwise a cancel or terminal event
    for one run mutates the state of every other concurrent run. Events that
    carry no ``workflow_id`` are treated as in-scope (fail-open) so event types
    that predate run scoping keep working.
    """
    if not isinstance(event.data, dict):
        return True
    event_wf = event.data.get("workflow_id")
    return event_wf is None or event_wf == self._workflow.id


async def _on_interactive_complete(self: DAGScheduler, event: EngineEvent) -> None:
    """Handle an interactive_complete event from the frontend.

    Resolves the pending future for the block so that
    ``_run_interactive`` can proceed with the user's response.
    """
    block_id = event.block_id
    if block_id is None:
        return

    future = self._interactive_futures.get(block_id)
    if future is not None and not future.done():
        future.set_result(event.data)
    else:
        logger.warning(
            "Received interactive_complete for block %s but no pending future found",
            block_id,
        )


async def _on_block_done(self: DAGScheduler, event: EngineEvent) -> None:
    """Handle a block completion and dispatch newly ready blocks."""
    if not _event_is_for_run(self, event):
        return
    if event.block_id is None:
        return

    await self._dispatch_newly_ready()

    self._check_completion()
    self.save_checkpoint(self._checkpoint_manager)


async def _on_block_error(self: DAGScheduler, event: EngineEvent) -> None:
    """Handle a block error and propagate skips downstream."""
    if not _event_is_for_run(self, event):
        return
    if event.block_id is None:
        return

    self._block_states[event.block_id] = BlockState.ERROR
    await self._propagate_skip(event.block_id, "error")
    self._check_completion()
    self.save_checkpoint(self._checkpoint_manager)


async def _on_cancel_block(self: DAGScheduler, event: EngineEvent) -> None:
    """Handle a block cancellation request.

    Per ADR-018 Addendum 1 and the state table in
    ``docs/architecture/ARCHITECTURE.md`` §5.2, ``CANCELLED`` is only
    a valid transition from ``RUNNING`` or ``PAUSED``. A cancel
    request against a block in any other state is a **no-op** — the
    handler returns without emitting a lifecycle event or mutating
    state. This matches the executable spec in
    ``tests/engine/test_scheduler_state_machine_contract.py``
    ``test_cancel_block_state_table`` (#1376).

    Concretely:

    * **RUNNING / PAUSED** — the only states the state-table allows
      to transition into ``CANCELLED``. Branches on whether a
      ``ProcessHandle`` has been registered for the block yet:

      - *Handle present* (executing inside a subprocess): call
        ``handle.terminate()`` and let the worker unwind naturally.
        ``_run_and_finalize`` observes the ``CANCELLED`` state on
        its exception path and exits without emitting
        ``BLOCK_ERROR``.
      - *Handle absent* (pre-subprocess setup window, or in-process
        interactive block waiting in ``PAUSED``): call
        ``task.cancel()`` on the active task. ``_run_and_finalize``
        / ``_run_interactive`` receives ``CancelledError`` and
        unwinds via its ``finally`` clause.

    * **IDLE / READY** — the block has not started yet. The state
      table does not permit ``IDLE``/``READY`` → ``CANCELLED``, so
      ignore the request. Workflow-level cancellation handles
      blanket cleanup of not-yet-started blocks via
      :func:`_on_cancel_workflow`, which transitions them to
      ``SKIPPED``. ``cancel_block`` against a single not-yet-started
      block is treated as a stale UI click and intentionally takes
      no action.

    * **DONE / ERROR / CANCELLED / SKIPPED** — terminal states are
      idempotent under cancellation: ignore the request, log a
      debug-level note, and leave the state untouched. Re-emitting
      ``BLOCK_CANCELLED`` for a block that already finished would
      confuse downstream subscribers (the frontend would show a
      second "cancelled" toast for a block that already reported
      ``DONE``).

    * **Unknown block id** — ignored silently; the scheduler only
      cancels blocks it tracks.
    """
    if not _event_is_for_run(self, event):
        return
    if event.block_id is None:
        return

    block_id = event.block_id
    current_state = self._block_states.get(block_id)
    if current_state is None:
        # Unknown block — nothing to cancel.
        return

    if current_state not in (BlockState.RUNNING, BlockState.PAUSED):
        # #1376: per architecture §5.2, ``CANCELLED`` is only a valid
        # transition from ``RUNNING`` / ``PAUSED``. For every other
        # state (``IDLE``, ``READY``, ``DONE``, ``ERROR``,
        # ``CANCELLED``, ``SKIPPED``) the cancel request is a no-op.
        # The executable spec lives in
        # ``tests/engine/test_scheduler_state_machine_contract.py``
        # ``test_cancel_block_state_table``.
        logger.debug(
            "Ignoring cancel request for block %s in non-cancellable state %s",
            block_id,
            current_state.value,
        )
        return

    # current_state is RUNNING or PAUSED — the architecture state
    # table permits CANCELLED here.
    handle = None
    if self._process_registry is not None:
        handle = self._process_registry.get_handle(self._workflow.id, block_id)

    # Mark CANCELLED before terminating/cancelling so that
    # _run_and_finalize's exception path sees the CANCELLED state
    # and does not re-emit BLOCK_ERROR.
    self._block_states[block_id] = BlockState.CANCELLED

    # #591/#594: Cancel pending interactive future so _run_interactive
    # receives CancelledError and unwinds.
    interactive_future = self._interactive_futures.pop(block_id, None)
    if interactive_future is not None and not interactive_future.done():
        interactive_future.cancel()

    if handle is not None:
        # Authoritative path per ADR-019 — SIGTERM/SIGKILL the worker.
        try:
            handle.terminate()
        except Exception:
            logger.exception("Failed to terminate subprocess for block %s", block_id)
    else:
        # No subprocess handle yet: cancel the pre-subprocess task
        # so that the setup phase aborts with CancelledError.
        task = self._active_tasks.get(block_id)
        if task is not None and not task.done():
            task.cancel()

    if hasattr(self._runner, "cancel"):
        try:
            await self._runner.cancel(self._workflow.id, block_id)
        except Exception:
            logger.exception("Failed to cancel block %s via runner", block_id)

    await self._event_bus.emit(
        EngineEvent(
            event_type=BLOCK_CANCELLED,
            block_id=block_id,
            data=self._build_block_terminal_data(node_id=block_id),
        )
    )
    await self._propagate_skip(block_id, "cancelled")
    self._check_completion()
    self.save_checkpoint(self._checkpoint_manager)


async def _on_cancel_workflow(self: DAGScheduler, event: EngineEvent) -> None:
    """Handle a workflow cancellation: cancel all running blocks.

    Applies the same handle-vs-task branch as ``_on_cancel_block``
    (ADR-018 Addendum 1). Any block still IDLE/READY at the time of
    the cancel request is transitioned to SKIPPED with reason
    "workflow cancelled".
    """
    if not _event_is_for_run(self, event):
        return
    # Include both RUNNING and PAUSED blocks — interactive blocks
    # (DataRouter, PairEditor) sit in PAUSED while waiting for user
    # input via an asyncio.Future. They must also be cancelled.
    cancelable_blocks = [
        bid for bid, state in self._block_states.items() if state in (BlockState.RUNNING, BlockState.PAUSED)
    ]

    for block_id in cancelable_blocks:
        handle = None
        if self._process_registry is not None:
            handle = self._process_registry.get_handle(self._workflow.id, block_id)

        # Mark CANCELLED before terminating/cancelling so that
        # _run_and_finalize observes the CANCELLED state.
        self._block_states[block_id] = BlockState.CANCELLED

        if handle is not None:
            try:
                handle.terminate()
            except Exception:
                logger.exception(
                    "Failed to terminate subprocess for block %s during workflow cancel",
                    block_id,
                )
        else:
            task = self._active_tasks.get(block_id)
            if task is not None and not task.done():
                task.cancel()

        # Cancel interactive future if the block is PAUSED waiting
        # for user input (DataRouter/PairEditor).
        interactive_future = self._interactive_futures.pop(block_id, None)
        if interactive_future is not None and not interactive_future.done():
            interactive_future.cancel()

        if hasattr(self._runner, "cancel"):
            try:
                await self._runner.cancel(self._workflow.id, block_id)
            except Exception:
                logger.exception("Failed to cancel block %s during workflow cancel", block_id)

        await self._event_bus.emit(
            EngineEvent(
                event_type=BLOCK_CANCELLED,
                block_id=block_id,
                data=self._build_block_terminal_data(node_id=block_id),
            )
        )

    for block_id, state in list(self._block_states.items()):
        if state in (BlockState.IDLE, BlockState.READY):
            self._block_states[block_id] = BlockState.SKIPPED
            self.skip_reasons[block_id] = "workflow cancelled"
            await self._event_bus.emit(
                EngineEvent(
                    event_type=BLOCK_SKIPPED,
                    block_id=block_id,
                    data=self._build_block_terminal_data(node_id=block_id),
                )
            )

    self._check_completion()
    self.save_checkpoint(self._checkpoint_manager)
