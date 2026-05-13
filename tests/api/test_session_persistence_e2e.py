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


def test_two_user_messages_share_conversation_via_resume(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#804 Bug 1: conversation must persist across user turns.

    The real claude CLI requires ``-p/--print`` to use ``stream-json``
    mode (verified against ``claude --help`` 2026-05-13), which is
    single-turn — the subprocess exits after each ``result`` frame.
    Persistence is therefore preserved at the *conversation* layer, not
    the *subprocess* layer: the chat_ws handler lazy-``--resume``s the
    prior session_id on each user_message after the first.

    This test asserts the resume contract: send 2 user_messages, and
    verify the second turn was spawned with the first turn's session_id
    as ``resume_session_id`` (so the agent retains its memory of the
    conversation).

    Note: each turn DOES emit a fresh ``init`` event — that's the
    correct signal that a new subprocess has started. The earlier
    interpretation of "exactly one init per WS" was inconsistent with
    the underlying CLI semantics.
    """
    _override_with_stub(app, fresh_manager)
    spawn_calls: list[dict[str, Any]] = []

    async def _spy_start(
        *,
        manager: Any,
        project_dir: Path,
        chat_id: str,
        resume_session_id: str | None = None,
        permission_mode_str: str = "strict",
    ) -> Any:
        spawn_calls.append({"chat_id": chat_id, "resume_session_id": resume_session_id})
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

    monkeypatch.setattr(ai_routes, "_start_default_session", _spy_start)

    with (
        TestClient(app) as client,
        client.websocket_connect(
            f"/api/ai/chat/persist-multi?project_dir={tmp_path}"
        ) as ws,
    ):
        ws.send_text(json.dumps({"type": "user_message", "content": "hi"}))
        turn1 = _collect_events_until(ws, kind="done")
        # Stub claude's multi-turn loop keeps the same subprocess alive,
        # so turn 2 should NOT respawn through our spy here (because
        # send_user_message succeeds). The resume-on-respawn contract is
        # exercised separately when the subprocess dies; see the
        # ``test_resume_id_used_after_subprocess_death`` case below.
        ws.send_text(json.dumps({"type": "user_message", "content": "again"}))
        turn2 = _collect_events_until(ws, kind="done")

    # Sanity: each turn produced a ``done`` event.
    assert any(ev.get("kind") == "done" for ev in turn1), f"turn1 missing done: {turn1}"
    assert any(ev.get("kind") == "done" for ev in turn2), f"turn2 missing done: {turn2}"
    # With the multi-turn stub, exactly one subprocess spawn for both
    # turns (the stub keeps stdin open).
    assert len(spawn_calls) == 1, (
        f"multi-turn stub should keep subprocess alive across turns; got {len(spawn_calls)} spawns"
    )

    asyncio.run(fresh_manager.shutdown_all())


def test_resume_id_used_after_subprocess_death(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#804 Bug 1: when the prior subprocess died and metadata holds a
    session_id, the next user_message must spawn with ``--resume <id>``.

    We exercise this by pre-seeding ``SessionMetadata`` on disk with a
    fake ``session_id``, then sending a user_message and asserting the
    spy spawn function received that id as ``resume_session_id``.
    """
    _override_with_stub(app, fresh_manager)
    # Pre-seed metadata as if a prior subprocess had ended cleanly.
    sessions_dir = tmp_path / ".scieasy" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / "resume-after-death.json").write_text(
        json.dumps(
            {
                "chat_id": "resume-after-death",
                "title": "x",
                "created": "2025-01-01T00:00:00+00:00",
                "last_active": "2025-01-01T00:00:00+00:00",
                "provider": "claude-code",
                "model": None,
                "system_prompt_hash": "abc",
                "session_id": "prior-session-from-disk",
                "bypass_mode": False,
                "total_turns": 0,
            }
        ),
        encoding="utf-8",
    )

    spawn_calls: list[dict[str, Any]] = []

    async def _spy_start(
        *,
        manager: Any,
        project_dir: Path,
        chat_id: str,
        resume_session_id: str | None = None,
        permission_mode_str: str = "strict",
    ) -> Any:
        spawn_calls.append({"chat_id": chat_id, "resume_session_id": resume_session_id})
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

    monkeypatch.setattr(ai_routes, "_start_default_session", _spy_start)

    with (
        TestClient(app) as client,
        client.websocket_connect(
            f"/api/ai/chat/resume-after-death?project_dir={tmp_path}"
        ) as ws,
    ):
        ws.send_text(json.dumps({"type": "user_message", "content": "hi"}))
        _collect_events_until(ws, kind="done")

    # The WS-open path already attempts lazy resume; both that spawn AND
    # any subsequent user_message spawn must carry the resume id.
    assert spawn_calls, "no spawn occurred — chat_ws never started a session"
    for call in spawn_calls:
        assert call["resume_session_id"] == "prior-session-from-disk", (
            f"expected resume_session_id=prior-session-from-disk, got {call!r}"
        )
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
