"""A graceful backend stop, requested by the process that launched it (#2327).

A Windows process cannot be sent a SIGTERM it can handle: Node's
``ChildProcess.kill`` terminates it outright, and so does ``taskkill /F``. The
desktop shell therefore asks the bundled backend to stop by closing the
backend's stdin. With ``SCISTUDIO_STOP_ON_STDIN_EOF=1`` in its environment, the
backend treats end-of-file on stdin as a stop request and raises ``SIGTERM`` in
itself. uvicorn handles that like a delivered signal and runs the application
lifespan's shutdown, which ends workflow runs with a terminal lineage status
(``ApiRuntime.shutdown_workflow_runs``). Only the parent holds the pipe's write
end, so the request needs no token.

On macOS and Linux the shell keeps sending a real SIGTERM, and does not set the
variable. See section 4.6 and FR-015 of the ADR-055 Spec 3 local background
runtime spec.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from collections.abc import Callable
from typing import IO, Any

logger = logging.getLogger(__name__)

STOP_ON_STDIN_EOF_ENV = "SCISTUDIO_STOP_ON_STDIN_EOF"

_started_lock = threading.Lock()
_started = False


def _raise_sigterm() -> None:
    signal.raise_signal(signal.SIGTERM)


def watch_for_stop_request(
    stream: IO[Any],
    request_stop: Callable[[], None] = _raise_sigterm,
) -> threading.Thread:
    """Call *request_stop* once *stream* reaches end-of-file.

    A read error is not a stop request: the watcher logs it and ends without
    calling *request_stop*.
    """

    def _watch() -> None:
        try:
            while stream.read(1024):
                pass
        except (OSError, ValueError):
            logger.debug("#2327: stop-request stream failed; not treating it as a stop request", exc_info=True)
            return
        logger.info("#2327: the launching process closed stdin; stopping the backend gracefully")
        request_stop()

    thread = threading.Thread(target=_watch, name="scistudio-stop-request", daemon=True)
    thread.start()
    return thread


def start_stop_request_watcher() -> threading.Thread | None:
    """Start the stdin watcher once per process, when the launcher asked for it."""
    global _started

    if os.environ.get(STOP_ON_STDIN_EOF_ENV) != "1":
        return None
    stdin = sys.stdin
    stream = getattr(stdin, "buffer", None) or stdin
    if stream is None:
        return None
    with _started_lock:
        if _started:
            return None
        _started = True
    return watch_for_stop_request(stream)


__all__ = ["STOP_ON_STDIN_EOF_ENV", "start_stop_request_watcher", "watch_for_stop_request"]
