"""ADR-034 Phase 1.2: WebSocket integration tests for the PTY route.

We avoid spinning up the real claude / codex CLI here.  The route
exposes a private ``_spawn`` test hook which we monkeypatch to spawn
a tiny Python echo subprocess in a PTY instead.  This gives end-to-end
coverage of frame parsing, lifecycle, resize, error paths, and the
resource cap without depending on external binaries.
"""

from __future__ import annotations

import contextlib
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scieasy.ai.agent.terminal import PtyProcess
from scieasy.api.routes import ai_pty
from scieasy.api.routes.ai_pty import _active_ptys


def _echo_argv() -> list[str]:
    return [
        sys.executable,
        "-c",
        (
            "import sys\n"
            "sys.stdout.write('READY\\n')\n"
            "sys.stdout.flush()\n"
            "for line in iter(sys.stdin.readline, ''):\n"
            "    if not line:\n"
            "        break\n"
            "    sys.stdout.write(line)\n"
            "    sys.stdout.flush()\n"
        ),
    ]


@pytest.fixture(autouse=True)
def _fake_spawn(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Replace the PTY spawn with a Python echo subprocess.

    Also resets the module-level active-PTY map between tests so the
    16-cap test is order-independent.
    """

    def fake(*, provider: str, project_dir: Path, dangerous: bool) -> PtyProcess:
        return PtyProcess(_echo_argv(), cwd=project_dir, cols=80, rows=24)

    monkeypatch.setattr(ai_pty, "_spawn", fake)
    _active_ptys.clear()
    yield
    # Best-effort teardown for leftover PTYs (max-count test holds them).
    for pty in list(_active_ptys.values()):
        with contextlib.suppress(Exception):
            pty.kill_tree()
    _active_ptys.clear()


def _ws_url(tab_id: str, project_dir: Path, *, provider: str = "claude-code", dangerous: bool = False) -> str:
    """Construct the locked-contract WS path with query params."""
    from urllib.parse import quote

    return (
        f"/api/ai/pty/{tab_id}"
        f"?project_dir={quote(str(project_dir))}"
        f"&provider={provider}"
        f"&dangerous={'true' if dangerous else 'false'}"
    )


def test_pty_ws_lifecycle(client: TestClient, opened_project: Path) -> None:
    """Connect → receive READY banner → write → echo → close → PTY killed."""
    with client.websocket_connect(_ws_url("tab-A", opened_project)) as ws:
        # Drain frames until READY arrives or we time out.
        deadline = time.monotonic() + 5.0
        got_ready = False
        while time.monotonic() < deadline and not got_ready:
            frame = ws.receive_json()
            assert frame.get("type") in {"stdout", "exit", "error"}
            if frame["type"] == "stdout" and "READY" in frame.get("data", ""):
                got_ready = True
        assert got_ready, "never received READY banner"

        ws.send_json({"type": "stdin", "data": "hello\n"})
        # Drain until we see 'hello' echoed back.
        deadline = time.monotonic() + 5.0
        got_echo = False
        while time.monotonic() < deadline and not got_echo:
            frame = ws.receive_json()
            if frame["type"] == "stdout" and "hello" in frame.get("data", ""):
                got_echo = True
        assert got_echo, "never received echoed 'hello'"

    # On close, route teardown should kill PTY and remove from registry.
    # Poll generously — Windows ``taskkill /T /F`` has a 5 s subprocess
    # timeout of its own and the route's pump cancellation can add another
    # ~0.1 s of executor latency.
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline and _active_ptys:
        time.sleep(0.1)
    assert not _active_ptys, f"PTY not cleaned up: {list(_active_ptys)}"


def test_pty_ws_resize_no_error(client: TestClient, opened_project: Path) -> None:
    """Sending a resize frame must not produce an error frame."""
    with client.websocket_connect(_ws_url("tab-resize", opened_project)) as ws:
        # Drain the initial READY banner.
        ws.receive_json()
        ws.send_json({"type": "resize", "cols": 100, "rows": 40})
        # Send some input to verify the PTY is still alive after resize.
        ws.send_json({"type": "stdin", "data": "x\n"})
        deadline = time.monotonic() + 5.0
        saw_x = False
        while time.monotonic() < deadline and not saw_x:
            frame = ws.receive_json()
            assert frame["type"] != "error", f"unexpected error frame: {frame}"
            if frame["type"] == "stdout" and "x" in frame.get("data", ""):
                saw_x = True
        assert saw_x


def test_pty_ws_invalid_provider(client: TestClient, opened_project: Path) -> None:
    """An unknown provider must yield an error frame and a close."""
    with client.websocket_connect(_ws_url("tab-bad", opened_project, provider="bogus")) as ws:
        frame = ws.receive_json()
        assert frame["type"] == "error"
        assert "Invalid provider" in frame["message"]


def test_pty_ws_max_count(client: TestClient, opened_project: Path) -> None:
    """The 17th simultaneous connection must be rejected with an error."""
    from scieasy.api.routes.ai_pty import MAX_ACTIVE_PTYS

    assert MAX_ACTIVE_PTYS == 16

    # Open MAX connections and hold them.  Each TestClient WS context
    # is a contextmanager; nest them so they stay alive concurrently.
    import contextlib

    with contextlib.ExitStack() as stack:
        websockets = []
        for i in range(MAX_ACTIVE_PTYS):
            ws = stack.enter_context(client.websocket_connect(_ws_url(f"tab-{i}", opened_project)))
            websockets.append(ws)
            # Wait until the registry reflects the new PTY before opening
            # the next — protects against the route's async accept path
            # racing the cap check.
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and len(_active_ptys) < i + 1:
                time.sleep(0.05)

        assert len(_active_ptys) == MAX_ACTIVE_PTYS

        # The 17th connection should be refused before the PTY spawns.
        with client.websocket_connect(_ws_url("tab-overflow", opened_project)) as ws_extra:
            frame = ws_extra.receive_json()
            assert frame["type"] == "error"
            assert "max" in frame["message"].lower()


def test_pty_ws_missing_project_dir(client: TestClient) -> None:
    """Missing ``project_dir`` query parameter must surface an error frame."""
    with client.websocket_connect("/api/ai/pty/tab-x?provider=claude-code") as ws:
        frame = ws.receive_json()
        assert frame["type"] == "error"
        assert "project_dir" in frame["message"]
