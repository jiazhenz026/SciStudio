"""Regression test for #884.

ADR-035 §3.5 path (a) (the MCP ``finish_ai_block`` tool) resolves the
active run dir from ``MCPContext.ai_block_run_dir`` or the
``SCISTUDIO_AI_BLOCK_RUN_DIR`` env var. The env var had no producer —
the engine PTY spawn never injected it — so every call returned
``not_in_ai_block_context`` and path (a) was dead-on-arrival.

The fix threads ``extra_env`` through ``PtyProcess.__init__`` so
``open_engine_initiated_tab`` can pass ``SCISTUDIO_AI_BLOCK_RUN_DIR``
into the spawned subprocess env. This test pins that contract by
spawning a tiny Python child that prints its env value back over the
PTY and asserts the bytes round-trip.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from scistudio.ai.agent.terminal import PtyProcess


def _python_print_env_argv(var: str) -> list[str]:
    """A tiny subprocess that prints one env var then exits."""
    return [
        sys.executable,
        "-c",
        f"import os, sys; sys.stdout.write(os.environ.get({var!r}, '<unset>') + chr(10)); sys.stdout.flush()",
    ]


def _read_until(pty: PtyProcess, needle: bytes, deadline_s: float = 5.0) -> bytes:
    """Read from the PTY until *needle* appears or the deadline passes."""
    buf = bytearray()
    deadline = time.monotonic() + deadline_s
    while time.monotonic() < deadline:
        chunk = pty.read(timeout=0.2)
        if chunk:
            buf.extend(chunk)
            if needle in bytes(buf):
                return bytes(buf)
    return bytes(buf)


def test_pty_process_extra_env_reaches_child(tmp_path: Path) -> None:
    """Caller-supplied ``extra_env`` is visible inside the spawned process."""
    pty = PtyProcess(
        _python_print_env_argv("SCISTUDIO_AI_BLOCK_RUN_DIR"),
        cwd=tmp_path,
        cols=80,
        rows=24,
        extra_env={"SCISTUDIO_AI_BLOCK_RUN_DIR": str(tmp_path / "run-abc")},
    )
    try:
        # Child writes the value then exits — wait for the value to
        # arrive in the PTY buffer.
        out = _read_until(pty, b"run-abc", deadline_s=5.0)
        assert b"run-abc" in out, (
            f"extra_env value missing from child stdout. Got: {out!r}. "
            "open_engine_initiated_tab depends on this for #884."
        )
        assert b"<unset>" not in out, "Env var resolved to <unset> — extra_env was not applied."
    finally:
        pty.kill_tree()


def test_pty_process_extra_env_overrides_inherited(tmp_path: Path) -> None:
    """``extra_env`` overrides the inherited environment.

    Pins the precedence rule documented in ``PtyProcess.__init__``: caller
    env wins over anything inherited from the engine process. Without this
    rule a stale ``SCISTUDIO_AI_BLOCK_RUN_DIR`` from a prior block run could
    leak into the next block's PTY.
    """
    import os

    sentinel_var = "SCISTUDIO_TEST_EXTRA_ENV_OVERRIDE_884"
    os.environ[sentinel_var] = "inherited-value"
    try:
        pty = PtyProcess(
            _python_print_env_argv(sentinel_var),
            cwd=tmp_path,
            cols=80,
            rows=24,
            extra_env={sentinel_var: "override-value"},
        )
        try:
            out = _read_until(pty, b"override-value", deadline_s=5.0)
            assert b"override-value" in out
            assert b"inherited-value" not in out
        finally:
            pty.kill_tree()
    finally:
        os.environ.pop(sentinel_var, None)
