"""A real backend stops gracefully when its launcher closes stdin (#2327).

Starts ``python -m scistudio.cli.main gui --port 0 --bundled`` with
``SCISTUDIO_STOP_ON_STDIN_EOF=1`` and a stdin pipe, the way the Windows desktop
shell starts it. The test then:
- starts a workflow run, whose pre-run auto-commit runs git, a child that
  inherits stdin;
- keeps an event socket and the log event stream open;
- closes stdin.

The run's lineage row must end ``cancelled`` within the desktop's force-kill
wait (``STOP_ESCALATION_MS``, 25 s), and the process must exit with no fatal
stdin-lock error. This is the Windows desktop path (re-audit findings N1 and
N2), and the test runs on every platform the suite runs on.
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import psutil
import pytest

import scistudio
from scistudio.core.lineage.store import LineageStore
from scistudio.engine.events import BLOCK_RUNNING

websockets_sync_client = pytest.importorskip("websockets.sync.client")

DESKTOP_FORCE_KILL_SEC = 25.0

SLOW_BLOCK = """
import time
from pathlib import Path
from typing import ClassVar

from scistudio.blocks.io.io_block import IOBlock
from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


class StopProbeSlowSource(IOBlock):
    type_name: ClassVar[str] = "stop_probe_slow_source"
    name: ClassVar[str] = "Stop Probe Slow Source"
    description: ClassVar[str] = "Test block that sleeps before it loads."
    direction: ClassVar[str] = "input"

    def load(self, config, output_dir=""):
        time.sleep(float(config.params.get("seconds", 120)))
        path = Path(config.params["path"])
        ref = StorageReference(backend="filesystem", path=str(path), format="csv")
        return Collection(items=[DataObject(storage_ref=ref)], item_type=DataObject)

    def save(self, obj, config):
        # IOBlock declares both directions abstract; this probe only loads.
        raise NotImplementedError("the stop probe only loads")
"""


def _backend_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir()
    src = str(Path(scistudio.__file__).resolve().parents[1])
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(filter(None, [src, os.environ.get("PYTHONPATH")])),
        "SCISTUDIO_STOP_ON_STDIN_EOF": "1",
        "HOME": str(home),
        "USERPROFILE": str(home),
        "SCISTUDIO_LOG_DIR": str(tmp_path / "logs"),
        "PYTHONUNBUFFERED": "1",
    }
    env.pop("SCISTUDIO_BUNDLED", None)
    return env


def _wait_for_ready(lines: queue.Queue[str], timeout: float = 90.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=max(0.1, deadline - time.monotonic()))
        except queue.Empty:
            break
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("event") == "scistudio.ready":
            return str(event["url"]).rstrip("/")
    raise AssertionError("the backend never printed its ready line")


def _wait_until_serving(http: httpx.Client, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if http.get("/api/projects/").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise AssertionError("the backend never answered HTTP")


def _drain_socket(socket: Any, events: list[str]) -> None:
    try:
        for message in socket:
            events.append(str(json.loads(message).get("type")))
    except Exception:
        pass


def _hold_log_stream(base: str, opened: threading.Event, ended: threading.Event) -> None:
    try:
        with httpx.stream("GET", f"{base}/api/logs/stream", timeout=None) as response:
            opened.set()
            for _ in response.iter_lines():
                pass
    except Exception:
        pass
    finally:
        opened.set()
        ended.set()


def _kill_tree(pid: int) -> None:
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    for process in [*parent.children(recursive=True), parent]:
        with contextlib.suppress(psutil.NoSuchProcess):
            process.kill()


@pytest.mark.timeout(300)
def test_real_backend_stops_gracefully_on_stdin_eof_with_streams_open(tmp_path: Path) -> None:
    """The Windows desktop path: the shell closes the backend's stdin."""
    _stop_mid_run_and_check(tmp_path, by_stdin=True)


@pytest.mark.timeout(300)
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX stop path: the desktop sends SIGTERM on macOS and Linux; Windows uses the stdin request",
)
def test_real_backend_stops_gracefully_on_sigterm_with_streams_open(tmp_path: Path) -> None:
    """The macOS and Linux desktop path: the shell sends SIGTERM (#2352)."""
    _stop_mid_run_and_check(tmp_path, by_stdin=False)


def _stop_mid_run_and_check(tmp_path: Path, *, by_stdin: bool) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    stderr_path = tmp_path / "backend-stderr.txt"
    env = _backend_env(tmp_path)
    if not by_stdin:
        # The POSIX shell spawns the backend with stdin closed and no flag.
        env.pop("SCISTUDIO_STOP_ON_STDIN_EOF", None)
    with stderr_path.open("w", encoding="utf-8") as stderr_file:
        proc = subprocess.Popen(
            [sys.executable, "-m", "scistudio.cli.main", "gui", "--port", "0", "--bundled"],
            stdin=subprocess.PIPE if by_stdin else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            env=env,
            cwd=str(tmp_path),
            text=True,
        )
    assert proc.stdout is not None
    stdout = proc.stdout
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line.strip()) for line in stdout], daemon=True).start()
    socket: Any = None
    try:
        base = _wait_for_ready(lines)
        with httpx.Client(base_url=base, timeout=30) as http:
            _wait_until_serving(http)
            created = http.post("/api/projects/", json={"name": "Stop Probe", "description": "", "path": str(projects)})
            assert created.status_code == 200, created.text
            project = Path(created.json()["path"])
            (project / "blocks").mkdir(exist_ok=True)
            (project / "blocks" / "stop_probe_slow_source.py").write_text(SLOW_BLOCK, encoding="utf-8")
            data = project / "data" / "raw" / "probe.csv"
            data.parent.mkdir(parents=True, exist_ok=True)
            data.write_text("a\n1\n", encoding="utf-8")
            assert http.post("/api/blocks/reload").status_code == 200
            workflow = {
                "id": "stop-probe",
                "version": "1.0.0",
                "description": "graceful stop probe",
                "nodes": [
                    {
                        "id": "slow",
                        "block_type": "stop_probe_slow_source",
                        "config": {"params": {"path": str(data), "seconds": 120}},
                        "layout": {"x": 0.0, "y": 0.0},
                    }
                ],
                "edges": [],
                "metadata": {},
            }
            saved = http.post("/api/workflows/", json=workflow)
            assert saved.status_code == 200, saved.text

            # The desktop keeps both streams open while a workflow is open.
            events: list[str] = []
            socket = websockets_sync_client.connect(base.replace("http", "ws", 1) + "/ws", open_timeout=30)
            threading.Thread(target=_drain_socket, args=(socket, events), daemon=True).start()
            stream_opened = threading.Event()
            stream_ended = threading.Event()
            threading.Thread(target=_hold_log_stream, args=(base, stream_opened, stream_ended), daemon=True).start()
            assert stream_opened.wait(30)

            # The pre-run auto-commit runs git with an inherited stdin.
            started = http.post("/api/workflows/stop-probe/execute")
            assert started.status_code == 200, started.text
            deadline = time.monotonic() + 90
            while BLOCK_RUNNING not in events and time.monotonic() < deadline:
                time.sleep(0.1)
            assert BLOCK_RUNNING in events, "the slow block never started"
            (run,) = http.get("/api/runs", params={"workflow_id": "stop-probe"}).json()["runs"]
            assert run["status"] == "running"
            time.sleep(1.0)

        stop_requested = time.monotonic()
        if by_stdin:
            assert proc.stdin is not None
            proc.stdin.close()
        else:
            proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=DESKTOP_FORCE_KILL_SEC)
        except subprocess.TimeoutExpired:
            pytest.fail(f"the backend was still running {DESKTOP_FORCE_KILL_SEC:.0f} s after the stop request")
        elapsed = time.monotonic() - stop_requested
        assert stream_ended.wait(5), "the log stream ended with the backend"

        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
        assert "Fatal Python error" not in stderr, stderr[-4000:]
        assert "could not acquire lock" not in stderr, stderr[-4000:]
        store = LineageStore(project / ".scistudio" / "lineage.db")
        try:
            row = store.get_run(run["run_id"])
        finally:
            store.close()
        assert row is not None
        assert row["status"] == "cancelled", (row["status"], elapsed, stderr[-4000:])
        assert elapsed < DESKTOP_FORCE_KILL_SEC
    finally:
        if socket is not None:
            with contextlib.suppress(Exception):
                socket.close()
        if proc.poll() is None:
            _kill_tree(proc.pid)
            proc.wait(timeout=30)
