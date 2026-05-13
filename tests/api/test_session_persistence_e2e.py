"""End-to-end test for #804 Bug 1 — session persistence across user turns.

Asserts the core persistence invariant: a single chat WebSocket that
sends N user_message frames produces exactly one ``init`` event. If a
new ``init`` event arrives on each turn, the backend is silently
respawning the claude subprocess and the persistence design is broken.

Uses the multi-turn ``stub_claude.py`` fixture (extended in #804 to
loop on stdin instead of exiting after one turn).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scieasy.ai.agent.claude_code import ClaudeCodeProvider
from scieasy.ai.agent.provider import PermissionMode
from scieasy.ai.agent.session import AgentSessionManager
from scieasy.api.app import create_app
from scieasy.api.deps import get_agent_session_manager
from scieasy.api.routes import ai as ai_routes

STUB_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "stub_claude.py"


@pytest.fixture
def app() -> Any:
    return create_app()


@pytest.fixture
def fresh_manager() -> AgentSessionManager:
    return AgentSessionManager()


def _override_with_stub(app: Any, manager: AgentSessionManager) -> None:
    app.dependency_overrides[get_agent_session_manager] = lambda: manager


def _patch_start_default_session(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_start(
        *,
        manager: Any,
        project_dir: Path,
        chat_id: str,
        resume_session_id: str | None = None,
        permission_mode_str: str = "strict",
    ) -> Any:
        provider = ClaudeCodeProvider(binary_override=STUB_PATH)
        return await manager.start_session(
            project_dir=project_dir,
            chat_id=chat_id,
            provider=provider,
            system_prompt="test",
            mcp_config={},
            permission_mode=PermissionMode.STRICT,
            resume_session_id=resume_session_id,
        )

    monkeypatch.setattr(ai_routes, "_start_default_session", _stub_start)


def _collect_events_until(ws: Any, *, kind: str, max_events: int = 20) -> list[dict[str, Any]]:
    """Drain events from the WS until one with ``event.kind == kind`` arrives.

    Returns the full list of events seen (including the terminating one).
    """
    collected: list[dict[str, Any]] = []
    for _ in range(max_events):
        try:
            payload = ws.receive_json()
        except Exception:
            break
        if payload.get("type") != "agent_event":
            continue
        event = payload.get("event") or {}
        collected.append(event)
        if event.get("kind") == kind:
            return collected
    return collected


def test_two_user_messages_produce_one_init(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#804 Bug 1: session must persist across user turns.

    Sends 2 ``user_message`` frames on the same WS. Counts ``init``
    events across both responses. The persistence design says exactly
    one ``init`` should arrive — emitted when the subprocess spawned on
    turn 1, NOT re-emitted on turn 2.
    """
    _override_with_stub(app, fresh_manager)
    _patch_start_default_session(monkeypatch)

    with (
        TestClient(app) as client,
        client.websocket_connect(
            f"/api/ai/chat/persist-multi?project_dir={tmp_path}"
        ) as ws,
    ):
        # Turn 1: send first message and drain until ``done``.
        ws.send_text(json.dumps({"type": "user_message", "content": "hi"}))
        turn1 = _collect_events_until(ws, kind="done")
        # Turn 2: send second message on the SAME WS. Expect another
        # turn's worth of events but NO new ``init``.
        ws.send_text(json.dumps({"type": "user_message", "content": "again"}))
        turn2 = _collect_events_until(ws, kind="done")

    all_events = turn1 + turn2
    init_count = sum(1 for ev in all_events if ev.get("kind") == "init")
    assert init_count == 1, (
        f"expected exactly 1 init event across 2 user_messages on the "
        f"same WS, got {init_count}. all events: {all_events}"
    )
    # Sanity: each turn should have produced at least a ``done`` event.
    assert any(ev.get("kind") == "done" for ev in turn1), f"turn1 missing done: {turn1}"
    assert any(ev.get("kind") == "done" for ev in turn2), f"turn2 missing done: {turn2}"

    asyncio.run(fresh_manager.shutdown_all())


def test_two_user_messages_share_one_session(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#804 Bug 1: manager session count stays at 1 across two turns."""
    _override_with_stub(app, fresh_manager)
    _patch_start_default_session(monkeypatch)

    with (
        TestClient(app) as client,
        client.websocket_connect(
            f"/api/ai/chat/persist-count?project_dir={tmp_path}"
        ) as ws,
    ):
        ws.send_text(json.dumps({"type": "user_message", "content": "hi"}))
        _collect_events_until(ws, kind="done")
        # After turn 1 the session must be alive.
        live_after_t1 = fresh_manager.live_count_for(tmp_path)
        assert live_after_t1 == 1, f"after turn 1 expected 1 live session, got {live_after_t1}"
        ws.send_text(json.dumps({"type": "user_message", "content": "again"}))
        _collect_events_until(ws, kind="done")
        # After turn 2 still exactly 1 — no respawn.
        live_after_t2 = fresh_manager.live_count_for(tmp_path)
        assert live_after_t2 == 1, f"after turn 2 expected 1 live session, got {live_after_t2}"

    asyncio.run(fresh_manager.shutdown_all())
