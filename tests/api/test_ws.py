"""Tests for WebSocket realtime updates."""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import scistudio.api.ws as ws_module
from scistudio.api.runtime import ApiRuntime
from scistudio.api.ws import _OUTBOUND_EVENTS, websocket_handler
from scistudio.engine.events import (
    BLOCK_DONE,
    CANCEL_BLOCK_REQUEST,
    CANCEL_WORKFLOW_REQUEST,
    WORKFLOW_STARTED,
    EngineEvent,
    EventBus,
)
from tests.api.helpers import wait_for_condition


def test_workflow_started_in_outbound_events() -> None:
    """WORKFLOW_STARTED must be forwarded to WebSocket clients (#580)."""
    assert WORKFLOW_STARTED in _OUTBOUND_EVENTS


def test_websocket_receives_serialised_engine_events(client: TestClient, runtime: ApiRuntime) -> None:
    """Outbound workflow events should be pushed to connected clients."""
    with client.websocket_connect("/ws") as websocket:
        asyncio.run(
            runtime.event_bus.emit(
                EngineEvent(
                    event_type=BLOCK_DONE,
                    block_id="node-1",
                    data={"workflow_id": "wf-1", "outputs": {"port": "value"}},
                )
            )
        )
        message = websocket.receive_json()

    assert message["type"] == BLOCK_DONE
    assert message["block_id"] == "node-1"
    assert message["workflow_id"] == "wf-1"
    assert message["data"]["outputs"] == {"port": "value"}


def test_websocket_inbound_messages_emit_cancel_events(client: TestClient, runtime: ApiRuntime) -> None:
    """Inbound cancel messages should fan out onto the EventBus."""
    seen: list[tuple[str, str | None, str | None]] = []

    def capture(event: EngineEvent) -> None:
        seen.append((event.event_type, event.block_id, event.data.get("workflow_id")))

    runtime.event_bus.subscribe(CANCEL_BLOCK_REQUEST, capture)
    runtime.event_bus.subscribe(CANCEL_WORKFLOW_REQUEST, capture)
    try:
        with client.websocket_connect("/ws") as websocket:
            websocket.send_json({"type": "cancel_block", "workflow_id": "wf-2", "block_id": "node-3"})
            websocket.send_json({"type": "cancel_workflow", "workflow_id": "wf-2"})

        wait_for_condition(lambda: len(seen) == 2, timeout=2.0)
    finally:
        runtime.event_bus.unsubscribe(CANCEL_BLOCK_REQUEST, capture)
        runtime.event_bus.unsubscribe(CANCEL_WORKFLOW_REQUEST, capture)

    assert (CANCEL_BLOCK_REQUEST, "node-3", "wf-2") in seen
    assert (CANCEL_WORKFLOW_REQUEST, None, "wf-2") in seen


def test_websocket_replies_to_heartbeat_ping(client: TestClient, runtime: ApiRuntime) -> None:
    """#177: browser heartbeat pings receive a pong frame."""
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "ping"})
        message = websocket.receive_json()

    assert message == {"type": "pong"}


def test_websocket_handler_handles_cancelled_error_on_shutdown() -> None:
    """websocket_handler must exit cleanly when asyncio.CancelledError is raised.

    Regression test for #203: CancelledError was not caught alongside
    WebSocketDisconnect, causing the handler to hang on server shutdown.
    """

    async def _run() -> None:
        ws = AsyncMock()
        ws.accept = AsyncMock()
        # Simulate server shutdown: receive_text raises CancelledError
        ws.receive_text = AsyncMock(side_effect=asyncio.CancelledError)
        ws.send_json = AsyncMock(side_effect=asyncio.CancelledError)

        event_bus = EventBus()

        # Wrap in a task and cancel it after a short delay to simulate
        # server shutdown cancelling all tasks (which is the real scenario).
        task = asyncio.create_task(websocket_handler(ws, event_bus))
        # Give the handler a moment to start, then cancel
        await asyncio.sleep(0.05)
        task.cancel()
        # The handler should exit without propagating CancelledError
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(_run())


def test_last_gui_disconnect_cancels_active_workflow(monkeypatch: Any) -> None:
    """When the browser session disappears, running workflows must not leave lineage running."""

    async def _run() -> None:
        ws_module._gui_ws_clients.clear()
        if ws_module._gui_disconnect_cancel_task is not None:
            ws_module._gui_disconnect_cancel_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ws_module._gui_disconnect_cancel_task
            ws_module._gui_disconnect_cancel_task = None

        monkeypatch.setattr(ws_module, "_GUI_DISCONNECT_GRACE_SEC", 0.01)

        task = asyncio.create_task(asyncio.sleep(60))

        async def cancel_workflow() -> None:
            task.cancel()

        scheduler = SimpleNamespace(cancel_workflow=AsyncMock(side_effect=cancel_workflow))
        runtime = SimpleNamespace(workflow_runs={"wf-browser-owned": SimpleNamespace(task=task, scheduler=scheduler)})
        event_bus = EventBus()
        event_bus.runtime = runtime  # type: ignore[attr-defined]

        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.receive_text = AsyncMock(side_effect=asyncio.CancelledError)
        ws.send_json = AsyncMock(side_effect=asyncio.CancelledError)

        handler = asyncio.create_task(websocket_handler(ws, event_bus))
        await asyncio.sleep(0.02)
        handler.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await handler

        await asyncio.sleep(0.05)
        scheduler.cancel_workflow.assert_awaited_once()
        assert task.cancelled()

    asyncio.run(_run())
