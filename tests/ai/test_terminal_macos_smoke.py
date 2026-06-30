"""macOS-only smoke test for the POSIX PTY spawn path used by ADR-034.

This test verifies that the underlying ``pty.openpty`` + ``subprocess.Popen``
pattern from :func:`scistudio.ai.agent.terminal.PtyProcess._spawn_posix` works
on Darwin specifically — the implementation agent runs on Windows, so we
defer real verification to the user's Mac via this skipped-on-non-Darwin
smoke. CI runners are typically Linux, where this also runs (Linux is a
near-cousin of the macOS POSIX backend), but ``pytest -k macos`` on a
Mac runs the real thing.

Why a separate file (not folded into :mod:`tests.ai.test_terminal`)?

* Keeps the cross-platform unit suite hermetic — no subprocess spawning
  in the default test run, so coverage stats remain clean.
* Makes it obvious where to look when investigating macOS-specific bugs
  reported by the user.

Mac-specific gotchas to keep in mind when extending this test:

* HFS+/APFS reports filenames in NFD; if you compare to user-supplied
  strings, normalise both sides through :func:`unicodedata.normalize`.
* ``/tmp`` is a symlink to ``/private/tmp`` — :func:`Path.resolve` flattens
  this so equality compares work.
* PTY allocation in App-Sandboxed parents (signed codex binaries) may
  refuse; report this clearly when investigating.
"""

from __future__ import annotations

import os
import select
import subprocess
import sys
import time

import pytest

pytestmark = [
    # Real pty.openpty + Popen: isolate from xdist so a hang/leak cannot crash a
    # parallel worker (#1896).
    pytest.mark.serial,
    pytest.mark.skipif(
        sys.platform != "darwin",
        reason="POSIX PTY smoke test — exercised on macOS only.",
    ),
]


def test_openpty_plus_popen_echo_roundtrip() -> None:
    """``pty.openpty`` master/slave + ``Popen(['echo', 'hi'])`` round-trip.

    The expectation is that ``echo hi`` runs in the PTY, ``hi\\n`` (or
    ``hi\\r\\n`` if the terminal added a CR) appears on the master side,
    and the subprocess exits cleanly within 5 seconds. The test fails
    fast if either side stalls.
    """
    # macOS: ``/tmp`` is a symlink to ``/private/tmp`` but we don't use it
    # here. ``pty`` is a stdlib module on POSIX.
    import pty

    master_fd, slave_fd = pty.openpty()
    try:
        proc = subprocess.Popen(
            ["echo", "hi"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            start_new_session=True,
        )
        # Drop the slave side in this process — the child owns it now.
        os.close(slave_fd)
        slave_fd = -1

        deadline = time.monotonic() + 5.0
        buffer = bytearray()
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master_fd], [], [], 0.5)
            if not ready:
                if proc.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(master_fd, 1024)
            except OSError:
                break
            if not chunk:
                break
            buffer.extend(chunk)
            if b"hi" in buffer:
                break

        rc = proc.wait(timeout=5.0)
        assert rc == 0, f"echo exited with {rc}"
        assert b"hi" in buffer, f"PTY output missing 'hi': {buffer!r}"
    finally:
        os.close(master_fd)
        if slave_fd != -1:
            os.close(slave_fd)
