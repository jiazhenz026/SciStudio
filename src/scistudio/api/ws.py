"""WebSocket handler — bidirectional real-time block state and cancellation."""
# Maintainer context (kept outside generated API documentation):
# WebSocket handler — bidirectional real-time block state and cancellation.
#
# ADR-018: WebSocket becomes bidirectional. Server pushes block state changes;
# client sends cancel requests and interactive completions.
# Development references: ADR-018.

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from scistudio.api.file_contracts import FILE_CHANGED_EVENT_TYPE
from scistudio.engine import gui_presence
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

#: Live FR-013 grace-period tasks. Held so the event loop keeps a strong
#: reference to each one — a bare ``create_task`` result is garbage-collectable
#: mid-sleep, which would silently leave a gone workspace's MiniApp processes
#: running for the rest of the session.
_panel_close_tasks: set[asyncio.Task[None]] = set()

# ADR-036 §3.5 (I36c): outbound event type emitted after a successful
# blocks/*.py save passes lint and hot_reload runs. Declared here as a
# bare string (not a constant in scistudio.engine.events) because the
# events module is frozen by ADR-035/036 hard-scope rules.
BLOCKS_RELOADED = "blocks.reloaded"

# ADR-054 MiniApp FR-022: a file under an open MiniApp's panel directory
# changed and the host should reload that MiniApp. Data: ``{"panel_id": str}``.
# A bare string for the same reason ``BLOCKS_RELOADED`` is one.
PANEL_FILES_CHANGED = "panel.files_changed"

# ADR-054 MiniApp FR-030: the agent's ``open_miniapp`` tool asks the workspace
# to open a MiniApp tab. Data:
# ``{"panel_id": str, "workflow_id": str, "block_id": str, "port": str}``.
PANEL_OPEN_MINIAPP = "panel.open_miniapp"

#: FR-013: the shape of a workspace realtime client id. Minted here, sent to
#: the browser in the ``hello`` frame, and quoted back as ``ws_client_id`` when
#: the workspace opens a MiniApp context.
_CLIENT_ID = re.compile(r"ws-[0-9a-f]{16}\Z")

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
        # ADR-054 MiniApp FR-022/FR-030: an event type absent from this set is
        # never subscribed, so it silently never reaches the browser.
        PANEL_FILES_CHANGED,
        PANEL_OPEN_MINIAPP,
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
    """Write a JSON signal file under an AI Block run dir (path c).

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
    # Development references: ADR-035.
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


def _client_id_for(websocket: WebSocket) -> str:
    """Return the workspace client id this connection speaks for."""
    # Return the workspace client id this connection speaks for (FR-013).
    #
    # A fresh id per connection is the default, and it is what a browser that
    # reloaded should get: the page lost its contexts with its JavaScript, and
    # the ones it left behind are closed after the grace period below.
    #
    # A workspace whose socket merely dropped is a different case, and it is the
    # case the grace period exists for. Such a client reconnects quoting the id
    # it was given, and gets it back — so its MiniApp processes, which may hold
    # a large array that took a minute to load, survive a flaky connection
    # rather than being rebuilt from scratch. The value is accepted only in the
    # exact minted shape, so a reconnect can restore an identity but cannot
    # invent one.
    quoted = websocket.query_params.get("client_id", "")
    if _CLIENT_ID.fullmatch(quoted):
        return quoted
    return "ws-" + secrets.token_hex(8)


async def _close_panel_contexts_after_grace(event_bus: EventBus, client_id: str) -> None:
    """Close *client_id*'s MiniApp contexts once it has stayed gone."""
    # Close *client_id*'s MiniApp contexts once it has stayed gone (FR-013).
    #
    # A reconnect inside the grace period re-registers the id. This wakes to find
    # it present, and the MiniApp keeps running.
    from scistudio.panels.contexts import get_panel_contexts
    from scistudio.panels.process_config import client_disconnect_grace

    try:
        await asyncio.sleep(client_disconnect_grace())
        if client_id in gui_presence.connected():
            return
        runtime = getattr(event_bus, "runtime", None)
        if runtime is None:
            return
        get_panel_contexts(runtime).close_for_client(client_id)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("Failed to close panel contexts for client %s", client_id, exc_info=True)


async def _run_socket_pumps(*loops: Coroutine[Any, Any, None]) -> None:
    """End both socket pumps as soon as either direction disconnects."""
    tasks = {asyncio.create_task(loop) for loop in loops}
    try:
        completed, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in completed:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def websocket_handler(websocket: WebSocket, event_bus: EventBus) -> None:
    """Handle a WebSocket connection for real-time workflow updates.

    Bidirectional protocol.
    Inbound: client sends cancel_block, cancel_workflow, interactive_complete.
    Outbound: server pushes all block state changes and workflow completion.

    also subscribes to the ai_pty broadcaster so engine-
    initiated AI Block tab opens / closes (``block_pty_opened`` /
    ``block_pty_closed``) flow over the same WS without introducing a
    new EngineEvent type.

    Closing a connection only unsubscribes that client. It never cancels a
    workflow run, however many clients remain: a run ends when it completes
    or is cancelled explicitly. Backend shutdown, and reconciliation when a
    project is opened, keep a run's lineage from staying ``running`` (see
    ``scistudio.api.runtime._run_lifetime``).
    """
    # Development references: ADR-018, ADR-035, ADR-055 section 7, #2327.
    # Imported lazily so the module-level circular import (ai_pty
    # imports nothing from ws, ws imports nothing from ai_pty at module
    # load) is sidestepped — and to keep the ws module's dep surface
    # narrow.
    from scistudio.api.routes import ai_pty as ai_pty_module

    await websocket.accept()

    # FR-013: this workspace's identity. Registered before the frame that
    # announces it is sent, so a send that fails still unwinds through the
    # ``finally`` below rather than leaving a registration behind.
    client_id = _client_id_for(websocket)
    gui_presence.register(client_id)

    outbound_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    from scistudio.panels.gui_debug import get_gui_debug

    runtime = getattr(event_bus, "runtime", None)
    debug_broker = get_gui_debug(runtime) if runtime is not None else None
    debug_connection = debug_broker.connect(client_id, outbound_queue.put_nowait) if debug_broker else ""

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

                if debug_broker and debug_broker.receive(
                    debug_connection, data, getattr(getattr(event_bus, "runtime", None), "project_dir", None)
                ):
                    continue
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
                    # ADR-054: a new panel must own this exact waiting prompt.
                    # Validation claims once; the event contract below stays unchanged.
                    from scistudio.panels.contexts import get_panel_contexts
                    from scistudio.panels.targets import PanelError

                    runtime = getattr(event_bus, "runtime", None)
                    if runtime is not None:
                        try:
                            get_panel_contexts(runtime).claim_writeback(
                                data.get("context_id"),
                                data.get("workflow_id"),
                                data.get("block_id"),
                                data.get("data", {}),
                            )
                        except PanelError as exc:
                            outbound_queue.put_nowait(
                                {
                                    "type": "panel_error",
                                    "workflow_id": data.get("workflow_id"),
                                    "block_id": data.get("block_id"),
                                    "context_id": data.get("context_id"),
                                    "error": {"code": exc.code, "message": exc.message},
                                }
                            )
                            continue
                    # ADR-051 audit P2-1 / #1517: carry workflow_id so the
                    # scheduler can run-scope the response (the decision is
                    # nested under ``response`` and the scoping id is stripped
                    # before it reaches ``interactive_response`` / lineage).
                    scope = {
                        "context_id": data.get("context_id"),
                        "workflow_id": data.get("workflow_id"),
                        "block_id": data.get("block_id"),
                    }
                    try:
                        await event_bus.emit(
                            EngineEvent(
                                event_type=INTERACTIVE_COMPLETE,
                                block_id=data.get("block_id"),
                                data={
                                    "workflow_id": data.get("workflow_id"),
                                    "response": data.get("data", {}),
                                },
                            )
                        )
                    except Exception:
                        if runtime is None or not scope["context_id"]:
                            raise
                        outbound_queue.put_nowait(
                            {
                                "type": "panel_error",
                                **scope,
                                "error": {
                                    "code": "completion_failed",
                                    "message": "Decision dispatch failed; reopen the panel",
                                },
                            }
                        )
                    else:
                        if runtime is not None and scope["context_id"]:
                            outbound_queue.put_nowait({"type": "panel_accepted", **scope})
                elif msg_type == "ping":
                    outbound_queue.put_nowait({"type": "pong"})
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
        # FR-013: the client id reaches the browser first. Sent directly rather
        # than through the outbound queue, which an already-running workflow's
        # events could otherwise get ahead of in the same tick.
        await websocket.send_json({"type": "hello", "client_id": client_id})
        await _run_socket_pumps(_inbound_loop(), _outbound_loop())
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        if debug_broker and debug_connection:
            debug_broker.disconnect(debug_connection)
        gui_presence.unregister(client_id)
        for event_type in _OUTBOUND_EVENTS:
            event_bus.unsubscribe(event_type, _on_event)
        ai_pty_module.unregister_ai_pty_subscriber(_on_ai_pty_message)
        # FR-013: this workspace's MiniApp processes outlive a dropped socket
        # for the grace period and no longer. The task holds no reference to
        # this connection, so it survives the handler returning.
        close_task = asyncio.create_task(_close_panel_contexts_after_grace(event_bus, client_id))
        _panel_close_tasks.add(close_task)
        close_task.add_done_callback(_panel_close_tasks.discard)
