"""Tests for PlatformOps — platform.py (#495)."""

from __future__ import annotations

import sys

import pytest

from scistudio.engine.runners.platform import PosixOps

# ---------------------------------------------------------------------------
# PosixOps.is_alive — invalid PID guard (#495)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="PosixOps only on Unix")
class TestPosixOpsIsAliveGuard:
    """pid <= 0 must never reach os.kill(); return False immediately."""

    def test_negative_one(self):
        """pid=-1 would signal all user processes via os.kill(-1, 0)."""
        ops = PosixOps()
        assert ops.is_alive(-1) is False

    def test_zero(self):
        """pid=0 would signal the caller's process group."""
        ops = PosixOps()
        assert ops.is_alive(0) is False

    def test_large_negative(self):
        ops = PosixOps()
        assert ops.is_alive(-9999) is False

    def test_valid_pid_self(self):
        """Sanity: the current process should be alive."""
        import os

        ops = PosixOps()
        assert ops.is_alive(os.getpid()) is True
