"""A graceful backend stop, requested by the process that launched it.

A Windows process cannot be sent a SIGTERM it can handle: Node's
``ChildProcess.kill`` terminates it outright, and so does ``taskkill /F``. The
desktop shell therefore asks the bundled backend to stop by closing the
backend's stdin. With ``SCISTUDIO_STOP_ON_STDIN_EOF=1`` in its environment, the
backend takes that pipe off its standard input as it starts. It keeps a
private duplicate that child processes cannot inherit, and points standard
input at the null device. Git and every other child the backend starts
therefore inherits the null device. On Windows, a child that inherited the
pipe would hang while the backend waits on it. A thread reads the private
duplicate with ``os.read``, never through ``sys.stdin``, and at end-of-file
raises ``SIGTERM`` in the backend. Only the parent holds the pipe's write end,
so the request needs no token. On macOS and Linux the shell sends a real
SIGTERM and does not set the variable.

The web server finishes its open connections before it runs the application's
shutdown, and a connected page keeps the log event stream and the event socket
open. :func:`arm_stop_notice` therefore makes each stop signal first call
:func:`begin_shutdown`, which ends the log stream and the AI terminal sessions,
so the application's shutdown runs within a bounded time.
"""

# Development references: #2327 (re-audit findings N1, N2 and R1), and section
# 4.6 and FR-015 of the ADR-055 Spec 3 local background runtime spec.

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import ApiRuntime

logger = logging.getLogger(__name__)

STOP_ON_STDIN_EOF_ENV = "SCISTUDIO_STOP_ON_STDIN_EOF"

_NOTICE_SIGNALS = ("SIGTERM", "SIGINT", "SIGBREAK")

_started_lock = threading.Lock()
_started = False

# Threads killing AI terminal process trees; the end of shutdown joins them.
_KILLERS: list[threading.Thread] = []
_killers_lock = threading.Lock()


def _raise_sigterm() -> None:
    signal.raise_signal(signal.SIGTERM)


def watch_for_stop_request(fd: int, request_stop: Callable[[], None] = _raise_sigterm) -> threading.Thread:
    """Call *request_stop* once the pipe at file descriptor *fd* reaches end-of-file.

    The watcher owns *fd* and closes it when it ends. A read error is not a
    stop request: the watcher logs it and ends without calling *request_stop*.

    Args:
        fd: A readable file descriptor, typically the private duplicate of the
            launcher's stdin pipe.
        request_stop: Called once, from the watcher thread, at end-of-file.

    Returns:
        The started daemon thread.
    """

    def _watch() -> None:
        reached_end = False
        try:
            while os.read(fd, 1024):
                pass
            reached_end = True
        except OSError:
            logger.debug("the stop-request pipe failed; not treating it as a stop request", exc_info=True)
        finally:
            with contextlib.suppress(OSError):
                os.close(fd)
        if reached_end:
            logger.info("the launching process closed stdin; stopping the backend gracefully")
            request_stop()

    thread = threading.Thread(target=_watch, name="scistudio-stop-request", daemon=True)
    thread.start()
    return thread


def _point_windows_standard_input_at_fd0() -> None:
    """Make the Win32 standard input handle follow file descriptor 0.

    A child process inherits the Win32 standard handle, not the C runtime's
    descriptor 0, so both must name the null device.
    """
    if sys.platform != "win32":
        return
    import ctypes
    import msvcrt

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.SetStdHandle.argtypes = (ctypes.c_uint32, ctypes.c_void_p)
    kernel32.SetStdHandle.restype = ctypes.c_int
    std_input_handle = 0xFFFFFFF6  # STD_INPUT_HANDLE, the DWORD value of -10
    if not kernel32.SetStdHandle(std_input_handle, msvcrt.get_osfhandle(0)):
        raise ctypes.WinError(ctypes.get_last_error())


def detach_standard_input() -> int:
    """Move standard input to a private descriptor and give descriptor 0 the null device.

    Returns:
        A new descriptor for the original standard input, which child
        processes cannot inherit.

    Raises:
        OSError: The descriptors could not be rearranged.
    """
    private = os.dup(0)  # not inheritable, so no child process holds the pipe
    try:
        null = os.open(os.devnull, os.O_RDONLY)
        try:
            os.dup2(null, 0)
        finally:
            os.close(null)
        _point_windows_standard_input_at_fd0()
    except OSError:
        os.close(private)
        raise
    # Nothing in the backend reads stdin; keep sys.stdin on the null device too.
    sys.stdin = open(os.devnull, encoding="utf-8")  # noqa: SIM115 - lives for the process
    return private


def start_stop_request_watcher() -> threading.Thread | None:
    """Watch the launcher's stdin pipe for a stop request, when it asked for one.

    Does nothing unless ``SCISTUDIO_STOP_ON_STDIN_EOF=1`` is set, and starts at
    most one watcher per process.

    Returns:
        The watcher thread, or ``None`` when no watcher was started.
    """
    global _started

    if os.environ.get(STOP_ON_STDIN_EOF_ENV) != "1":
        return None
    with _started_lock:
        if _started:
            return None
        _started = True
    try:
        private = detach_standard_input()
    except OSError:
        logger.warning(
            "could not take stdin as the stop-request channel; the launcher's force-kill is the only stop left",
            exc_info=True,
        )
        return None
    return watch_for_stop_request(private)


def arm_stop_notice(
    on_stopping: Callable[[], None],
    *,
    loop: asyncio.AbstractEventLoop | None = None,
) -> Callable[[], None]:
    """Make each stop signal call *on_stopping* before its current handler.

    Chains onto the SIGTERM, SIGINT and (on Windows) SIGBREAK handlers the web
    server installed. A stop request then ends the backend's long-lived streams
    before the server waits for its connections to close. With *loop*, the
    notice is scheduled on that event loop instead of running inside the signal
    handler. A signal with no Python-level handler is left alone, and nothing is
    armed off the main thread.

    Args:
        on_stopping: Called once per stop signal, before the previous handler.
        loop: The event loop to schedule *on_stopping* on.

    Returns:
        A function that restores the previous handlers wherever the chained
        handler is still installed.
    """
    if threading.current_thread() is not threading.main_thread():
        return lambda: None

    def _notify() -> None:
        try:
            if loop is not None and not loop.is_closed():
                loop.call_soon_threadsafe(on_stopping)
            else:
                on_stopping()
        except Exception:
            logger.warning("the stop notice failed", exc_info=True)

    installed: list[tuple[int, Any, Any]] = []
    for name in _NOTICE_SIGNALS:
        signum = getattr(signal, name, None)
        if signum is None:
            continue
        previous = signal.getsignal(signum)
        if not callable(previous):
            continue

        def _chained(received: int, frame: Any, previous: Callable[[int, Any], Any] = previous) -> None:
            _notify()
            previous(received, frame)

        try:
            signal.signal(signum, _chained)
        except (OSError, ValueError):
            continue
        installed.append((signum, previous, _chained))

    def disarm() -> None:
        for signum, previous, chained in installed:
            with contextlib.suppress(OSError, ValueError):
                if signal.getsignal(signum) is chained:
                    signal.signal(signum, previous)
        installed.clear()

    return disarm


def _kill_quietly(session: Any) -> None:
    try:
        session.kill_tree()
    except Exception:
        logger.warning("could not kill an AI terminal session", exc_info=True)


def terminate_ai_terminal_sessions(*, timeout_sec: float = 0.0) -> int:
    """Kill every AI terminal session and its process tree.

    A session with no socket attached, such as one the engine started in
    external-AI mode, has no other shutdown path. The kills run on daemon
    threads. With *timeout_sec*, this waits up to that long in total for them,
    including kills an earlier call started.

    Args:
        timeout_sec: How long to wait for the kills; ``0`` does not wait.

    Returns:
        The number of sessions this call started killing.
    """
    try:
        from scistudio.api.routes import ai_pty
    except Exception:
        logger.debug("AI terminal sessions are unavailable", exc_info=True)
        return 0
    started = 0
    for tab_id, session in list(ai_pty._active_ptys.items()):
        ai_pty._active_ptys.pop(tab_id, None)
        run_id = ai_pty._engine_tab_to_run.pop(tab_id, None)
        if run_id is not None:
            ai_pty._engine_run_to_run_dir.pop(run_id, None)
        killer = threading.Thread(target=_kill_quietly, args=(session,), name="scistudio-pty-kill", daemon=True)
        killer.start()
        with _killers_lock:
            _KILLERS.append(killer)
        started += 1
    if started:
        logger.info("stopping %d AI terminal session(s)", started)
    if timeout_sec > 0:
        deadline = time.monotonic() + timeout_sec
        with _killers_lock:
            pending = list(_KILLERS)
        for killer in pending:
            killer.join(max(0.0, deadline - time.monotonic()))
        with _killers_lock:
            _KILLERS[:] = [killer for killer in _KILLERS if killer.is_alive()]
    return started


def _session_project_dir(session: Any) -> Path | None:
    raw = getattr(session, "_cwd", None)
    if raw is None:
        return None
    try:
        return Path(raw).resolve()
    except (OSError, TypeError, ValueError):
        return None


def terminate_project_terminal_sessions(project_dir: Path) -> int:
    """Kill the AI terminal sessions started for the project at *project_dir*.

    A session belongs to the project it was started in: its working directory
    is that project or a directory inside it (an AI Block run folder). Leaving
    the project closes them, so an agent started there cannot act on the
    project opened next. The kills run on daemon threads.

    Returns:
        The number of sessions this call started killing.
    """
    # Development references: #2433.
    try:
        from scistudio.api.routes import ai_pty
    except Exception:
        logger.debug("AI terminal sessions are unavailable", exc_info=True)
        return 0
    try:
        root = Path(project_dir).resolve()
    except OSError:
        return 0
    started = 0
    for tab_id, session in list(ai_pty._active_ptys.items()):
        cwd = _session_project_dir(session)
        if cwd is None or not (cwd == root or cwd.is_relative_to(root)):
            continue
        ai_pty._active_ptys.pop(tab_id, None)
        run_id = ai_pty._engine_tab_to_run.pop(tab_id, None)
        if run_id is not None:
            ai_pty._engine_run_to_run_dir.pop(run_id, None)
        killer = threading.Thread(target=_kill_quietly, args=(session,), name="scistudio-pty-kill", daemon=True)
        killer.start()
        with _killers_lock:
            _KILLERS.append(killer)
        started += 1
    if started:
        logger.info("closed %d AI terminal session(s) of project %s", started, root)
    return started


def begin_shutdown(self: ApiRuntime) -> None:
    """End the backend's long-lived streams so a graceful stop can proceed.

    Closes the log event stream for every subscriber and kills the AI terminal
    sessions. Safe to call more than once.
    """
    self.log_broadcaster.close()
    terminate_ai_terminal_sessions()


__all__ = [
    "STOP_ON_STDIN_EOF_ENV",
    "arm_stop_notice",
    "begin_shutdown",
    "detach_standard_input",
    "start_stop_request_watcher",
    "terminate_ai_terminal_sessions",
    "terminate_project_terminal_sessions",
    "watch_for_stop_request",
]
