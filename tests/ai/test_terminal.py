"""ADR-034 Phase 1.2: unit tests for the PTY wrapper.

We avoid spinning up the real claude / codex binaries here — those
tests live in the WS integration suite where we can monkeypatch the
spawn argv.  This module exercises :class:`PtyProcess` directly with
small Python subprocesses that behave like a stub TUI.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from scistudio.ai.agent.terminal import PtyProcess

# Real PtyProcess + child subprocesses: isolate from xdist so a hang/leak cannot
# crash a parallel worker (#1896).
pytestmark = pytest.mark.serial


def _python_echo_argv() -> list[str]:
    """A tiny line-echo subprocess that flushes on every newline."""
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


def _python_sleep_argv(seconds: float) -> list[str]:
    return [sys.executable, "-c", f"import time; print('hi', flush=True); time.sleep({seconds})"]


def test_pty_process_lifecycle(tmp_path: Path) -> None:
    """Spawn → read banner → kill_tree leaves no live subprocess."""
    pty = PtyProcess(_python_sleep_argv(60.0), cwd=tmp_path, cols=80, rows=24)
    try:
        assert pty.is_alive()
        assert pty.pid > 0

        # Accumulate output for up to ~3 seconds; banner should arrive
        # almost immediately on every platform.
        buf = bytearray()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and b"hi" not in buf:
            buf.extend(pty.read(0.1))
        assert b"hi" in buf, f"never saw banner; got {bytes(buf)!r}"
    finally:
        pty.kill_tree()

    # is_alive must report False after kill_tree.
    assert not pty.is_alive()

    # kill_tree is idempotent.
    pty.kill_tree()


def test_pty_process_resize_does_not_raise(tmp_path: Path) -> None:
    """resize() on a live PTY must succeed without exception."""
    pty = PtyProcess(_python_echo_argv(), cwd=tmp_path, cols=80, rows=24)
    try:
        pty.resize(cols=120, rows=40)
        # Defensive clamps: zero / huge values should not raise.
        pty.resize(cols=0, rows=0)
        pty.resize(cols=99999, rows=99999)
    finally:
        pty.kill_tree()


def test_pty_process_write_round_trip(tmp_path: Path) -> None:
    """Writing bytes to the PTY's stdin should be echoed back."""
    pty = PtyProcess(_python_echo_argv(), cwd=tmp_path)
    try:
        pty.write(b"hello\n")
        buf = bytearray()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and b"hello" not in buf:
            buf.extend(pty.read(0.1))
        # On Windows winpty often echoes both the input and output;
        # on POSIX TTY mode the kernel echoes the line.  We only assert
        # the substring is present.
        assert b"hello" in buf, f"echo never seen; got {bytes(buf)!r}"
    finally:
        pty.kill_tree()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-specific kill semantics")
def test_pty_kill_tree_posix(tmp_path: Path) -> None:
    """POSIX kill_tree should signal the process group, not just the leader."""
    pty = PtyProcess(_python_sleep_argv(60.0), cwd=tmp_path)
    pid = pty.pid
    try:
        assert pty.is_alive()
    finally:
        pty.kill_tree()
    # Give the OS a moment to reap.
    time.sleep(0.2)
    assert not pty.is_alive()
    # On POSIX, os.kill(pid, 0) raises ProcessLookupError when the PID is gone.
    import os

    with pytest.raises((ProcessLookupError, OSError)):
        os.kill(pid, 0)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific kill semantics")
def test_pty_kill_tree_windows(tmp_path: Path) -> None:
    """Windows kill_tree should invoke taskkill /T /F and the PTY should die."""
    pty = PtyProcess(_python_sleep_argv(60.0), cwd=tmp_path)
    try:
        assert pty.is_alive()
    finally:
        pty.kill_tree()
    # Brief pause for taskkill to reap.
    time.sleep(1.0)
    assert not pty.is_alive()


def test_pty_cleanup_paths_removed(tmp_path: Path) -> None:
    """Files in cleanup_paths must be deleted on kill_tree."""
    tmp_file = tmp_path / "scratch.md"
    tmp_file.write_text("payload")
    pty = PtyProcess(
        _python_sleep_argv(5.0),
        cwd=tmp_path,
        cleanup_paths=[tmp_file],
    )
    try:
        assert tmp_file.exists()
    finally:
        pty.kill_tree()
    assert not tmp_file.exists()
