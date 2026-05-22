"""Cross-WS subscriber registry used by the engine-initiated tab path.

The workflow WS handler (``scistudio.api.ws``) registers one
subscriber per connection on accept and unregisters on disconnect.
Engine-initiated tab opens / closes call :func:`broadcast_ai_pty_message`
which fans out the message dict to every live subscriber. See the
package ``__init__`` module docstring for the rationale (ADR-035 §3.10
without adding new EngineEvent types).

State (``_ai_pty_subscribers``, ``_ai_pty_subscribers_lock``) lives on
the package namespace; this module accesses it via late-bound lookup so
the test suite's existing monkeypatch contract on the package keeps
working.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from scistudio.api.routes import ai_pty as _pkg

logger = logging.getLogger(__name__)


def register_ai_pty_subscriber(callback: _pkg._AiPtySubscriber) -> None:
    """Register a callback to receive ai_pty broadcast messages.

    The workflow WS handler (``scistudio.api.ws.websocket_handler``)
    registers one subscriber per active connection.

    Idempotent — registering the same callback twice is a no-op.
    """
    with _pkg._ai_pty_subscribers_lock:
        _pkg._ai_pty_subscribers.add(callback)


def unregister_ai_pty_subscriber(callback: _pkg._AiPtySubscriber) -> None:
    """Remove a previously registered subscriber.

    Silently no-ops if the callback was not registered (cleanup paths
    should never crash the WS teardown).
    """
    with _pkg._ai_pty_subscribers_lock:
        _pkg._ai_pty_subscribers.discard(callback)


async def broadcast_ai_pty_message(message: dict[str, Any]) -> None:
    """Fan-out *message* to every registered WS subscriber.

    Best-effort: subscriber exceptions are caught and logged so a single
    flaky client cannot break the broadcast for everyone else. Coroutine
    return values are awaited so async subscribers (the production WS
    handler queues the message into an asyncio.Queue) work correctly.
    """
    with _pkg._ai_pty_subscribers_lock:
        snapshot = list(_pkg._ai_pty_subscribers)
    for cb in snapshot:
        try:
            result = cb(message)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.warning("broadcast_ai_pty_message: subscriber raised", exc_info=True)
