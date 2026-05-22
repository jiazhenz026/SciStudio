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
    if event.block_id is None:
        return

    await self._dispatch_newly_ready()

    self._check_completion()
    self.save_checkpoint(self._checkpoint_manager)


async def _on_block_error(self: DAGScheduler, event: EngineEvent) -> None:
    """Handle a block error and propagate skips downstream."""
    if event.block_id is None:
        return

    self._block_states[event.block_id] = BlockState.ERROR
    await self._propagate_skip(event.block_id, "error")
    self._check_completion()
    self.save_checkpoint(self._checkpoint_manager)


async def _on_cancel_block(self: DAGScheduler, event: EngineEvent) -> None:
    """Handle a block cancellation request.

    Per ADR-018 Addendum 1, cancellation branches on whether a
    ``ProcessHandle`` has been registered for the block yet:

    * **Handle present** (block is executing inside a subprocess):
      call ``handle.terminate()`` and let the worker unwind
      naturally. ``_run_and_finalize`` observes the CANCELLED state
      on its exception path and exits without emitting BLOCK_ERROR.
    * **Handle absent** (block is still in its pre-subprocess setup
      window or has no subprocess at all): call ``task.cancel()``
      on the active task. ``_run_and_finalize`` receives a
      ``CancelledError`` and unwinds via its ``finally`` clause.
    * **No handle, no active task**: the block is pre-dispatch or
      was set externally (e.g. tests that pre-assign RUNNING). In
      that case we simply transition to CANCELLED without
      terminating or cancelling anything.
    """
    if event.block_id is None:
        return

    block_id = event.block_id
    handle = None
    if self._process_registry is not None:
        handle = self._process_registry.get_handle(block_id)

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
            await self._runner.cancel(block_id)
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
    # Include both RUNNING and PAUSED blocks — interactive blocks
    # (DataRouter, PairEditor) sit in PAUSED while waiting for user
    # input via an asyncio.Future. They must also be cancelled.
    cancelable_blocks = [
        bid for bid, state in self._block_states.items() if state in (BlockState.RUNNING, BlockState.PAUSED)
    ]

    for block_id in cancelable_blocks:
        handle = None
        if self._process_registry is not None:
            handle = self._process_registry.get_handle(block_id)

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
                await self._runner.cancel(block_id)
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


async def _on_process_exited(self: DAGScheduler, event: EngineEvent) -> None:
    """Handle an unexpected subprocess exit detected by ProcessMonitor.

    If the block is RUNNING and not yet in a terminal state, transition
    to ERROR and emit BLOCK_ERROR so that skip propagation and completion
    checks fire through the normal path.

    PAUSED blocks (AppBlock case) are left alone — the FileWatcher
    manages output collection and will handle the process exit.
    """
    block_id = event.block_id
    if block_id is None or block_id not in self._block_states:
        return

    current = self._block_states[block_id]

    # Already in a terminal state — ignore.
    terminal = {BlockState.DONE, BlockState.ERROR, BlockState.CANCELLED, BlockState.SKIPPED}
    if current in terminal:
        return

    # PAUSED: AppBlock subprocess exited. FileWatcher handles it.
    if current == BlockState.PAUSED:
        return

    # RUNNING: subprocess crashed / OOM-killed / externally terminated.
    if current == BlockState.RUNNING:
        exit_info = event.data.get("exit_info")
        error_detail = "Process exited unexpectedly"
        if isinstance(exit_info, dict):
            sig = exit_info.get("signal_number")
            code = exit_info.get("exit_code")
            if sig:
                error_detail = f"Process killed by signal {sig}"
            elif code is not None:
                error_detail = f"Process exited with code {code}"
        elif exit_info is not None:
            sig = getattr(exit_info, "signal_number", None)
            code = getattr(exit_info, "exit_code", None)
            if sig:
                error_detail = f"Process killed by signal {sig}"
            elif code is not None:
                error_detail = f"Process exited with code {code}"

        self._block_states[block_id] = BlockState.ERROR
        await self._event_bus.emit(
            EngineEvent(
                event_type=BLOCK_ERROR,
                block_id=block_id,
                data=self._build_block_terminal_data(node_id=block_id, error=error_detail),
            )
        )
        # Retry any READY blocks that were previously throttled and
        # dispatch successors whose predecessors are now all DONE.
        await self._dispatch_newly_ready()
        self._check_completion()
