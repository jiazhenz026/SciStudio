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
    token = gui_presence.register("ws-0123456789abcdef")
    gui_presence.unregister("ws-0123456789abcdef", token)

    asyncio.run(ws_module._close_panel_contexts_after_grace(_event_bus_with(store), "ws-0123456789abcdef"))

    assert closed == ["ws-0123456789abcdef"]


def test_a_workspace_that_comes_back_keeps_its_miniapp() -> None:
    """The debounce: a reconnect inside the grace period re-registers the id."""
    store, closed = _store()
    client_id = "ws-fedcba9876543210"
    token: object | None = None

    async def scenario() -> None:
        nonlocal token
        task = asyncio.create_task(ws_module._close_panel_contexts_after_grace(_event_bus_with(store), client_id))
        await asyncio.sleep(0.01)
        token = gui_presence.register(client_id)
        await task

    asyncio.run(scenario())
    try:
        assert closed == []
    finally:
        gui_presence.unregister(client_id, token)


def test_the_grace_period_survives_a_runtime_without_contexts() -> None:
    """A bus with no runtime is a shutdown in progress, not a crash."""
    event_bus = EventBus()
    asyncio.run(ws_module._close_panel_contexts_after_grace(event_bus, "ws-0000000000000000"))


@pytest.mark.parametrize("close_old_first", [True, False])
def test_overlapping_connections_keep_presence_until_both_close(close_old_first: bool) -> None:
    client_id = "ws-1111111111111111"
    old = gui_presence.register(client_id)
    replacement = gui_presence.register(client_id)
    first, last = (old, replacement) if close_old_first else (replacement, old)
    try:
        gui_presence.unregister(client_id, first)
        gui_presence.unregister(client_id, first)  # Duplicate cleanup is harmless.
        assert client_id in gui_presence.connected()
        assert gui_presence.any_connected()
        store, closed = _store()
        asyncio.run(ws_module._close_panel_contexts_after_grace(_event_bus_with(store), client_id))
        assert closed == []
    finally:
        gui_presence.unregister(client_id, last)
    assert client_id not in gui_presence.connected()
    asyncio.run(ws_module._close_panel_contexts_after_grace(_event_bus_with(store), client_id))
    assert closed == [client_id]


def test_old_socket_cleanup_does_not_unregister_its_replacement(client: TestClient) -> None:
    with client.websocket_connect("/ws") as old:
        client_id = old.receive_json()["client_id"]
        with client.websocket_connect(f"/ws?client_id={client_id}") as replacement:
            assert replacement.receive_json()["client_id"] == client_id
            old.close()
            # A ping proves the replacement still has working socket pumps.
            replacement.send_json({"type": "ping"})
            assert replacement.receive_json()["type"] == "pong"
            assert client_id in gui_presence.connected()
    assert client_id not in gui_presence.connected()


def test_reconnect_gets_a_fresh_grace_period_for_its_next_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        entered: asyncio.Queue[asyncio.Event] = asyncio.Queue()
        closed: list[str] = []

        async def grace(_bus: EventBus, client_id: str) -> None:
            release = asyncio.Event()
            await entered.put(release)
            await release.wait()
            closed.append(client_id)

        monkeypatch.setattr(ws_module, "_close_panel_contexts_after_grace", grace)
        client_id = "ws-2222222222222222"
        bus = EventBus()
        ws_module._schedule_panel_close(bus, client_id)
        old_timer = ws_module._panel_close_tasks[client_id]
        old_release = await entered.get()
        token = gui_presence.register(client_id)
        ws_module._cancel_panel_close(client_id)
        await asyncio.gather(old_timer, return_exceptions=True)
        assert old_timer.cancelled()
        # An older socket's finally must not start a timer while connected.
        ws_module._schedule_panel_close(bus, client_id)
        assert client_id not in ws_module._panel_close_tasks
        gui_presence.unregister(client_id, token)
        ws_module._schedule_panel_close(bus, client_id)
        new_timer = ws_module._panel_close_tasks[client_id]
        new_release = await entered.get()
        old_release.set()
        await asyncio.sleep(0)
        assert closed == []
        assert ws_module._panel_close_tasks[client_id] is new_timer
        new_release.set()
        await new_timer
        await asyncio.sleep(0)
        assert closed == [client_id]
        assert client_id not in ws_module._panel_close_tasks

    asyncio.run(scenario())
