"""Behavior tests for ``ai_pty._subscribers`` (issue #1432).

Exercises the cross-WS broadcast registry without going through a
WebSocket round-trip; verifies that monkeypatch seams on the package
namespace work as the existing test suite expects.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from scistudio.api.routes import ai_pty
from scistudio.api.routes.ai_pty.subscribers import (
    broadcast_ai_pty_message,
    register_ai_pty_subscriber,
    unregister_ai_pty_subscriber,
)


@pytest.fixture(autouse=True)
def _reset_subscribers() -> None:
    """Clear the package-level subscriber set before and after each test."""
    ai_pty._ai_pty_subscribers.clear()
    yield
    ai_pty._ai_pty_subscribers.clear()


def test_register_and_unregister_are_idempotent() -> None:
    """Registering the same callback twice yields a single entry."""

    def cb(_: dict[str, Any]) -> None:
        return None

    register_ai_pty_subscriber(cb)
    register_ai_pty_subscriber(cb)
    assert len(ai_pty._ai_pty_subscribers) == 1
    unregister_ai_pty_subscriber(cb)
    assert cb not in ai_pty._ai_pty_subscribers
    # Second unregister no-ops.
    unregister_ai_pty_subscriber(cb)


def test_broadcast_delivers_to_sync_subscriber() -> None:
    """Sync callback receives the broadcast message verbatim."""
    received: list[dict[str, Any]] = []

    def cb(msg: dict[str, Any]) -> None:
        received.append(msg)

    register_ai_pty_subscriber(cb)
    asyncio.run(broadcast_ai_pty_message({"type": "block_pty_opened", "tab_id": "abc"}))
    assert received == [{"type": "block_pty_opened", "tab_id": "abc"}]


def test_broadcast_delivers_to_async_subscriber() -> None:
    """Async callback's coroutine result is awaited so the message lands."""
    received: list[dict[str, Any]] = []

    async def cb(msg: dict[str, Any]) -> None:
        received.append(msg)

    register_ai_pty_subscriber(cb)
    asyncio.run(broadcast_ai_pty_message({"type": "block_pty_closed", "block_run_id": "rid"}))
    assert received == [{"type": "block_pty_closed", "block_run_id": "rid"}]


def test_broadcast_swallows_subscriber_exception() -> None:
    """A flaky subscriber must not break delivery to the others."""
    received: list[dict[str, Any]] = []

    def flaky(_: dict[str, Any]) -> None:
        raise RuntimeError("subscriber boom")

    def good(msg: dict[str, Any]) -> None:
        received.append(msg)

    register_ai_pty_subscriber(flaky)
    register_ai_pty_subscriber(good)
    # Must not raise even though ``flaky`` does.
    asyncio.run(broadcast_ai_pty_message({"type": "block_pty_opened", "tab_id": "x"}))
    assert received == [{"type": "block_pty_opened", "tab_id": "x"}]


def test_subscriber_state_lives_on_package_namespace() -> None:
    """Subscriber state lives on the package for monkeypatch compatibility.

    Submodule must not maintain its own private subscriber set — the
    existing test suite (and ``scistudio.api.ws``) reach into the
    package-level state.
    """
    from scistudio.api.routes.ai_pty import subscribers

    # The submodule uses ``_pkg._ai_pty_subscribers`` at call time; it
    # must not shadow the state with its own module-level binding.
    assert not hasattr(subscribers, "_ai_pty_subscribers")
