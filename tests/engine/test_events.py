"""Tests for EventBus — ADR-018."""

from __future__ import annotations

import asyncio

from scistudio.engine.events import (
    BLOCK_DONE,
    BLOCK_ERROR,
    BLOCK_READY,
    BLOCK_RUNNING,
    CHECKPOINT_SAVED,
    EngineEvent,
    EventBus,
)

# ---------------------------------------------------------------------------
# EngineEvent dataclass construction
# ---------------------------------------------------------------------------


class TestEngineEvent:
    """Tests for the EngineEvent dataclass."""

    def test_construction_minimal(self) -> None:
        event = EngineEvent(event_type=BLOCK_READY)
        assert event.event_type == BLOCK_READY
        assert event.block_id is None
        assert event.data == {}
        assert event.timestamp is not None

    def test_construction_full(self) -> None:
        event = EngineEvent(
            event_type=BLOCK_DONE,
            block_id="block-42",
            data={"elapsed": 1.5},
        )
        assert event.event_type == BLOCK_DONE
        assert event.block_id == "block-42"
        assert event.data == {"elapsed": 1.5}


# ---------------------------------------------------------------------------
# EventBus tests
# ---------------------------------------------------------------------------


class TestEventBus:
    """Tests for the EventBus publish/subscribe dispatcher."""

    def test_subscribe_and_emit_round_trip(self) -> None:
        """A subscribed sync callback receives the emitted event."""
        bus = EventBus()
        received: list[EngineEvent] = []

        bus.subscribe(BLOCK_READY, received.append)

        event = EngineEvent(event_type=BLOCK_READY, block_id="b1")
        asyncio.run(bus.emit(event))

        assert len(received) == 1
        assert received[0] is event

    def test_unsubscribe_removes_callback(self) -> None:
        """After unsubscribe, the callback no longer receives events."""
        bus = EventBus()
        received: list[EngineEvent] = []

        bus.subscribe(BLOCK_DONE, received.append)
        bus.unsubscribe(BLOCK_DONE, received.append)

        event = EngineEvent(event_type=BLOCK_DONE)
        asyncio.run(bus.emit(event))

        assert received == []

    def test_unsubscribe_nonexistent_callback_no_error(self) -> None:
        """Unsubscribing a callback that was never registered is a no-op."""
        bus = EventBus()
        bus.unsubscribe(BLOCK_READY, lambda e: None)  # should not raise

    def test_multiple_subscribers_per_event(self) -> None:
        """Multiple callbacks for the same event type all receive the event."""
        bus = EventBus()
        results_a: list[EngineEvent] = []
        results_b: list[EngineEvent] = []

        bus.subscribe(BLOCK_RUNNING, results_a.append)
        bus.subscribe(BLOCK_RUNNING, results_b.append)

        event = EngineEvent(event_type=BLOCK_RUNNING, block_id="b2")
        asyncio.run(bus.emit(event))

        assert len(results_a) == 1
        assert len(results_b) == 1
        assert results_a[0] is event
        assert results_b[0] is event

    def test_error_isolation_between_subscribers(self) -> None:
        """A failing callback does not prevent subsequent callbacks."""
        bus = EventBus()
        received: list[EngineEvent] = []

        def bad_callback(event: EngineEvent) -> None:
            raise RuntimeError("boom")

        bus.subscribe(BLOCK_ERROR, bad_callback)
        bus.subscribe(BLOCK_ERROR, received.append)

        event = EngineEvent(event_type=BLOCK_ERROR, block_id="b3")
        # Should NOT raise even though bad_callback explodes
        asyncio.run(bus.emit(event))

        assert len(received) == 1
        assert received[0] is event

    def test_emit_unknown_event_type_no_error(self) -> None:
        """Emitting an event type with no subscribers is a silent no-op."""
        bus = EventBus()
        event = EngineEvent(event_type="totally_unknown_event")
        # Should not raise
        asyncio.run(bus.emit(event))

    def test_async_callback_support(self) -> None:
        """An async callback is properly awaited during emit."""
        bus = EventBus()
        received: list[EngineEvent] = []

        async def async_handler(event: EngineEvent) -> None:
            await asyncio.sleep(0)  # simulate async work
            received.append(event)

        bus.subscribe(CHECKPOINT_SAVED, async_handler)

        event = EngineEvent(event_type=CHECKPOINT_SAVED, block_id="b4")
        asyncio.run(bus.emit(event))

        assert len(received) == 1
        assert received[0] is event

    def test_mixed_sync_and_async_callbacks(self) -> None:
        """Both sync and async callbacks work in the same event type."""
        bus = EventBus()
        sync_received: list[str] = []
        async_received: list[str] = []

        def sync_handler(event: EngineEvent) -> None:
            sync_received.append(event.event_type)

        async def async_handler(event: EngineEvent) -> None:
            await asyncio.sleep(0)
            async_received.append(event.event_type)

        bus.subscribe(BLOCK_DONE, sync_handler)
        bus.subscribe(BLOCK_DONE, async_handler)

        asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_DONE)))

        assert sync_received == [BLOCK_DONE]
        assert async_received == [BLOCK_DONE]

    def test_async_error_isolation(self) -> None:
        """A failing async callback does not block subsequent callbacks."""
        bus = EventBus()
        received: list[EngineEvent] = []

        async def bad_async(event: EngineEvent) -> None:
            raise ValueError("async boom")

        bus.subscribe(BLOCK_ERROR, bad_async)
        bus.subscribe(BLOCK_ERROR, received.append)

        event = EngineEvent(event_type=BLOCK_ERROR)
        asyncio.run(bus.emit(event))

        assert len(received) == 1

    def test_emit_safe_under_in_dispatch_unsubscribe(self) -> None:
        """#1544 (BUG-9): a callback that unsubscribes during dispatch must
        not corrupt the in-flight iteration.

        Pre-fix, ``emit`` iterated the live subscriber list; a callback that
        removed a subscriber mid-dispatch either skipped a later callback or
        raised ``RuntimeError: list changed size during iteration`` (for the
        equivalent dict-mutation case). With the snapshot copy, every
        callback present at emit start still runs.
        """
        bus = EventBus()
        order: list[str] = []

        def first(_event: EngineEvent) -> None:
            order.append("first")
            # Unsubscribe a *later* callback during dispatch.
            bus.unsubscribe(BLOCK_DONE, third)
            # Also unsubscribe self.
            bus.unsubscribe(BLOCK_DONE, first)

        def second(_event: EngineEvent) -> None:
            order.append("second")

        def third(_event: EngineEvent) -> None:
            order.append("third")

        bus.subscribe(BLOCK_DONE, first)
        bus.subscribe(BLOCK_DONE, second)
        bus.subscribe(BLOCK_DONE, third)

        asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_DONE)))

        # All three callbacks present at emit start ran exactly once, in order,
        # despite first() removing third() and itself mid-dispatch.
        assert order == ["first", "second", "third"]

    def test_emit_safe_under_in_dispatch_subscribe(self) -> None:
        """#1544 (BUG-9): subscribing during dispatch must not raise and the
        new callback only takes effect on the next emit (deterministic set)."""
        bus = EventBus()
        late: list[EngineEvent] = []

        def late_handler(event: EngineEvent) -> None:
            late.append(event)

        def adder(_event: EngineEvent) -> None:
            bus.subscribe(BLOCK_DONE, late_handler)

        bus.subscribe(BLOCK_DONE, adder)

        # First emit: adder registers late_handler, but the snapshot was taken
        # before it existed, so late_handler does not run this round.
        asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_DONE)))
        assert late == []

        # Second emit: late_handler is now in the snapshot and runs once.
        # (adder runs again and re-adds another late_handler, but that one
        # only takes effect next round.)
        asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_DONE)))
        assert len(late) == 1

    def test_subscriber_isolation_across_event_types(self) -> None:
        """Subscribers only receive events for their registered type."""
        bus = EventBus()
        ready_events: list[EngineEvent] = []
        done_events: list[EngineEvent] = []

        bus.subscribe(BLOCK_READY, ready_events.append)
        bus.subscribe(BLOCK_DONE, done_events.append)

        asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_READY)))
        asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_DONE)))

        assert len(ready_events) == 1
        assert len(done_events) == 1
        assert ready_events[0].event_type == BLOCK_READY
        assert done_events[0].event_type == BLOCK_DONE
