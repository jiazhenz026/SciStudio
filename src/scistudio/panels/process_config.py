"""Tunable limits for the panel process host."""
# Tunable limits for the panel process host (ADR-054 MiniApp FR-011/FR-012).
#
# The startup and call limits, the result budget, the queue depth, and the grace
# periods are spec decisions open to owner revision (adr-054-miniapp §6). Each is
# overridable by an environment variable so tests can drive fast timeouts without
# weakening the defaults the product ships with. Both the backend host and the
# subprocess bootstrap read the result budget from here so they agree on
# ``too_large``.

from __future__ import annotations

import os


def _num(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _int(name: str, default: int) -> int:
    return int(_num(name, default))


# FR-012: setup must complete within the startup limit or the context reports
# start_failed and offers Restart and Stop.
def startup_timeout() -> float:
    return _num("SCISTUDIO_PANEL_STARTUP_TIMEOUT", 120.0)


# FR-011: a call fails with timeout after the call limit; the process is then
# marked unresponsive and later calls fail busy until the running call returns.
def call_timeout() -> float:
    return _num("SCISTUDIO_PANEL_CALL_TIMEOUT", 60.0)


# FR-011: at most 16 calls may wait; a call beyond that fails at once with busy.
def max_waiting() -> int:
    return _int("SCISTUDIO_PANEL_MAX_WAITING", 16)


# FR-011: a result larger than the byte budget fails with too_large.
def max_result_bytes() -> int:
    return _int("SCISTUDIO_PANEL_MAX_RESULT_BYTES", 64 * 1024 * 1024)


# FR-013: teardown, then terminate with a grace period, then kill the tree.
def teardown_grace() -> float:
    return _num("SCISTUDIO_PANEL_TEARDOWN_GRACE", 5.0)


# FR-013: a context closes once its workspace realtime client has been gone for
# the disconnect grace period.
def client_disconnect_grace() -> float:
    return _num("SCISTUDIO_PANEL_CLIENT_GRACE", 30.0)


__all__ = [
    "call_timeout",
    "client_disconnect_grace",
    "max_result_bytes",
    "max_waiting",
    "startup_timeout",
    "teardown_grace",
]
