"""The desktop shell's graceful stop request (#2327).

Windows cannot deliver a SIGTERM the backend could handle, so the shell asks
the bundled backend to stop by closing its stdin, and the backend raises
SIGTERM in itself. uvicorn then runs the lifespan shutdown, which ends workflow
runs with a terminal lineage status.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

import scistudio
from scistudio.api.runtime import _stop_request


def test_end_of_file_requests_a_stop() -> None:
    read_fd, write_fd = os.pipe()
    stream = os.fdopen(read_fd, "rb", buffering=0)
    requested = threading.Event()
    try:
        thread = _stop_request.watch_for_stop_request(stream, requested.set)
        assert not requested.wait(0.2), "an open pipe is not a stop request"
        os.close(write_fd)
        assert requested.wait(5)
        thread.join(5)
    finally:
        stream.close()


def test_a_read_error_is_not_a_stop_request() -> None:
    class _Broken(io.RawIOBase):
        def read(self, size: int = -1) -> bytes:
            raise OSError("the handle is invalid")

    requested = threading.Event()
    thread = _stop_request.watch_for_stop_request(_Broken(), requested.set)
    thread.join(5)
    assert not requested.is_set()


def test_the_watcher_starts_only_when_the_shell_asks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_stop_request.STOP_ON_STDIN_EOF_ENV, raising=False)
    assert _stop_request.start_stop_request_watcher() is None


def test_closing_stdin_raises_a_handled_sigterm_in_the_backend_process() -> None:
    """End to end in a real process, on whichever platform the suite runs on."""
    src = str(Path(scistudio.__file__).resolve().parents[1])
    code = textwrap.dedent(
        """
        import signal, sys, time
        from scistudio.api.runtime._stop_request import watch_for_stop_request
        received = []
        signal.signal(signal.SIGTERM, lambda signum, frame: received.append(signum))
        watch_for_stop_request(sys.stdin.buffer)
        print("ready", flush=True)
        deadline = time.monotonic() + 20
        while not received and time.monotonic() < deadline:
            time.sleep(0.05)
        print("stopped" if received else "no-signal", flush=True)
        """
    )
    pythonpath = os.pathsep.join(filter(None, [src, os.environ.get("PYTHONPATH")]))
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": pythonpath},
    )
    try:
        assert proc.stdout is not None and proc.stdin is not None
        assert proc.stdout.readline().strip() == b"ready"
        proc.stdin.close()
        assert proc.stdout.readline().strip() == b"stopped"
        assert proc.wait(timeout=30) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)
