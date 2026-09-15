"""Track connected GUI workspaces for backend operations that need a workspace."""
# Which workspace realtime clients are connected, for anything outside the API.
#
# ADR-054 MiniApp FR-013/FR-030. The realtime layer
# (:mod:`scistudio.api.ws`) already knew which browsers were attached, but it
# knew it as a set of Python object ids private to that module, so nothing else
# could ask the two questions the MiniApp feature asks:
#
# * *Is any workspace open at all?* — the agent's ``open_miniapp`` tool has to
#   say "no workspace is open" rather than report success into nowhere.
# * *Is this particular workspace still gone?* — a ``miniapp`` context is bound
#   to the client that opened it and closes once that client has been away for
#   the disconnect grace period.
#
# This module is the shared answer. It lives under :mod:`scistudio.engine`
# rather than :mod:`scistudio.api` for one reason: :mod:`scistudio.ai` may
# import the engine and may not import the API (import-linter contract "AI must
# not depend on api"), and the agent tool is an ``ai`` consumer.
#
# It holds identity only — no sockets, no queues, no callbacks — so registering
# cannot fail and reading cannot block. The realtime layer registers on connect
# and unregisters in its ``finally`` block; the grace period and every decision
# taken on a disconnect stay there.

from __future__ import annotations

import threading

__all__ = ["any_connected", "connected", "register", "unregister"]

_lock = threading.Lock()
_clients: set[str] = set()


def register(client_id: str) -> None:
    """Record *client_id* as a connected workspace realtime client."""
    with _lock:
        _clients.add(client_id)


def unregister(client_id: str) -> None:
    """Forget *client_id*; unknown ids are ignored so a double close is safe."""
    with _lock:
        _clients.discard(client_id)


def connected() -> tuple[str, ...]:
    """Return the connected client ids, as a snapshot the caller may hold."""
    with _lock:
        return tuple(sorted(_clients))


def any_connected() -> bool:
    """Return whether any workspace realtime client is connected."""
    with _lock:
        return bool(_clients)
