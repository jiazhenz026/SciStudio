"""ADR-035 §3.10: engine-initiated PTY tab open + internal IPC routes.

Exercises:
* :func:`open_engine_initiated_tab` direct synchronous call (allocation,
  registration, broadcast, cap, error paths).
* The two internal HTTP endpoints — auth, payload validation, happy path.

The PTY spawn helper is monkeypatched (same seam used by ``test_ai_pty.py``)
so no real claude / codex binary is launched.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scistudio.ai.agent.terminal import PtyProcess
from scistudio.api.routes import ai_pty
from scistudio.api.routes.ai_pty import (
    _active_ptys,
    _engine_tab_to_run,
    broadcast_ai_pty_message,
    open_engine_initiated_tab,
    register_ai_pty_subscriber,
    unregister_ai_pty_subscriber,
)


def _echo_argv() -> list[str]:
    return [
        sys.executable,
        "-c",
        (
            "import sys\n"
            "sys.stdout.write('ENGINE-READY\\n')\n"
            "sys.stdout.flush()\n"
            "for line in iter(sys.stdin.readline, ''):\n"
            "    if not line:\n"
            "        break\n"
            "    sys.stdout.write(line)\n"
            "    sys.stdout.flush()\n"
        ),
    ]


@pytest.fixture(autouse=True)
def _fake_spawn(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Replace _spawn with a tiny echo subprocess + reset state."""

    def fake(
        *,
        provider: str,
        project_dir: Path,
        dangerous: bool,
        extra_env: dict[str, str] | None = None,
    ) -> PtyProcess:
        return PtyProcess(_echo_argv(), cwd=project_dir, cols=80, rows=24, extra_env=extra_env)

    monkeypatch.setattr(ai_pty._state, "_spawn", fake)
    _active_ptys.clear()
    _engine_tab_to_run.clear()
    yield
    for pty in list(_active_ptys.values()):
        with contextlib.suppress(Exception):
            pty.kill_tree()
    _active_ptys.clear()
    _engine_tab_to_run.clear()


def _spec_kw(tmp_path: Path, run_id: str = "rid-1", permission_mode: str = "safe") -> dict[str, Any]:
    return {
        "title": "🤖 demo",
        "spawn_argv": ["claude", "--append-system-prompt", "@/tmp/p"],
        "cwd": str(tmp_path),
        "initial_stdin": "Hello agent\n",
        "block_run_id": run_id,
        "permission_mode": permission_mode,
    }


# ---------------------------------------------------------------------------
# open_engine_initiated_tab — direct sync call
# ---------------------------------------------------------------------------


def test_open_engine_tab_returns_tab_id_and_registers(tmp_path: Path) -> None:
    tab_id = open_engine_initiated_tab(**_spec_kw(tmp_path))
    assert isinstance(tab_id, str) and len(tab_id) == 12
    assert tab_id in _active_ptys
    assert _engine_tab_to_run[tab_id] == "rid-1"


def test_open_engine_tab_stamps_metadata_on_pty(tmp_path: Path) -> None:
    tab_id = open_engine_initiated_tab(**_spec_kw(tmp_path, run_id="rid-2"))
    pty = _active_ptys[tab_id]
    assert pty._engine_block_run_id == "rid-2"
    assert pty._engine_initial_stdin == "Hello agent\n"


def test_open_engine_tab_rejects_relative_cwd() -> None:
    with pytest.raises(RuntimeError, match="absolute"):
        open_engine_initiated_tab(
            title="x",
            spawn_argv=["claude"],
            cwd="rel/path",
            initial_stdin="",
            block_run_id="rid",
            permission_mode="safe",
        )


def test_open_engine_tab_rejects_unknown_permission_mode(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="permission_mode"):
        open_engine_initiated_tab(
            title="x",
            spawn_argv=["claude"],
            cwd=str(tmp_path),
            initial_stdin="",
            block_run_id="rid",
            permission_mode="totally-fake",
        )


def test_open_engine_tab_picks_codex_provider_from_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake(
        *,
        provider: str,
        project_dir: Path,
        dangerous: bool,
        extra_env: dict[str, str] | None = None,
    ) -> PtyProcess:
        captured["provider"] = provider
        captured["dangerous"] = dangerous
        return PtyProcess(_echo_argv(), cwd=project_dir, cols=80, rows=24, extra_env=extra_env)

    monkeypatch.setattr(ai_pty._state, "_spawn", fake)
    open_engine_initiated_tab(
        title="x",
        spawn_argv=["codex", "--dangerously-bypass-approvals-and-sandbox"],
        cwd=str(tmp_path),
        initial_stdin="",
        block_run_id="rid-codex",
        permission_mode="bypass",
    )
    assert captured["provider"] == "codex"
    assert captured["dangerous"] is True


def test_open_engine_tab_respects_pty_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_pty._state, "MAX_ACTIVE_PTYS", 1)
    open_engine_initiated_tab(**_spec_kw(tmp_path, run_id="rid-A"))
    with pytest.raises(RuntimeError, match="cap"):
        open_engine_initiated_tab(**_spec_kw(tmp_path, run_id="rid-B"))


def test_open_engine_tab_spawn_failure_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(
        *,
        provider: str,
        project_dir: Path,
        dangerous: bool,
        extra_env: dict[str, str] | None = None,
    ) -> PtyProcess:
        raise FileNotFoundError("claude binary missing")

    monkeypatch.setattr(ai_pty._state, "_spawn", boom)
    with pytest.raises(FileNotFoundError):
        open_engine_initiated_tab(**_spec_kw(tmp_path))


# ---------------------------------------------------------------------------
# Broadcaster registry
# ---------------------------------------------------------------------------


def test_broadcast_fans_out_to_subscribers() -> None:
    received_a: list[dict[str, Any]] = []
    received_b: list[dict[str, Any]] = []

    def cb_a(msg: dict[str, Any]) -> None:
        received_a.append(msg)

    def cb_b(msg: dict[str, Any]) -> None:
        received_b.append(msg)

    register_ai_pty_subscriber(cb_a)
    register_ai_pty_subscriber(cb_b)
    try:
        asyncio.run(broadcast_ai_pty_message({"type": "block_pty_opened", "tab_id": "x"}))
        assert received_a == received_b == [{"type": "block_pty_opened", "tab_id": "x"}]
    finally:
        unregister_ai_pty_subscriber(cb_a)
        unregister_ai_pty_subscriber(cb_b)


def test_broadcast_swallows_subscriber_exception() -> None:
    received: list[dict[str, Any]] = []

    def good(msg: dict[str, Any]) -> None:
        received.append(msg)

    def bad(msg: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    register_ai_pty_subscriber(bad)
    register_ai_pty_subscriber(good)
    try:
        # Must not raise even though bad raised.
        asyncio.run(broadcast_ai_pty_message({"type": "block_pty_closed"}))
        assert received == [{"type": "block_pty_closed"}]
    finally:
        unregister_ai_pty_subscriber(bad)
        unregister_ai_pty_subscriber(good)


def test_unregister_unknown_is_noop() -> None:
    # Should not raise.
    unregister_ai_pty_subscriber(lambda m: None)


# ---------------------------------------------------------------------------
# Internal HTTP endpoints
# ---------------------------------------------------------------------------


@pytest.fixture()
def _ipc_token(monkeypatch: pytest.MonkeyPatch) -> str:
    tok = "test-secret-token-xyz"
    monkeypatch.setenv("SCISTUDIO_ENGINE_IPC_TOKEN", tok)
    return tok


def test_internal_request_tab_happy_path(client: TestClient, opened_project: Path, _ipc_token: str) -> None:
    resp = client.post(
        "/api/ai/pty/internal/request-tab",
        json={
            "type": "request_pty_tab",
            "spec": {
                "title": "🤖 t",
                "spawn_argv": ["claude"],
                "cwd": str(opened_project),
                "initial_stdin": "hi\n",
                "block_run_id": "rid-http-1",
                "permission_mode": "safe",
            },
        },
        headers={"X-SciStudio-IPC-Token": _ipc_token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert isinstance(body["tab_id"], str) and len(body["tab_id"]) == 12


def test_internal_request_tab_bad_token_401(client: TestClient, opened_project: Path, _ipc_token: str) -> None:
    resp = client.post(
        "/api/ai/pty/internal/request-tab",
        json={"type": "request_pty_tab", "spec": {"cwd": str(opened_project)}},
        headers={"X-SciStudio-IPC-Token": "wrong-token"},
    )
    assert resp.status_code == 401


def test_internal_request_tab_missing_token_401(client: TestClient, opened_project: Path, _ipc_token: str) -> None:
    resp = client.post(
        "/api/ai/pty/internal/request-tab",
        json={"type": "request_pty_tab", "spec": {"cwd": str(opened_project)}},
    )
    assert resp.status_code == 401


def test_internal_request_tab_wrong_type_400(client: TestClient, _ipc_token: str) -> None:
    resp = client.post(
        "/api/ai/pty/internal/request-tab",
        json={"type": "wrong", "spec": {}},
        headers={"X-SciStudio-IPC-Token": _ipc_token},
    )
    assert resp.status_code == 400


def test_internal_request_tab_cap_returns_503(
    client: TestClient,
    opened_project: Path,
    _ipc_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ai_pty._state, "MAX_ACTIVE_PTYS", 0)
    resp = client.post(
        "/api/ai/pty/internal/request-tab",
        json={
            "type": "request_pty_tab",
            "spec": {
                "title": "t",
                "spawn_argv": ["claude"],
                "cwd": str(opened_project),
                "initial_stdin": "",
                "block_run_id": "rid-cap",
                "permission_mode": "safe",
            },
        },
        headers={"X-SciStudio-IPC-Token": _ipc_token},
    )
    assert resp.status_code == 503


def test_internal_request_tab_soft_failure_returns_error_envelope(
    client: TestClient,
    opened_project: Path,
    _ipc_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-cap RuntimeError surfaces as a 200 with error envelope."""

    def boom(**kw: Any) -> str:
        raise RuntimeError("permission_mode totally-fake")

    monkeypatch.setattr(ai_pty.engine, "open_engine_initiated_tab", boom)
    resp = client.post(
        "/api/ai/pty/internal/request-tab",
        json={
            "type": "request_pty_tab",
            "spec": {
                "title": "t",
                "spawn_argv": ["claude"],
                "cwd": str(opened_project),
                "initial_stdin": "",
                "block_run_id": "rid-soft",
                "permission_mode": "safe",
            },
        },
        headers={"X-SciStudio-IPC-Token": _ipc_token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tab_id"] is None
    assert "permission_mode" in body["error"]


def test_internal_notify_happy_path(client: TestClient, opened_project: Path, _ipc_token: str) -> None:
    # Open a tab first so notify can resolve tab_id.
    open_resp = client.post(
        "/api/ai/pty/internal/request-tab",
        json={
            "type": "request_pty_tab",
            "spec": {
                "title": "🤖 t",
                "spawn_argv": ["claude"],
                "cwd": str(opened_project),
                "initial_stdin": "",
                "block_run_id": "rid-notify-1",
                "permission_mode": "safe",
            },
        },
        headers={"X-SciStudio-IPC-Token": _ipc_token},
    )
    assert open_resp.status_code == 200

    received: list[dict[str, Any]] = []

    def cb(msg: dict[str, Any]) -> None:
        received.append(msg)

    register_ai_pty_subscriber(cb)
    try:
        resp = client.post(
            "/api/ai/pty/internal/notify",
            json={
                "type": "notify_block_pty_event",
                "block_run_id": "rid-notify-1",
                "event": "completed",
                "detail": {"outputs": 1},
            },
            headers={"X-SciStudio-IPC-Token": _ipc_token},
        )
        assert resp.status_code == 204
    finally:
        unregister_ai_pty_subscriber(cb)

    assert len(received) >= 1
    msg = next(m for m in received if m["type"] == "block_pty_closed")
    assert msg["block_run_id"] == "rid-notify-1"
    assert msg["event"] == "completed"
    assert msg["detail"] == {"outputs": 1}


def test_internal_notify_unknown_event_400(client: TestClient, _ipc_token: str) -> None:
    resp = client.post(
        "/api/ai/pty/internal/notify",
        json={
            "type": "notify_block_pty_event",
            "block_run_id": "rid",
            "event": "not-a-real-event",
        },
        headers={"X-SciStudio-IPC-Token": _ipc_token},
    )
    assert resp.status_code == 400


def test_internal_notify_bad_token_401(client: TestClient, _ipc_token: str) -> None:
    resp = client.post(
        "/api/ai/pty/internal/notify",
        json={
            "type": "notify_block_pty_event",
            "block_run_id": "rid",
            "event": "completed",
        },
        headers={"X-SciStudio-IPC-Token": "wrong"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# WS forwards block_pty_opened (integration through the /ws handler)
# ---------------------------------------------------------------------------


def test_ws_forwards_block_pty_opened(client: TestClient, opened_project: Path, _ipc_token: str) -> None:
    """End-to-end: open a tab via internal HTTP → /ws receives the broadcast."""
    with client.websocket_connect("/ws") as ws:
        # Trigger an engine-initiated tab open.
        resp = client.post(
            "/api/ai/pty/internal/request-tab",
            json={
                "type": "request_pty_tab",
                "spec": {
                    "title": "🤖 ws-test",
                    "spawn_argv": ["claude"],
                    "cwd": str(opened_project),
                    "initial_stdin": "",
                    "block_run_id": "rid-ws",
                    "permission_mode": "safe",
                },
            },
            headers={"X-SciStudio-IPC-Token": _ipc_token},
        )
        assert resp.status_code == 200

        # Drain frames until block_pty_opened arrives or we time out.
        import time as _time

        deadline = _time.monotonic() + 5.0
        got = None
        while _time.monotonic() < deadline:
            try:
                frame = ws.receive_json()
            except Exception:
                break
            if frame.get("type") == "block_pty_opened":
                got = frame
                break
        assert got is not None, "block_pty_opened never reached the /ws client"
        assert got["block_run_id"] == "rid-ws"
        assert got["title"] == "🤖 ws-test"
