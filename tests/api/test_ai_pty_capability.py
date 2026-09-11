"""ADR-055 Spec 4 FR-006 — ``ai_chat_disabled`` refuses agent-kind PTY sessions (issue #2322).

The Terminal and the AI chat share the ``/api/ai`` PTY routes and differ only
by the registry's provider kind, so the gate keys on the kind, not the route:

* with ``ai_chat_disabled`` set, every agent-kind provider is refused with a
  clear error and **no process is spawned**: the user-launched WebSocket, the
  AI Block's pre-spawned tab, and the Bring In My Work tab;
* the Terminal (``user-terminal``) still starts, and a tutorial replay, which
  spawns nothing and is joined under ``user-terminal``, is still joined;
* without the capability, agent sessions start exactly as before;
* the policy follows the application lifespan and is cleared at teardown.

The spawn is replaced by a recorder returning an in-memory PTY, so "no process"
is asserted as "the spawn was never called".
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from scistudio.ai.agent.providers_registry import REGISTRY, ProviderKind
from scistudio.api import app as app_module
from scistudio.api.app import create_app
from scistudio.api.routes import ai_pty
from scistudio.api.routes.ai_pty import engine as ai_pty_engine
from scistudio.api.routes.ai_pty._state import _spawn as _real_spawn
from scistudio.api.routes.ai_pty.replay import open_replay_tab
from scistudio.api.seam import Capabilities
from scistudio.tutorials.actions import AI_CHAT_TERMINAL_SURFACE
from tests.api.seam_contract import PREFIXED_MOUNT

AGENT_KEYS = REGISTRY.agent_keys()
TERMINAL_KEY = "user-terminal"
MOUNTS = pytest.mark.parametrize("mount_prefix", ["", PREFIXED_MOUNT], ids=["root-mount", "prefixed-mount"])
REFUSAL = "turned off on this server"


class _FakePty:
    """An in-memory PTY: says READY once, echoes nothing, idles until killed."""

    def __init__(self) -> None:
        self._pending = b"READY\n"
        self._lock = threading.Lock()
        self._alive = True

    def read(self, timeout: float = 0.1) -> bytes:
        with self._lock:
            chunk, self._pending = self._pending, b""
        if not chunk:
            time.sleep(min(timeout, 0.02))
        return chunk

    def write(self, data: bytes) -> None:
        return None

    def resize(self, *, cols: int, rows: int) -> None:
        return None

    def is_alive(self) -> bool:
        return self._alive

    def kill_tree(self) -> None:
        self._alive = False


@pytest.fixture()
def spawned(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Record every spawn instead of starting a process; reset shared PTY state."""
    calls: list[str] = []

    def record(
        *,
        provider: str,
        project_dir: Path,
        dangerous: bool,
        cols: int = 120,
        rows: int = 30,
        extra_env: dict[str, str] | None = None,
        prompt: str = "",
    ) -> Any:
        calls.append(provider)
        return _FakePty()

    monkeypatch.setattr(ai_pty._state, "_spawn", record)
    ai_pty._active_ptys.clear()
    yield calls
    for pty in list(ai_pty._active_ptys.values()):
        with contextlib.suppress(Exception):
            pty.kill_tree()
    ai_pty._active_ptys.clear()
    ai_pty._set_agent_sessions_disabled(False)


@pytest.fixture()
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated home and a project directory the PTY may start in."""
    from scistudio.api import runtime as runtime_module

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("SCISTUDIO_ROOT_PATH", raising=False)
    monkeypatch.setattr(app_module, "_resolve_spa_static_dir", lambda: None)
    project = tmp_path / "project"
    project.mkdir()
    return project


def _app(*, disabled: bool) -> Any:
    return create_app(capabilities=Capabilities(ai_chat_disabled=True)) if disabled else create_app()


def _pty_url(mount_prefix: str, tab_id: str, project: Path, provider: str) -> str:
    return f"{mount_prefix}/api/ai/pty/{tab_id}?project_dir={quote(str(project))}&provider={provider}&dangerous=false"


def _first_stdout(websocket: Any) -> str:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        frame = websocket.receive_json()
        assert frame["type"] != "error", frame
        if frame["type"] == "stdout" and frame["data"]:
            return str(frame["data"])
    raise AssertionError("no stdout frame arrived")


# ---------------------------------------------------------------------------
# The user-launched WebSocket.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", AGENT_KEYS)
def test_every_agent_provider_is_refused_without_a_process(
    project_dir: Path, spawned: list[str], provider: str
) -> None:
    with (
        TestClient(_app(disabled=True)) as client,
        client.websocket_connect(_pty_url("", "tab-agent", project_dir, provider)) as websocket,
    ):
        frame = websocket.receive_json()
    assert frame["type"] == "error"
    assert REFUSAL in frame["message"]
    assert REGISTRY.get(provider).label in frame["message"]
    assert "Terminal" in frame["message"]
    assert spawned == []
    assert not ai_pty._active_ptys


@MOUNTS
def test_agent_refusal_and_terminal_under_both_mounts(
    project_dir: Path, spawned: list[str], monkeypatch: pytest.MonkeyPatch, mount_prefix: str
) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    with TestClient(_app(disabled=True), root_path=mount_prefix) as client:
        with client.websocket_connect(_pty_url(mount_prefix, "tab-agent", project_dir, "claude-code")) as websocket:
            assert websocket.receive_json()["type"] == "error"
        assert spawned == []
        # The Terminal is never gated.
        with client.websocket_connect(_pty_url(mount_prefix, "tab-shell", project_dir, TERMINAL_KEY)) as websocket:
            assert "READY" in _first_stdout(websocket)
    assert spawned == [TERMINAL_KEY]


def test_tutorial_replay_is_joined_under_the_terminal_provider(project_dir: Path, spawned: list[str]) -> None:
    """A replay adopted under ``user-terminal`` is a terminal-kind session, never refused."""
    with TestClient(_app(disabled=True)) as client:
        handle = open_replay_tab(AI_CHAT_TERMINAL_SURFACE)
        try:
            handle.session.feed(b"scripted transcript\n")
            url = _pty_url("", handle.tab_id, project_dir, TERMINAL_KEY)
            with client.websocket_connect(url) as websocket:
                assert "scripted transcript" in _first_stdout(websocket)
        finally:
            handle.close()
    assert spawned == [], "a replay is joined, never spawned"


@MOUNTS
def test_agent_sessions_start_as_before_without_the_capability(
    project_dir: Path, spawned: list[str], monkeypatch: pytest.MonkeyPatch, mount_prefix: str
) -> None:
    """Default unchanged: no capability, no gate."""
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    with (
        TestClient(_app(disabled=False), root_path=mount_prefix) as client,
        client.websocket_connect(_pty_url(mount_prefix, "tab-agent", project_dir, "claude-code")) as websocket,
    ):
        assert "READY" in _first_stdout(websocket)
    assert spawned == ["claude-code"]


# ---------------------------------------------------------------------------
# The pre-spawned paths: AI Block and Bring In My Work.
# ---------------------------------------------------------------------------


def test_ai_block_tab_is_refused_before_spawning(project_dir: Path, spawned: list[str]) -> None:
    with TestClient(_app(disabled=True)), pytest.raises(ai_pty.AgentSessionsDisabledError, match=REFUSAL):
        ai_pty_engine.open_engine_initiated_tab(
            title="AI Block",
            provider="claude-code",
            cwd=str(project_dir),
            initial_stdin="do the task",
            block_run_id="block-run-1",
            permission_mode="safe",
        )
    assert spawned == []
    assert not ai_pty._active_ptys
    assert "block-run-1" not in ai_pty._engine_tab_to_run.values()


def test_ai_block_request_route_reports_the_refusal(project_dir: Path, spawned: list[str]) -> None:
    with TestClient(_app(disabled=True)) as client:
        response = client.post(
            "/api/ai/pty/internal/request-tab",
            headers={"X-SciStudio-IPC-Token": os.environ["SCISTUDIO_ENGINE_IPC_TOKEN"]},
            json={
                "type": "request_pty_tab",
                "spec": {
                    "title": "AI Block",
                    "provider": "codex",
                    "cwd": str(project_dir),
                    "block_run_id": "block-run-2",
                    "permission_mode": "safe",
                },
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["tab_id"] is None
    assert REFUSAL in body["error"]
    assert spawned == []


def test_bring_in_my_work_tab_is_refused_before_spawning(project_dir: Path, spawned: list[str]) -> None:
    with TestClient(_app(disabled=True)), pytest.raises(ai_pty.AgentSessionsDisabledError, match=REFUSAL):
        ai_pty_engine.open_work_import_tab(
            provider="codex",
            cwd=str(project_dir),
            opening_message="Read the brief.",
            permission_mode="safe",
        )
    assert spawned == []
    assert not ai_pty._active_ptys


def test_pre_spawned_tabs_start_as_before_without_the_capability(project_dir: Path, spawned: list[str]) -> None:
    with TestClient(_app(disabled=False)):
        tab_id = ai_pty_engine.open_work_import_tab(
            provider="codex",
            cwd=str(project_dir),
            opening_message="Read the brief.",
            permission_mode="safe",
        )
    assert spawned == ["codex"]
    assert tab_id in ai_pty._active_ptys


# ---------------------------------------------------------------------------
# The policy itself.
# ---------------------------------------------------------------------------


def test_provider_dispatch_refuses_as_a_backstop(
    project_dir: Path, spawned: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real ``_spawn`` refuses too, so a caller that skips the check spawns nothing."""
    started: list[str] = []
    monkeypatch.setitem(ai_pty._state._PROVIDER_SPAWNERS, "claude-code", lambda **_: started.append("claude-code"))
    monkeypatch.setitem(ai_pty._state._PROVIDER_SPAWNERS, TERMINAL_KEY, lambda **_: started.append(TERMINAL_KEY))
    ai_pty._set_agent_sessions_disabled(True)
    with pytest.raises(ai_pty.AgentSessionsDisabledError):
        _real_spawn(provider="claude-code", project_dir=project_dir, dangerous=False)
    _real_spawn(provider=TERMINAL_KEY, project_dir=project_dir, dangerous=False)
    assert started == [TERMINAL_KEY]


def test_the_gate_keys_on_the_registry_provider_kind(spawned: list[str]) -> None:
    ai_pty._set_agent_sessions_disabled(True)
    for descriptor in REGISTRY:
        refused = ai_pty.agent_session_refusal(descriptor.key) is not None
        assert refused is (descriptor.kind is ProviderKind.AGENT), descriptor.key
    assert ai_pty.agent_session_refusal("no-such-provider") is None


def test_the_policy_follows_the_application_lifespan(project_dir: Path, spawned: list[str]) -> None:
    assert ai_pty.agent_session_refusal("claude-code") is None
    with TestClient(_app(disabled=True)):
        assert ai_pty.agent_session_refusal("claude-code") is not None
        assert ai_pty.agent_session_refusal(TERMINAL_KEY) is None
    assert ai_pty.agent_session_refusal("claude-code") is None, "cleared at teardown"
    with TestClient(_app(disabled=False)):
        assert ai_pty.agent_session_refusal("claude-code") is None


# ---------------------------------------------------------------------------
# GET /api/ai/status runs no agent binary under ai_chat_disabled (no-context
# audit P3-5).
# ---------------------------------------------------------------------------


@pytest.fixture()
def probes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every agent binary probe the status route would run."""
    from scistudio.api.routes import ai as ai_routes

    ran: list[str] = []

    def binary_status(descriptor: Any) -> tuple[str | None, bool, str | None]:
        ran.append(descriptor.key)
        return None, False, None

    monkeypatch.setattr(ai_routes, "_binary_status", binary_status)
    return ran


def test_status_runs_no_agent_probe_while_agent_sessions_are_disabled(
    project_dir: Path, spawned: list[str], probes: list[str]
) -> None:
    with TestClient(_app(disabled=True)) as client:
        rows = client.get("/api/ai/status").json()["providers"]
    assert probes == []
    assert [row["name"] for row in rows] == list(AGENT_KEYS)
    assert all(row["disabled"] is True and row["available"] is False for row in rows)


def test_status_probes_agents_as_before_without_the_capability(
    project_dir: Path, spawned: list[str], probes: list[str]
) -> None:
    with TestClient(_app(disabled=False)) as client:
        rows = client.get("/api/ai/status").json()["providers"]
    assert sorted(probes) == sorted(AGENT_KEYS)
    assert all("disabled" not in row for row in rows)
