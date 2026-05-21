"""Tests that ``git.head_changed`` engine events flow through the WebSocket.

ADR-039 §3.8: HEAD or branch-tip movement → ``GIT_HEAD_CHANGED`` engine
event → ``/ws`` outbound loop → connected client JSON frame.

The watcher itself is unit-tested in ``test_workflow_watcher_git.py``;
this file covers the wire bridge from EventBus to the ``/ws`` handler.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime
from scistudio.api.ws import _OUTBOUND_EVENTS
from scistudio.engine.events import GIT_HEAD_CHANGED, EngineEvent


def test_git_head_changed_in_outbound_events() -> None:
    """ADR-039 §3.8: the constant must be in the WS outbound allowlist."""
    assert GIT_HEAD_CHANGED in _OUTBOUND_EVENTS


def test_websocket_receives_git_head_changed_frame(client: TestClient, runtime: ApiRuntime) -> None:
    """A ``GIT_HEAD_CHANGED`` engine event is forwarded to connected clients."""
    sha = "f" * 40
    with client.websocket_connect("/ws") as websocket:
        asyncio.run(
            runtime.event_bus.emit(
                EngineEvent(
                    event_type=GIT_HEAD_CHANGED,
                    data={
                        "commit_sha": sha,
                        "ref": "refs/heads/main",
                        "kind": "refs",
                    },
                )
            )
        )
        message = websocket.receive_json()

    assert message["type"] == GIT_HEAD_CHANGED
    assert message["data"]["commit_sha"] == sha
    assert message["data"]["ref"] == "refs/heads/main"
    assert message["data"]["kind"] == "refs"


def test_websocket_forwards_head_event_with_null_sha(client: TestClient, runtime: ApiRuntime) -> None:
    """A ``GIT_HEAD_CHANGED`` with ``commit_sha=None`` must still flow through.

    The watcher emits ``commit_sha=None`` when the on-disk HEAD/ref file
    cannot be read (race against an in-progress git operation). The
    frontend invalidates its cache either way; the WS bridge must not
    drop the frame.
    """
    with client.websocket_connect("/ws") as websocket:
        asyncio.run(
            runtime.event_bus.emit(
                EngineEvent(
                    event_type=GIT_HEAD_CHANGED,
                    data={"commit_sha": None, "ref": "HEAD", "kind": "head"},
                )
            )
        )
        message = websocket.receive_json()

    assert message["type"] == GIT_HEAD_CHANGED
    assert message["data"]["commit_sha"] is None
    assert message["data"]["ref"] == "HEAD"
