"""Regression tests for the ADR-035 Phase 2.5 audit fixes (PR #852).

Each test corresponds to one P1 / P2 finding from
``docs/audit/2026-05-14-1253-adr-035-implementation.md``:

* P1-A : ai_block bootstrap failure must propagate (not silently degrade argv)
* P1-B : ``_ensure_ipc_token()`` must run at FastAPI startup so worker IPC
         doesn't 401 every call
* P1-C : ``pty_endpoint`` must JOIN an engine-pre-spawned PTY rather than
         re-spawn over the top of it
* P1-E : ``block_user_marked_done`` / ``block_user_cancel`` inbound WS
         frames must produce a ``signals/mark_done.json`` write under the
         right run dir
"""

from __future__ import annotations

import contextlib
import json
import os
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
    _engine_run_to_run_dir,
    _engine_tab_to_run,
    open_engine_initiated_tab,
)

# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


def _echo_argv() -> list[str]:
    return [
        sys.executable,
        "-c",
        (
            "import sys\n"
            "for line in iter(sys.stdin.readline, ''):\n"
            "    if not line:\n"
            "        break\n"
            "    sys.stdout.write(line)\n"
            "    sys.stdout.flush()\n"
        ),
    ]


@pytest.fixture(autouse=True)
def _fake_spawn(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    captured_writes: list[bytes] = []

    class _RecordingPty(PtyProcess):
        def write(self, data: bytes) -> int:  # type: ignore[override]
            captured_writes.append(data)
            return super().write(data)

    def fake(
        *,
        provider: str,
        project_dir: Path,
        dangerous: bool,
        extra_env: dict[str, str] | None = None,
    ) -> PtyProcess:
        return _RecordingPty(_echo_argv(), cwd=project_dir, cols=80, rows=24, extra_env=extra_env)

    monkeypatch.setattr(ai_pty._state, "_spawn", fake)
    _active_ptys.clear()
    _engine_tab_to_run.clear()
    _engine_run_to_run_dir.clear()
    yield
    for pty in list(_active_ptys.values()):
        with contextlib.suppress(Exception):
            pty.kill_tree()
    _active_ptys.clear()
    _engine_tab_to_run.clear()
    _engine_run_to_run_dir.clear()


# ---------------------------------------------------------------------------
# P1-B: IPC token must be initialised at app startup.
# ---------------------------------------------------------------------------


def test_p1b_ipc_token_initialised_at_app_startup(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Audit P1-B: ``SCISTUDIO_ENGINE_IPC_TOKEN`` must be set after FastAPI startup.

    The TestClient's lifespan invokes :func:`create_app`'s lifespan which
    calls :func:`_ensure_ipc_token`. Without the fix the env var is unset
    and every internal IPC call returns 401.
    """
    # The ``client`` fixture has already entered the TestClient context,
    # so the lifespan startup has already run.
    token = os.environ.get("SCISTUDIO_ENGINE_IPC_TOKEN", "")
    assert token, "engine startup must populate SCISTUDIO_ENGINE_IPC_TOKEN"

    # Sanity: an internal IPC call sent with the live token authenticates.
    resp = client.post(
        "/api/ai/pty/internal/notify",
        json={
            "type": "notify_block_pty_event",
            "block_run_id": "rid-not-real",
            "event": "completed",
            "detail": {},
        },
        headers={"X-SciStudio-IPC-Token": token},
    )
    # 204 = handler accepted; 400 also acceptable if validation tightens.
    assert resp.status_code in (204, 400), resp.text


# ---------------------------------------------------------------------------
# P1-C: pty_endpoint must JOIN an engine-pre-spawned PTY rather than respawn.
# ---------------------------------------------------------------------------


def test_p1c_pty_endpoint_joins_engine_initiated_tab(
    client: TestClient, opened_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit P1-C: connecting to ``/api/ai/pty/{tab_id}`` for an
    engine-pre-spawned tab must REUSE the existing PTY (must not call
    ``_spawn`` a second time)."""

    spawn_calls: list[dict[str, Any]] = []
    # Capture the seam where the autouse ``_fake_spawn`` fixture installed its
    # fake (``ai_pty._state._spawn``), NOT the package re-export
    # ``ai_pty._spawn``: the fixture rebinds the leaf attribute, so reading the
    # package alias would capture the *real* spawner and try to exec ``claude``.
    real_spawn = ai_pty._state._spawn

    def counting_spawn(**kwargs: Any) -> PtyProcess:
        spawn_calls.append(kwargs)
        return real_spawn(**kwargs)

    monkeypatch.setattr(ai_pty._state, "_spawn", counting_spawn)

    # 1. Pre-spawn engine-initiated PTY.
    tab_id = open_engine_initiated_tab(
        title="🤖 demo",
        spawn_argv=["claude"],
        cwd=str(opened_project),
        initial_stdin="HELLO-AGENT\n",
        block_run_id="rid-join-1",
        permission_mode="safe",
        run_dir_path=str(opened_project / ".scistudio" / "ai-block-runs" / "rid-join-1"),
    )
    assert len(spawn_calls) == 1, "engine-initiated open should call _spawn exactly once"
    pre_spawn_pty = _active_ptys[tab_id]

    # 2. Connect to the user-visible WS endpoint for the same tab_id.
    url = f"/api/ai/pty/{tab_id}?provider=claude-code&project_dir={opened_project}&dangerous=false"
    with client.websocket_connect(url) as ws:
        # Drain a frame so the join code path runs to completion (the test
        # client returns from connect once accept is observed; receiving a
        # frame waits until the pump tasks have iterated at least once).
        with contextlib.suppress(Exception):
            ws.receive_json(timeout=0.5)
        # Sanity: still the same PTY instance — not respawned.
        assert _active_ptys.get(tab_id) is pre_spawn_pty
        # And the initial stdin replay sentinel was set.
        assert getattr(pre_spawn_pty, "_engine_initial_stdin_sent", False) is True

    # The teardown drops the entry; only the original spawn happened.
    assert len(spawn_calls) == 1, (
        f"_spawn must NOT be called a second time for engine-initiated join; got {spawn_calls}"
    )


# ---------------------------------------------------------------------------
# #1789: the engine-supplied prompt must be typed into the agent TUI only after
# it is up (first output seen) and submitted with a carriage return, not an LF.
# ---------------------------------------------------------------------------


def test_1789_initial_stdin_replayed_with_carriage_return_after_first_output(
    client: TestClient, opened_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The engine prompt is typed after the child's first output and submitted
    with a single ``\\r`` (Enter), with the composed trailing newline stripped.

    Previously the prompt was written the instant the WS connected and ended in
    an LF, so a raw-mode TUI never saw an Enter — the text sat unsent (#1789).
    """
    import time

    writes: list[bytes] = []

    # Child emits a banner immediately (so ``first_output`` fires), then idles so
    # the PTY stays alive while we observe the deferred replay.
    argv = [
        sys.executable,
        "-c",
        "import sys, time\nsys.stdout.write('BANNER\\n'); sys.stdout.flush()\ntime.sleep(3)\n",
    ]

    class _RecordingPty(PtyProcess):
        def write(self, data: bytes) -> int:  # type: ignore[override]
            writes.append(data)
            return super().write(data)

    def fake(
        *,
        provider: str,
        project_dir: Path,
        dangerous: bool,
        extra_env: dict[str, str] | None = None,
    ) -> PtyProcess:
        return _RecordingPty(argv, cwd=project_dir, cols=80, rows=24, extra_env=extra_env)

    monkeypatch.setattr(ai_pty._state, "_spawn", fake)

    tab_id = open_engine_initiated_tab(
        title="🤖 demo",
        spawn_argv=["claude"],
        cwd=str(opened_project),
        initial_stdin="Do the thing\n",
        block_run_id="rid-1789",
        permission_mode="safe",
        run_dir_path=str(opened_project / ".scistudio" / "ai-block-runs" / "rid-1789"),
    )

    url = f"/api/ai/pty/{tab_id}?provider=claude-code&project_dir={opened_project}&dangerous=false"
    with client.websocket_connect(url) as ws:
        # Drain frames until the deferred replay (first_output + settle) writes
        # the submit byte, or we give up after a few seconds.
        deadline = time.time() + 6.0
        while time.time() < deadline and b"\r" not in writes:
            with contextlib.suppress(Exception):
                ws.receive_json(timeout=0.2)

    assert writes, "expected the engine prompt to be replayed to the PTY"
    # Submit byte is a lone carriage return, written last.
    assert writes[-1] == b"\r", f"expected a trailing carriage-return submit, got {writes!r}"
    # The body precedes it, carries the prompt, and has no trailing newline.
    body = writes[-2] if len(writes) >= 2 else b""
    assert b"Do the thing" in body
    assert not body.endswith(b"\n"), f"composed trailing LF must be stripped, got {body!r}"


def test_1789_engine_pty_resized_to_client_viewport_on_join(
    client: TestClient, opened_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#1789: joining an engine-pre-spawned PTY must resize it to the connecting
    client's viewport.

    The engine spawns the PTY at the default 120x30 before any WS exists; without
    this correction the agent TUI renders at 120x30 while xterm shows the fitted
    size, producing a garbled display that does not fill the pane.
    """
    resizes: list[tuple[int, int]] = []

    class _RecordingPty(PtyProcess):
        def resize(self, cols: int, rows: int) -> None:  # type: ignore[override]
            resizes.append((cols, rows))
            return super().resize(cols, rows)

    def fake(
        *,
        provider: str,
        project_dir: Path,
        dangerous: bool,
        extra_env: dict[str, str] | None = None,
    ) -> PtyProcess:
        return _RecordingPty(_echo_argv(), cwd=project_dir, cols=120, rows=30, extra_env=extra_env)

    monkeypatch.setattr(ai_pty._state, "_spawn", fake)

    tab_id = open_engine_initiated_tab(
        title="🤖 demo",
        spawn_argv=["claude"],
        cwd=str(opened_project),
        initial_stdin="",
        block_run_id="rid-1789-size",
        permission_mode="safe",
        run_dir_path=str(opened_project / ".scistudio" / "ai-block-runs" / "rid-1789-size"),
    )

    url = (
        f"/api/ai/pty/{tab_id}?provider=claude-code&project_dir={opened_project}"
        "&dangerous=false&cols=100&rows=40"
    )
    with client.websocket_connect(url) as ws, contextlib.suppress(Exception):
        ws.receive_json(timeout=0.5)

    assert (100, 40) in resizes, f"expected join to resize the PTY to the client viewport, got {resizes!r}"


# ---------------------------------------------------------------------------
# P1-E: block_user_marked_done / block_user_cancel WS frames must write
# ``signals/mark_done.json`` under the run dir.
# ---------------------------------------------------------------------------


def _wait_for_path(path: Path, timeout: float = 2.0) -> bool:
    """Poll until *path* exists or *timeout* seconds elapse."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)
    return False


def test_p1e_block_user_marked_done_writes_signal_file(client: TestClient, opened_project: Path) -> None:
    """Audit P1-E: ``block_user_marked_done`` WS frame must produce a
    ``signals/mark_done.json`` under the AI Block run dir within ~1s."""

    run_id = "rid-mark-done-1"
    run_dir = opened_project / ".scistudio" / "ai-block-runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "signals").mkdir()

    # Register an engine-initiated tab so the WS handler can resolve
    # block_run_id → run_dir.
    tab_id = open_engine_initiated_tab(
        title="🤖 demo",
        spawn_argv=["claude"],
        cwd=str(opened_project),
        initial_stdin="",
        block_run_id=run_id,
        permission_mode="safe",
        run_dir_path=str(run_dir),
    )

    with client.websocket_connect("/ws") as ws:
        ws.send_json(
            {
                "type": "block_user_marked_done",
                "block_run_id": run_id,
                "tab_id": tab_id,
            }
        )

    signal = run_dir / "signals" / "mark_done.json"
    assert _wait_for_path(signal, timeout=2.0), f"mark_done.json did not appear under {run_dir / 'signals'}"
    payload = json.loads(signal.read_text(encoding="utf-8"))
    assert payload["kind"] == "user_mark_done"
    assert payload["block_run_id"] == run_id


def test_p1e_block_user_cancel_writes_signal_file(client: TestClient, opened_project: Path) -> None:
    """Audit P1-E: ``block_user_cancel`` WS frame must also write the signal."""
    run_id = "rid-cancel-1"
    run_dir = opened_project / ".scistudio" / "ai-block-runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "signals").mkdir()

    tab_id = open_engine_initiated_tab(
        title="🤖 demo",
        spawn_argv=["claude"],
        cwd=str(opened_project),
        initial_stdin="",
        block_run_id=run_id,
        permission_mode="safe",
        run_dir_path=str(run_dir),
    )

    with client.websocket_connect("/ws") as ws:
        ws.send_json(
            {
                "type": "block_user_cancel",
                "block_run_id": run_id,
                "tab_id": tab_id,
            }
        )

    signal = run_dir / "signals" / "mark_done.json"
    assert _wait_for_path(signal, timeout=2.0)
    payload = json.loads(signal.read_text(encoding="utf-8"))
    assert payload["kind"] == "user_cancel"
    assert payload["block_run_id"] == run_id


def test_p1e_unknown_block_run_id_is_swallowed(client: TestClient) -> None:
    """Audit P1-E robustness: an unknown block_run_id must NOT crash the WS pump."""
    with client.websocket_connect("/ws") as ws:
        # Should not raise; the connection should still accept further frames.
        ws.send_json(
            {
                "type": "block_user_marked_done",
                "block_run_id": "totally-unknown-rid",
                "tab_id": "fake-tab",
            }
        )
        # Send a known frame type after; if the loop crashed this would error.
        ws.send_json({"type": "cancel_workflow", "workflow_id": "wf-x"})


# ---------------------------------------------------------------------------
# P1-A: AIBlock bootstrap failure must surface as a real error.
# ---------------------------------------------------------------------------


def test_p1a_bootstrap_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Audit P1-A: failures in ``_write_system_prompt_tempfile`` /
    ``_ensure_mcp_config`` must abort spawn with a RuntimeError carrying
    a "bootstrap failed" message — not silently degrade the argv."""
    import scistudio.ai.agent.terminal as terminal_mod
    from scistudio.blocks.ai.ai_block import AIBlock
    from scistudio.blocks.base.config import BlockConfig

    # Force the helpers to raise.
    def boom(*_args: Any, **_kwargs: Any) -> str:
        raise OSError("disk full")

    monkeypatch.setattr(terminal_mod, "_write_system_prompt_tempfile", boom)

    # Pretend `claude` is on PATH so we get past the discoverability check.
    monkeypatch.setattr(
        "scistudio.blocks.ai.ai_block._discover_provider",
        lambda _provider: "/usr/bin/claude",
    )

    block = AIBlock()
    cfg = BlockConfig(
        params={
            "user_prompt": "do things",
            "provider": "claude-code",
            "permission_mode": "safe",
            "project_dir": os.getcwd(),
        }
    )
    with pytest.raises(RuntimeError, match="bootstrap failed"):
        block._build_spawn_argv(cfg, manifest_path="/tmp/manifest.json")
