"""ADR-054 MiniApp FR-013/FR-022/FR-030: the workspace client id and the panel events.

User Story 7 acceptance scenario 4: when the browser is reloaded or closed, a
MiniApp's context closes and its process ends after the grace period — and, the
other half of the same rule, a workspace whose socket merely dropped and came
back inside that period keeps what it had running.
"""

from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

import scistudio.api.ws as ws_module
from scistudio.api.runtime import ApiRuntime
from scistudio.api.ws import _OUTBOUND_EVENTS, PANEL_FILES_CHANGED, PANEL_OPEN_MINIAPP
from scistudio.engine import gui_presence
from scistudio.engine.events import EngineEvent, EventBus


def test_panel_events_are_outbound() -> None:
    """FR-022/FR-030: an event type absent from the set never reaches the browser."""
    assert PANEL_FILES_CHANGED == "panel.files_changed"
    assert PANEL_OPEN_MINIAPP == "panel.open_miniapp"
    assert PANEL_FILES_CHANGED in _OUTBOUND_EVENTS
    assert PANEL_OPEN_MINIAPP in _OUTBOUND_EVENTS


def test_panel_events_reach_a_connected_client(client: TestClient, runtime: ApiRuntime) -> None:
    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()  # the hello frame
        asyncio.run(
            runtime.event_bus.emit(
                EngineEvent(
                    event_type=PANEL_OPEN_MINIAPP,
                    data={"panel_id": "threshold_explorer", "workflow_id": "wf", "block_id": "seg", "port": "out"},
                )
            )
        )
        message = websocket.receive_json()

    assert message["type"] == "panel.open_miniapp"
    assert message["data"]["panel_id"] == "threshold_explorer"


def test_hello_is_the_first_frame_and_registers_the_client(client: TestClient) -> None:
    """FR-013: the browser has to know what to quote as ``ws_client_id``."""
    with client.websocket_connect("/ws") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello"
        assert re.fullmatch(r"ws-[0-9a-f]{16}", hello["client_id"])
        assert hello["client_id"] in gui_presence.connected()

    assert hello["client_id"] not in gui_presence.connected()


def test_a_reconnecting_workspace_may_keep_its_identity(client: TestClient) -> None:
    """A dropped socket is not a closed workspace: the id can be quoted back."""
    with client.websocket_connect("/ws") as first:
        given = first.receive_json()["client_id"]

    with client.websocket_connect(f"/ws?client_id={given}") as second:
        assert second.receive_json()["client_id"] == given

    with client.websocket_connect("/ws?client_id=not-a-client-id") as third:
        assert third.receive_json()["client_id"] != "not-a-client-id"


def _store() -> tuple[Any, list[str]]:
    closed: list[str] = []
    store = SimpleNamespace(close_for_client=closed.append)
    return store, closed


def _event_bus_with(store: Any) -> EventBus:
    event_bus = EventBus()
    event_bus.runtime = SimpleNamespace(_panel_contexts=store)
    return event_bus


@pytest.fixture(autouse=True)
def short_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCISTUDIO_PANEL_CLIENT_GRACE", "0.05")


def test_a_workspace_that_stays_away_loses_its_miniapp() -> None:
    """US7 AS4: the context closes once the client has been gone for the grace period."""
    store, closed = _store()
    gui_presence.register("ws-0123456789abcdef")
    gui_presence.unregister("ws-0123456789abcdef")

    asyncio.run(ws_module._close_panel_contexts_after_grace(_event_bus_with(store), "ws-0123456789abcdef"))

    assert closed == ["ws-0123456789abcdef"]


def test_a_workspace_that_comes_back_keeps_its_miniapp() -> None:
    """The debounce: a reconnect inside the grace period re-registers the id."""
    store, closed = _store()
    client_id = "ws-fedcba9876543210"
    gui_presence.unregister(client_id)

    async def scenario() -> None:
        task = asyncio.create_task(ws_module._close_panel_contexts_after_grace(_event_bus_with(store), client_id))
        await asyncio.sleep(0.01)
        gui_presence.register(client_id)
        await task

    asyncio.run(scenario())
    try:
        assert closed == []
    finally:
        gui_presence.unregister(client_id)


def test_the_grace_period_survives_a_runtime_without_contexts() -> None:
    """A bus with no runtime is a shutdown in progress, not a crash."""
    event_bus = EventBus()
    asyncio.run(ws_module._close_panel_contexts_after_grace(event_bus, "ws-0000000000000000"))
