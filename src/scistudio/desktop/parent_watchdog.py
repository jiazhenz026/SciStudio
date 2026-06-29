"""Parent-death backstop for the bundled desktop backend (#1865).

The desktop Electron process spawns the backend (``scistudio gui --bundled``) as
a child. When Electron exits *without* sending SIGTERM — force-quit, crash, or
the ``app.exit()`` relaunch paths — POSIX reparents the backend to init (PID 1)
and it would otherwise run forever as an orphan, accumulating one stray process
per launch. The frontend can then reconnect to a stale orphan that never scanned
the active project's blocks, so freshly authored drop-in blocks fail to appear.

The watchdog here notices the spawning parent has gone and shuts the backend
down. It lives in the backend source tree, so the OTA hot-patch carries it to
existing installs without a reinstall. The Electron-side spawn-lifecycle fixes
(relaunch handler, single-instance lock) are tracked separately and need a new
app build.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

# How often the watchdog re-checks the parent PID, and how long to wait for a
# graceful uvicorn shutdown before hard-exiting an orphaned backend.
PARENT_WATCH_INTERVAL_S = 2.0
ORPHAN_SHUTDOWN_GRACE_S = 3.0


def backend_is_orphaned(initial_ppid: int, current_ppid: int) -> bool:
    """Return ``True`` when the process that launched this backend has exited.

    On POSIX an orphaned child is reparented to init (PID 1), so either a change
    away from the original parent PID or a current parent of PID 1 means the
    spawning parent is gone.

    ``initial_ppid <= 1`` means the backend was already orphaned (or the parent
    was unknown) at startup; there is then no live parent to track, so this
    returns ``False`` and the watchdog stays inert rather than self-terminating.
    """
    if initial_ppid <= 1:
        return False
    return current_ppid != initial_ppid or current_ppid == 1


def _shutdown_orphaned_backend() -> None:
    """Gracefully stop, then hard-exit, an orphaned bundled backend."""
    import contextlib
    import os
    import signal
    import time

    logger.warning("Parent process exited; shutting down orphaned bundled backend (#1865).")
    # Prefer a graceful uvicorn shutdown so lifespan teardown still runs.
    with contextlib.suppress(Exception):  # best-effort graceful path
        os.kill(os.getpid(), signal.SIGTERM)
    time.sleep(ORPHAN_SHUTDOWN_GRACE_S)
    # Hard fallback if graceful shutdown did not exit the process in time.
    os._exit(0)


def start_parent_death_watchdog(
    initial_ppid: int,
    *,
    interval: float = PARENT_WATCH_INTERVAL_S,
    on_orphan: Callable[[], None] | None = None,
    stop_event: threading.Event | None = None,
) -> threading.Thread | None:
    """Start a daemon thread that reaps this backend once it is orphaned.

    Returns the started thread, or ``None`` when there is no live parent to
    watch (``initial_ppid <= 1``). POSIX-only; callers gate on bundled mode.

    ``stop_event`` makes the poll loop interruptible: setting it ends the loop
    on the next tick without invoking the handler. The bundled runtime never
    sets it (the watchdog runs for the process lifetime); tests pass one so the
    daemon thread is stopped and joined deterministically rather than leaked.
    """
    if initial_ppid <= 1:
        return None

    handler = on_orphan or _shutdown_orphaned_backend
    stop = stop_event if stop_event is not None else threading.Event()

    def _run() -> None:
        import os

        # Event.wait returns True only when the stop event is set; on a timeout
        # (the common path) it returns False, so we poll the parent each tick.
        while not stop.wait(interval):
            if backend_is_orphaned(initial_ppid, os.getppid()):
                handler()
                return

    thread = threading.Thread(target=_run, name="scistudio-parent-watchdog", daemon=True)
    thread.start()
    return thread
