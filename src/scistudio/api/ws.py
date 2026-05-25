"""WebSocket handler — bidirectional real-time block state and cancellation.

ADR-018: WebSocket becomes bidirectional. Server pushes block state changes;
client sends cancel requests and interactive completions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from scistudio.api.file_contracts import FILE_CHANGED_EVENT_TYPE
from scistudio.engine.events import (
    BLOCK_CANCELLED,
    BLOCK_DONE,
    BLOCK_ERROR,
    BLOCK_PAUSED,
    BLOCK_READY,
    BLOCK_RUNNING,
    BLOCK_SKIPPED,
    CANCEL_BLOCK_REQUEST,
    CANCEL_WORKFLOW_REQUEST,
    GIT_HEAD_CHANGED,
    INTERACTIVE_COMPLETE,
    INTERACTIVE_PROMPT,
    WORKFLOW_CHANGED,
    WORKFLOW_COMPLETED,
    WORKFLOW_STARTED,
    EngineEvent,
    EventBus,
)

logger = logging.getLogger(__name__)

_GUI_DISCONNECT_GRACE_SEC = 2.0
_gui_ws_clients: set[int] = set()
_gui_disconnect_cancel_task: asyncio.Task[None] | None = None

# ADR-036 §3.5 (I36c): outbound event type emitted after a successful
# blocks/*.py save passes lint and hot_reload runs. Declared here as a
# bare string (not a constant in scistudio.engine.events) because the
# events module is frozen by ADR-035/036 hard-scope rules.
BLOCKS_RELOADED = "blocks.reloaded"

# Event types pushed to the client.
_OUTBOUND_EVENTS = frozenset(
    {
        BLOCK_READY,
        BLOCK_RUNNING,
        BLOCK_PAUSED,
        BLOCK_DONE,
        BLOCK_ERROR,
        BLOCK_CANCELLED,
        BLOCK_SKIPPED,
        WORKFLOW_COMPLETED,
        WORKFLOW_STARTED,
        INTERACTIVE_PROMPT,
        # #718 part (a): forward workflow.changed so connected clients can
        # refresh their cached workflow view when an external writer (another
        # tab, the embedded coding agent, or POST /import-path) mutates the
        # workflow YAML.
        WORKFLOW_CHANGED,
        # ADR-036 §3.5: forward blocks.reloaded so the palette can refresh +
        # a passive toast can fire when the user saves a clean blocks/*.py.
        BLOCKS_RELOADED,
        FILE_CHANGED_EVENT_TYPE,
        # ADR-039 §3.8: forward git.head_changed so the canvas + (future)
        # Git tab invalidate cached log/branch/status state when an
        # external actor moves HEAD or a branch tip.
        GIT_HEAD_CHANGED,
    }
)


def _handle_block_user_signal(
    data: dict[str, Any],
    *,
    signal_filename: str,
    signal_kind: str,
) -> None:
    """Write a JSON signal file under an AI Block run dir (ADR-035 §3.5 path c).

    Resolves the run dir from ``block_run_id`` via the engine-side
    registry maintained by ``ai_pty.open_engine_initiated_tab``. Best
    effort: missing block_run_id, unknown run_id, or write failures are
    logged and swallowed so they cannot crash the WS pump loop.

    Args:
        data: Raw inbound frame dict; reads ``block_run_id`` (required)
            and ``tab_id`` (informational).
        signal_filename: File name to write under ``<run_dir>/signals/``
            (e.g. ``"mark_done.json"``).
        signal_kind: Logical label persisted into the signal payload
            (``"user_mark_done"`` or ``"user_cancel"``) so post-mortem
            tooling can tell the two paths apart.
    """
    block_run_id = data.get("block_run_id")
    tab_id = data.get("tab_id")
    if not isinstance(block_run_id, str) or not block_run_id:
        logger.warning("%s frame missing block_run_id; ignoring", signal_kind)
        return
    # Imported lazily — `ai_pty` already imports lazily from `ws.py` to
    # break the module-level circular import; mirror the pattern here.
    from scistudio.api.routes import ai_pty as ai_pty_module

    run_dir = ai_pty_module.get_run_dir_for_block_run(block_run_id)
    if run_dir is None:
        logger.warning(
            "%s: no run_dir registered for block_run_id=%s tab_id=%s",
            signal_kind,
            block_run_id,
            tab_id,
        )
        return
    signal_dir = run_dir / "signals"
    try:
        signal_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "kind": signal_kind,
            "block_run_id": block_run_id,
            "tab_id": tab_id,
            "ts": datetime.now(UTC).isoformat(),
        }
        (signal_dir / signal_filename).write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
        logger.info(
            "%s: wrote %s for block_run_id=%s",
            signal_kind,
            signal_filename,
            block_run_id,
        )
    except OSError:
        logger.warning(
            "%s: failed to write %s under %s",
            signal_kind,
            signal_filename,
            signal_dir,
            exc_info=True,
        )


def serialise_event(event: EngineEvent) -> dict[str, Any]:
    """Convert an EngineEvent to a JSON-serialisable dict for the WebSocket protocol."""
    return {
        "type": event.event_type,
        "block_id": event.block_id,
        "workflow_id": event.data.get("workflow_id") if isinstance(event.data, dict) else None,
        "data": event.data,
        "timestamp": event.timestamp.isoformat(),
    }


async def _cancel_running_workflows_for_gui_disconnect(event_bus: EventBus) -> None:
    """Cancel active workflows when the GUI session disappears."""
    runtime = getattr(event_bus, "runtime", None)
    runs = getattr(runtime, "workflow_runs", None)
    if not isinstance(runs, dict):
        return

    for workflow_id, run in list(runs.items()):
        task = getattr(run, "task", None)
        if task is not None and callable(getattr(task, "done", None)) and task.done():
            continue
        scheduler = getattr(run, "scheduler", None)
        cancel_workflow = getattr(scheduler, "cancel_workflow", None)
        if not callable(cancel_workflow):
            continue
        try:
            await cancel_workflow()
            logger.info("Cancelled workflow %s after GUI websocket disconnect", workflow_id)
        except Exception:
            logger.warning("Failed to cancel workflow %s after GUI websocket disconnect", workflow_id, exc_info=True)
            continue

        if task is not None and callable(getattr(task, "done", None)) and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
            except (asyncio.CancelledError, TimeoutError):
                pass
            except Exception:
                logger.debug(
                    "Workflow %s task finished with exception after GUI disconnect", workflow_id, exc_info=True
                )


def _has_active_workflow_runs(event_bus: EventBus) -> bool:
    runtime = getattr(event_bus, "runtime", None)
    runs = getattr(runtime, "workflow_runs", None)
    if not isinstance(runs, dict):
        return False
    for run in runs.values():
        task = getattr(run, "task", None)
        if task is None:
            continue
        if not callable(getattr(task, "done", None)) or not task.done():
            return True
    return False


async def _cancel_after_gui_disconnect_grace(event_bus: EventBus) -> None:
    """Debounce transient reconnects before cancelling browser-owned runs."""
    global _gui_disconnect_cancel_task

    try:
        await asyncio.sleep(_GUI_DISCONNECT_GRACE_SEC)
        if _gui_ws_clients:
            return
        await _cancel_running_workflows_for_gui_disconnect(event_bus)
    except asyncio.CancelledError:
        raise
    finally:
        if asyncio.current_task() is _gui_disconnect_cancel_task:
            _gui_disconnect_cancel_task = None


async def websocket_handler(websocket: WebSocket, event_bus: EventBus) -> None:
    """Handle a WebSocket connection for real-time workflow updates.

    ADR-018: Bidirectional protocol.
    - Inbound: client sends cancel_block, cancel_workflow, interactive_complete.
    - Outbound: server pushes all block state changes and workflow completion.

    ADR-035 §3.10: also subscribes to the ai_pty broadcaster so engine-
    initiated AI Block tab opens / closes (``block_pty_opened`` /
    ``block_pty_closed``) flow over the same WS without introducing a
    new EngineEvent type.
    """
    # Imported lazily so the module-level circular import (ai_pty
    # imports nothing from ws, ws imports nothing from ai_pty at module
    # load) is sidestepped — and to keep the ws module's dep surface
    # narrow.
    from scistudio.api.routes import ai_pty as ai_pty_module

    global _gui_disconnect_cancel_task

    await websocket.accept()

    outbound_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    client_token = id(outbound_queue)
    _gui_ws_clients.add(client_token)
    if _gui_disconnect_cancel_task is not None and not _gui_disconnect_cancel_task.done():
        _gui_disconnect_cancel_task.cancel()

    def _on_event(event: EngineEvent) -> None:
        """Callback for EventBus — enqueue event for outbound delivery."""
        outbound_queue.put_nowait(serialise_event(event))

    def _on_ai_pty_message(message: dict[str, Any]) -> None:
        """Callback for ai_pty broadcaster — enqueue raw dict frame."""
        outbound_queue.put_nowait(message)

    # Subscribe to all outbound event types.
    for event_type in _OUTBOUND_EVENTS:
        event_bus.subscribe(event_type, _on_event)
    ai_pty_module.register_ai_pty_subscriber(_on_ai_pty_message)

    async def _inbound_loop() -> None:
        """Read messages from the client and dispatch to EventBus."""
        try:
            while True:
                raw = await websocket.receive_text()
                data = json.loads(raw)
                msg_type = data.get("type", "")

                if msg_type == "cancel_block":
                    block_id = data.get("block_id")
                    workflow_id = data.get("workflow_id")
                    if not block_id or not workflow_id:
                        logger.warning("cancel_block message missing block_id or workflow_id")
                        continue
                    await event_bus.emit(
                        EngineEvent(
                            event_type=CANCEL_BLOCK_REQUEST,
                            block_id=block_id,
                            data={"workflow_id": workflow_id},
                        )
                    )
                elif msg_type == "cancel_workflow":
                    workflow_id = data.get("workflow_id")
                    if not workflow_id:
                        logger.warning("cancel_workflow message missing workflow_id")
                        continue
                    await event_bus.emit(
                        EngineEvent(
                            event_type=CANCEL_WORKFLOW_REQUEST,
                            data={"workflow_id": workflow_id},
                        )
                    )
                elif msg_type == "interactive_complete":
                    await event_bus.emit(
                        EngineEvent(
                            event_type=INTERACTIVE_COMPLETE,
                            block_id=data.get("block_id"),
                            data=data.get("data", {}),
                        )
                    )
                elif msg_type == "block_user_marked_done":
                    # Audit P1-E (Codex #866-3): ADR-035 §3.5 path (c) —
                    # the user clicked "Mark done" in an AI Block tab.
                    # Translate the WS frame into a ``mark_done.json`` signal
                    # file under the run dir; the worker's CompletionWatcher
                    # picks it up on its next poll tick (≤250ms) and
                    # transitions the block to DONE.
                    _handle_block_user_signal(
                        data,
                        signal_filename="mark_done.json",
                        signal_kind="user_mark_done",
                    )
                elif msg_type == "block_user_cancel":
                    # Audit P1-E (Codex #866-3): ADR-035 §3.9 — user closed
                    # the AI Block tab while it was still running. Treat as
                    # a user-initiated completion: write the same
                    # ``mark_done.json`` signal so the worker can unblock
                    # and tear down cleanly. (Full cancellation semantics —
                    # CompletionWatcher.cancel() propagation across the
                    # engine⇄worker boundary — is filed as a follow-up; this
                    # restores the wire-level no-op the audit flagged.)
                    _handle_block_user_signal(
                        data,
                        signal_filename="mark_done.json",
                        signal_kind="user_cancel",
                    )
                else:
                    logger.warning("Unknown WebSocket message type: %s", msg_type)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass

    async def _outbound_loop() -> None:
        """Send queued events to the client."""
        try:
            while True:
                payload = await outbound_queue.get()
                await websocket.send_json(payload)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass

    try:
        await asyncio.gather(_inbound_loop(), _outbound_loop())
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        _gui_ws_clients.discard(client_token)
        for event_type in _OUTBOUND_EVENTS:
            event_bus.unsubscribe(event_type, _on_event)
        ai_pty_module.unregister_ai_pty_subscriber(_on_ai_pty_message)
        if not _gui_ws_clients and _has_active_workflow_runs(event_bus):
            _gui_disconnect_cancel_task = asyncio.create_task(_cancel_after_gui_disconnect_grace(event_bus))
