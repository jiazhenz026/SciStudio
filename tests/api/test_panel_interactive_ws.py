"""New panel decisions are claimed before the unchanged interactive WS event."""

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from scistudio.api.ws import websocket_handler
from tests.panels.conftest import make_runtime
from tests.panels.test_panel_contexts import waiting


def test_websocket_claims_context_without_changing_engine_event(tmp_path):
    runtime, store = make_runtime(tmp_path)
    context = waiting(runtime, store)
    emitted = []
    runtime.event_bus.subscribe("interactive_complete", lambda event: emitted.append(event))
    app = FastAPI()

    @app.websocket("/ws")
    async def route(socket: WebSocket):
        await websocket_handler(socket, runtime.event_bus)

    with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
        websocket.send_json(
            {"type": "interactive_complete", "workflow_id": "wf", "block_id": "block", "data": {"chosen": True}}
        )
        error = websocket.receive_json()
        assert error["type"] == "panel_error" and error["error"]["code"] == "missing_context"
        assert error["workflow_id"] == "wf" and error["block_id"] == "block"
        assert not emitted
        websocket.send_json(
            {
                "type": "interactive_complete",
                "workflow_id": "wf",
                "block_id": "block",
                "context_id": context.context_id,
                "data": {"chosen": True},
            }
        )
        websocket.send_json({"type": "ping"})
        assert websocket.receive_json() == {
            "type": "panel_accepted",
            "context_id": context.context_id,
            "workflow_id": "wf",
            "block_id": "block",
        }
        assert websocket.receive_json()["type"] == "pong"
        assert len(emitted) == 1
        assert emitted[0].data == {"workflow_id": "wf", "response": {"chosen": True}}
        assert context.context_id not in store.contexts
        websocket.send_json(
            {
                "type": "interactive_complete",
                "workflow_id": "wf",
                "block_id": "block",
                "context_id": context.context_id,
                "data": {"chosen": False},
            }
        )
        duplicate = websocket.receive_json()
        assert duplicate["type"] == "panel_error" and duplicate["context_id"] == context.context_id
        assert duplicate["workflow_id"] == "wf" and duplicate["block_id"] == "block"
        assert len(emitted) == 1


def test_ack_waits_for_dispatch_and_allows_close_only_after_acceptance(tmp_path, monkeypatch):
    import asyncio
    from queue import Empty, Queue
    from threading import Event, Thread

    import pytest

    runtime, store = make_runtime(tmp_path)
    context = waiting(runtime, store)
    entered, release = Event(), Event()
    original_emit = runtime.event_bus.emit
    accepted = Queue()
    emitted = []
    runtime.event_bus.subscribe("interactive_complete", lambda event: emitted.append(event))

    async def delayed_emit(event):
        entered.set()
        await asyncio.to_thread(release.wait, 5)
        await original_emit(event)

    monkeypatch.setattr(runtime.event_bus, "emit", delayed_emit)
    app = FastAPI()

    @app.websocket("/ws")
    async def route(socket: WebSocket):
        await websocket_handler(socket, runtime.event_bus)

    with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
        websocket.send_json(
            {
                "type": "interactive_complete",
                "workflow_id": "wf",
                "block_id": "block",
                "context_id": context.context_id,
                "data": {"chosen": True},
            }
        )
        receiver = Thread(target=lambda: accepted.put(websocket.receive_json()))
        receiver.start()
        try:
            assert entered.wait(5)
            with pytest.raises(Empty):
                accepted.get(timeout=0.05)
            assert not emitted
        finally:
            release.set()
        ack = accepted.get(timeout=5)
        receiver.join(timeout=5)
        assert ack == {
            "type": "panel_accepted",
            "context_id": context.context_id,
            "workflow_id": "wf",
            "block_id": "block",
        }
        store.close(context.context_id)  # Host teardown happens only after the scoped acknowledgement.
        assert len(emitted) == 1


def test_dispatch_failure_returns_scoped_error_without_accepting(tmp_path, monkeypatch):
    runtime, store = make_runtime(tmp_path)
    context = waiting(runtime, store)

    async def failed_emit(event):
        raise RuntimeError("injected dispatch failure")

    monkeypatch.setattr(runtime.event_bus, "emit", failed_emit)
    app = FastAPI()

    @app.websocket("/ws")
    async def route(socket: WebSocket):
        await websocket_handler(socket, runtime.event_bus)

    with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
        websocket.send_json(
            {
                "type": "interactive_complete",
                "workflow_id": "wf",
                "block_id": "block",
                "context_id": context.context_id,
                "data": {"chosen": True},
            }
        )
        error = websocket.receive_json()
        assert error["type"] == "panel_error" and error["error"]["code"] == "completion_failed"
        assert error["context_id"] == context.context_id and error["workflow_id"] == "wf"
        websocket.send_json({"type": "ping"})
        assert websocket.receive_json() == {"type": "pong"}
