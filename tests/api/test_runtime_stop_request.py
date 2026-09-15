"""The backend's graceful stop request and its stop notice (#2327).

On Windows the desktop shell asks the bundled backend to stop by closing its
stdin. The backend moves that pipe to a private descriptor that children cannot
inherit and gives them the null device, so git and other children do not hang
on it; at end-of-file it raises SIGTERM in itself. Each stop signal first
calls a notice that ends the backend's long-lived streams.
"""

from __future__ import annotations

import asyncio
import os
import queue
import signal
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

import scistudio
from scistudio.api.runtime import _stop_request


def _child_env() -> dict[str, str]:
    src = str(Path(scistudio.__file__).resolve().parents[1])
    pythonpath = os.pathsep.join(filter(None, [src, os.environ.get("PYTHONPATH")]))
    env = {**os.environ, "PYTHONPATH": pythonpath}
    env.pop(_stop_request.STOP_ON_STDIN_EOF_ENV, None)
    return env


def test_end_of_file_requests_a_stop() -> None:
    read_fd, write_fd = os.pipe()
    requested = threading.Event()
    thread = _stop_request.watch_for_stop_request(read_fd, requested.set)
    assert not requested.wait(0.2), "an open pipe is not a stop request"
    os.close(write_fd)
    assert requested.wait(5)
    thread.join(5)


def test_a_read_error_is_not_a_stop_request() -> None:
    write_only = os.open(os.devnull, os.O_WRONLY)
    requested = threading.Event()
    thread = _stop_request.watch_for_stop_request(write_only, requested.set)
    thread.join(5)
    assert not thread.is_alive()
    assert not requested.is_set()


def test_the_watcher_starts_only_when_the_shell_asks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_stop_request.STOP_ON_STDIN_EOF_ENV, raising=False)
    assert _stop_request.start_stop_request_watcher() is None


def test_a_stop_notice_runs_before_the_previous_handler_and_can_be_disarmed() -> None:
    order: list[str] = []
    original = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, lambda signum, frame: order.append("previous"))
    try:
        disarm = _stop_request.arm_stop_notice(lambda: order.append("notice"))
        signal.raise_signal(signal.SIGTERM)
        assert order == ["notice", "previous"]
        disarm()
        signal.raise_signal(signal.SIGTERM)
        assert order == ["notice", "previous", "previous"]
    finally:
        signal.signal(signal.SIGTERM, original)


def test_a_stop_notice_is_scheduled_on_the_given_loop() -> None:
    async def _run() -> None:
        loop = asyncio.get_running_loop()
        seen: list[str] = []
        original = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, lambda signum, frame: None)
        try:
            disarm = _stop_request.arm_stop_notice(lambda: seen.append("notice"), loop=loop)
            signal.raise_signal(signal.SIGTERM)
            await asyncio.sleep(0.05)
            assert seen == ["notice"]
            disarm()
        finally:
            signal.signal(signal.SIGTERM, original)

    asyncio.run(_run())


def test_children_do_not_inherit_the_stop_request_pipe_and_the_backend_exits_cleanly() -> None:
    """Re-audit N1: a child that inherited the pipe the watcher reads hung on Windows.

    The process below starts the watcher the way the backend does, then starts
    children with an inherited stdin, a Python child that reads it and git,
    while the watcher waits on the pipe. Both must finish promptly, the stop
    must arrive when the pipe closes, and the process must exit with no fatal
    stdin-lock error.
    """
    code = textwrap.dedent(
        """
        import os, shutil, signal, subprocess, sys, time
        os.environ["SCISTUDIO_STOP_ON_STDIN_EOF"] = "1"
        from scistudio.api.runtime._stop_request import start_stop_request_watcher
        received = []
        signal.signal(signal.SIGTERM, lambda signum, frame: received.append(signum))
        assert start_stop_request_watcher() is not None
        time.sleep(0.3)
        started = time.monotonic()
        child = subprocess.run(
            [sys.executable, "-c", "import sys; print(len(sys.stdin.read()))"],
            capture_output=True, text=True, timeout=20,
        )
        print("python-child", child.stdout.strip(), round(time.monotonic() - started, 2), flush=True)
        git = shutil.which("git")
        if git:
            started = time.monotonic()
            subprocess.run([git, "--version"], capture_output=True, timeout=20, check=True)
            print("git-child", round(time.monotonic() - started, 2), flush=True)
        print("ready", flush=True)
        deadline = time.monotonic() + 20
        while not received and time.monotonic() < deadline:
            time.sleep(0.05)
        print("stopped" if received else "no-signal", flush=True)
        """
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_child_env(),
        text=True,
    )
    lines: queue.Queue[str] = queue.Queue()
    assert proc.stdout is not None and proc.stdin is not None and proc.stderr is not None
    reader = threading.Thread(target=lambda: [lines.put(line.strip()) for line in proc.stdout], daemon=True)
    reader.start()
    try:
        seen: list[str] = []
        while "ready" not in seen:
            seen.append(lines.get(timeout=40))
        python_child = next(line for line in seen if line.startswith("python-child"))
        _, output, seconds = python_child.split()
        assert output == "0", "the child must see an empty (null) stdin"
        assert float(seconds) < 10
        for line in seen:
            if line.startswith("git-child"):
                assert float(line.split()[1]) < 10
        proc.stdin.close()
        assert lines.get(timeout=30) == "stopped"
        assert proc.wait(timeout=30) == 0
        stderr = proc.stderr.read()
        assert "Fatal Python error" not in stderr
        assert "could not acquire lock" not in stderr
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)
