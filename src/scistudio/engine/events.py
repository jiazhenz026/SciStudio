"""Engine event bus — publish/subscribe backbone for runtime coordination.

ADR-018: EventBus becomes the runtime backbone. All state changes, cancellation,
process lifecycle, and checkpoint events flow through this bus.
ADR-017: PROCESS_SPAWNED and PROCESS_EXITED events added for subprocess tracking.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# -- Event type constants (ADR-017, ADR-018) --------------------------------

BLOCK_READY = "block_ready"
BLOCK_RUNNING = "block_running"
BLOCK_PAUSED = "block_paused"
BLOCK_DONE = "block_done"
BLOCK_ERROR = "block_error"
BLOCK_CANCELLED = "block_cancelled"  # ADR-018
BLOCK_SKIPPED = "block_skipped"  # ADR-018
CANCEL_BLOCK_REQUEST = "cancel_block_request"  # ADR-018
CANCEL_WORKFLOW_REQUEST = "cancel_workflow_request"  # ADR-018
PROCESS_SPAWNED = "process_spawned"  # ADR-017/019
PROCESS_EXITED = "process_exited"  # ADR-017/019
WORKFLOW_STARTED = "workflow_started"  # ADR-018
WORKFLOW_COMPLETED = "workflow_completed"  # ADR-018
CHECKPOINT_SAVED = "checkpoint_saved"  # ADR-018
INTERACTIVE_PROMPT = "interactive_prompt"  # #591/#594: backend -> frontend interactive data
INTERACTIVE_COMPLETE = "interactive_complete"  # #591/#594: frontend -> backend interactive response
# #718 part (a): emitted after every successful workflow write so other clients
# (e.g. a second browser tab, or the embedded coding agent's WS subscriber)
# know to refresh their cached view. Payload:
#   {"workflow_id": str, "changed_by": str | None}
# The legacy ``revision`` field was removed by ADR-039 §5.2; git commit SHA +
# working-tree dirty state replaces the optimistic-concurrency counter.
WORKFLOW_CHANGED = "workflow.changed"
FILE_CHANGED = "file.changed"  # ADR-045 shared version-vector event for file tabs.
# ADR-039 §3.8: emitted when the project's git HEAD or any ref/branch tip
# moves — used by the canvas + Git tab to invalidate cached log/diff views.
# Payload:
#   {"commit_sha": str | None, "ref": str, "kind": "head" | "refs"}
# The constant is the one authorized addition to the EventBus contract per
# the ADR-038/039 cascade boilerplate's hard-scope list. Emitted by the
# extended ``workflow_watcher`` after ``.git/HEAD`` or ``.git/refs/heads/*``
# mtime changes.
GIT_HEAD_CHANGED = "git.head_changed"


@dataclass
class EngineEvent:
    """A single event emitted by the engine during workflow execution."""

    event_type: str
    block_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


# -- Subscription matrix (ADR-018) ------------------------------------------
#
# Component          | Subscribes to
# -------------------|------------------------------------------------------
# DAGScheduler       | BLOCK_READY, BLOCK_DONE, BLOCK_ERROR, BLOCK_CANCELLED,
#                    | BLOCK_SKIPPED, CANCEL_BLOCK_REQUEST, CANCEL_WORKFLOW_REQUEST
# ResourceManager    | BLOCK_DONE, BLOCK_ERROR, BLOCK_CANCELLED,
#                    | PROCESS_SPAWNED, PROCESS_EXITED
# ProcessRegistry    | PROCESS_SPAWNED, PROCESS_EXITED
# WebSocket handler  | all BLOCK_* events, WORKFLOW_COMPLETED
# LineageRecorder    | BLOCK_DONE, BLOCK_ERROR, BLOCK_CANCELLED, BLOCK_SKIPPED
# CheckpointManager  | all terminal state events + CHECKPOINT_SAVED


class EventBus:
    """Publish/subscribe dispatcher for EngineEvent instances.

    Internal storage:
        _subscribers: dict[str, list[Callable[[EngineEvent], None]]]

    Methods:
        async emit(event): broadcast event to all subscribers of event.event_type.
            Calls each callback. If callback is a coroutine, await it.
        subscribe(event_type, callback): register callback for event_type.
        unsubscribe(event_type, callback): deregister callback for event_type.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[EngineEvent], None]]] = defaultdict(list)
        self.runtime: Any | None = None

    async def emit(self, event: EngineEvent) -> None:
        """Broadcast *event* to all subscribers of its event_type.

        Each callback is invoked in order. If a callback is a coroutine
        function its result is awaited. Exceptions in individual callbacks
        are caught, logged, and do **not** prevent subsequent callbacks
        from running (error isolation per ADR-018).
        """
        for callback in self._subscribers[event.event_type]:
            try:
                result = callback(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception(
                    "EventBus: callback %r failed for event %s",
                    callback,
                    event.event_type,
                )

    def subscribe(
        self,
        event_type: str,
        callback: Callable[..., Any],
    ) -> None:
        """Register *callback* to receive events of the given type.

        Accepts both sync and async callables — async coroutines are
        awaited automatically by :meth:`emit`.
        """
        self._subscribers[event_type].append(callback)

    def unsubscribe(
        self,
        event_type: str,
        callback: Callable[..., Any],
    ) -> None:
        """Remove a previously registered *callback* for *event_type*.

        If *callback* is not currently subscribed for *event_type* the
        call is silently ignored.
        """
        with contextlib.suppress(ValueError):
            self._subscribers[event_type].remove(callback)
