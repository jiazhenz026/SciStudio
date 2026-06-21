"""Rerun, reset, and graph-traversal helpers for :class:`DAGScheduler`.

ADR-046 §3 (Rerun / graph group): extracted verbatim from the original
``engine/scheduler.py`` god-file. Pure structural move per umbrella
#1427 Phase 3 — no behavior changes. ADR-018 Addendum 1 cancellation
semantics (terminate subprocess → cancel task → drain) are preserved
byte-identically.

Each function is a free function whose first parameter is ``self`` —
they are bound onto :class:`DAGScheduler` in
``scheduler/__init__.py`` via class-body static assignment so griffe
emits the canonical ``scistudio.engine.scheduler.DAGScheduler.<method>``
fact (see ADR-042 + the doc/closure audit walker).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from scistudio.blocks.base.state import BlockState

if TYPE_CHECKING:
    from . import DAGScheduler

logger = logging.getLogger("scistudio.engine.scheduler")


async def _cancel_if_active(self: DAGScheduler, block_id: str) -> None:
    """Cancel the active task/subprocess for *block_id* if one exists.

    This is the pre-reset counterpart of ``_on_cancel_block``: it
    terminates the subprocess handle (when present) or cancels the
    asyncio task, then awaits its completion so the task entry is
    removed from ``_active_tasks`` before the caller re-dispatches
    the block.  Introduced to fix #424 — rerunning a RUNNING block
    must kill the previous subprocess first.
    """
    if self._block_states.get(block_id) != BlockState.RUNNING:
        return
    task = self._active_tasks.get(block_id)
    if task is None:
        return

    # Terminate subprocess if one is tracked.
    handle = None
    if self._process_registry is not None:
        handle = self._process_registry.get_handle(self._workflow.id, block_id)
    if handle is not None:
        try:
            handle.terminate()
        except Exception:
            logger.exception("Failed to terminate subprocess for block %s during rerun", block_id)

    # Always cancel the asyncio task so _run_and_finalize can unwind.
    # When a subprocess handle is present, terminate() sends SIGTERM to
    # the worker but the wrapping asyncio task still needs cancellation
    # to stop awaiting the (now-dead) process (#424).
    if not task.done():
        task.cancel()

    if hasattr(self._runner, "cancel"):
        try:
            await self._runner.cancel(self._workflow.id, block_id)
        except Exception:
            logger.exception("Failed to cancel block %s via runner during rerun", block_id)

    # Yield once so the event loop can deliver the CancelledError into
    # the task coroutine, then await completion.
    await asyncio.sleep(0)
    with contextlib.suppress(asyncio.CancelledError, TimeoutError, Exception):
        await task
    # Ensure the task entry is removed (normally done by _run_and_finalize).
    self._active_tasks.pop(block_id, None)

    logger.info("Cancelled active block %s before rerun", block_id)


def _reset_upstream(self: DAGScheduler, block_id: str, visited: set[str]) -> None:
    """Recursively reset non-DONE upstream blocks to IDLE."""
    if block_id in visited:
        return
    visited.add(block_id)
    predecessors = self._dag.reverse_adjacency.get(block_id, [])
    for pred in predecessors:
        if self._block_states[pred] != BlockState.DONE:
            self._block_states[pred] = BlockState.IDLE
            self._block_outputs.pop(pred, None)
            self.skip_reasons.pop(pred, None)
            self._reset_upstream(pred, visited)


def _reset_downstream_skipped(self: DAGScheduler, block_id: str) -> None:
    """Breadth-first reset of downstream SKIPPED blocks."""
    queue = list(self._dag.adjacency.get(block_id, []))
    visited: set[str] = set()
    while queue:
        node_id = queue.pop(0)
        if node_id in visited:
            continue
        visited.add(node_id)
        if self._block_states[node_id] == BlockState.SKIPPED:
            self._block_states[node_id] = BlockState.IDLE
            self._block_outputs.pop(node_id, None)
            self.skip_reasons.pop(node_id, None)
            queue.extend(self._dag.adjacency.get(node_id, []))


def _ancestors_of(self: DAGScheduler, block_id: str) -> set[str]:
    """Return all upstream nodes for *block_id*."""
    visited: set[str] = set()
    queue = list(self._dag.reverse_adjacency.get(block_id, []))
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        queue.extend(self._dag.reverse_adjacency.get(current, []))
    return visited


async def _drain_active_tasks(self: DAGScheduler) -> None:
    """Await all dispatched tasks, including any successors they trigger.

    Used by callers that do not otherwise wait on
    ``self._completed_event`` (``resume``, ``reset_block``) but must
    still block until the tasks they just scheduled have finished.
    A snapshot is awaited in each iteration because ``_on_block_done``
    can add new entries to ``_active_tasks`` while we wait.
    """
    while self._active_tasks:
        tasks = list(self._active_tasks.values())
        await asyncio.gather(*tasks, return_exceptions=True)


async def _cancel_active_tasks_on_shutdown(self: DAGScheduler) -> None:
    """Best-effort cleanup of any tasks still running on shutdown.

    Called from ``execute()``'s ``finally`` block (ADR-018
    Addendum 1). Iterates every entry in ``self._active_tasks``:

    1. If a ``ProcessHandle`` is registered, terminate the
       subprocess via the ADR-019 path.
    2. If the task is still not done, cancel it and await its
       completion. Swallows any exception because this runs inside
       a ``finally`` clause and must not mask the original error.
    """
    for block_id, task in list(self._active_tasks.items()):
        handle = None
        if self._process_registry is not None:
            handle = self._process_registry.get_handle(self._workflow.id, block_id)
        if handle is not None:
            try:
                handle.terminate()
            except Exception:
                logger.exception(
                    "Shutdown: failed to terminate process for block %s",
                    block_id,
                )
        if not task.done():
            task.cancel()
            # Shutdown path: swallow any exception (including the
            # ``CancelledError`` raised by ``task.cancel()``) so the
            # original exception that triggered ``finally`` is not
            # masked.
            with contextlib.suppress(BaseException):
                await task
