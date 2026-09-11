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
        assert websocket.receive_json()["type"] == "panel_error"
        assert len(emitted) == 1
