"""Tests for the bundled-backend parent-death backstop (#1865).

The desktop Electron process spawns the backend as a child. When Electron exits
without sending SIGTERM (force-quit / crash / ``app.exit()`` relaunch paths) the
backend is reparented to init and would otherwise run forever as an orphan. The
watchdog reaps the backend once it detects it has been orphaned.
"""

from __future__ import annotations

import os
import threading

import pytest

from scistudio.desktop import parent_watchdog


class TestBackendIsOrphaned:
    def test_unchanged_live_parent_is_not_orphaned(self) -> None:
        assert parent_watchdog.backend_is_orphaned(4321, 4321) is False

    def test_reparented_to_init_is_orphaned(self) -> None:
        assert parent_watchdog.backend_is_orphaned(4321, 1) is True

    def test_parent_pid_changed_is_orphaned(self) -> None:
        # Parent died and a new (different) parent was assigned.
        assert parent_watchdog.backend_is_orphaned(4321, 9999) is True

    @pytest.mark.parametrize("initial", [0, 1, -1])
    def test_already_orphaned_or_unknown_at_start_stays_inert(self, initial: int) -> None:
        # No live parent to track at startup -> never self-terminate.
        assert parent_watchdog.backend_is_orphaned(initial, 1) is False
        assert parent_watchdog.backend_is_orphaned(initial, 12345) is False


class TestStartParentDeathWatchdog:
    def test_returns_none_when_no_live_parent_to_watch(self) -> None:
        assert parent_watchdog.start_parent_death_watchdog(1) is None

    def test_fires_on_orphan_when_parent_goes_away(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fired = threading.Event()
        stop = threading.Event()
        # Pretend the spawning parent (pid 4321) has been replaced by init.
        monkeypatch.setattr(os, "getppid", lambda: 1)

        thread = parent_watchdog.start_parent_death_watchdog(
            4321,
            interval=0.01,
            on_orphan=fired.set,
            stop_event=stop,
        )
        assert thread is not None
        try:
            assert fired.wait(timeout=2.0), "watchdog did not fire after parent loss"
        finally:
            stop.set()
            thread.join(timeout=2.0)
        assert not thread.is_alive()

    def test_stays_quiet_while_parent_is_alive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fired = threading.Event()
        stop = threading.Event()
        # Parent pid never changes -> backend is not orphaned.
        monkeypatch.setattr(os, "getppid", lambda: 4321)

        thread = parent_watchdog.start_parent_death_watchdog(
            4321,
            interval=0.01,
            on_orphan=fired.set,
            stop_event=stop,
        )
        assert thread is not None
        try:
            # Give the daemon several poll intervals to (incorrectly) fire.
            assert not fired.wait(timeout=0.2)
            assert thread.is_alive()
        finally:
            # Stop and join deterministically so the daemon never leaks past the
            # test (a leaked while-loop thread crashed an xdist worker, #1867).
            stop.set()
            thread.join(timeout=2.0)
        assert not thread.is_alive()
        assert not fired.is_set()
