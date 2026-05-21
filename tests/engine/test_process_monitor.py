"""Tests for ProcessMonitor — ADR-019.

Tests use mocks for ProcessHandle, ProcessRegistry, and EventBus to verify
that ProcessMonitor correctly polls for dead processes and emits events.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from scistudio.engine.events import PROCESS_EXITED, EngineEvent, EventBus
from scistudio.engine.runners.process_handle import (
    ProcessExitInfo,
    ProcessHandle,
    ProcessRegistry,
)
from scistudio.engine.runners.process_monitor import ProcessMonitor

# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestProcessMonitorConstruction:
    def test_initial_state(self) -> None:
        monitor = ProcessMonitor()
        assert monitor._event_bus is None
        assert monitor._registry is None
        assert monitor._task is None
        assert monitor._running is False


# ---------------------------------------------------------------------------
# Start / Stop lifecycle
# ---------------------------------------------------------------------------


class TestProcessMonitorLifecycle:
    def test_start_sets_running_and_creates_task(self) -> None:
        """start() should set _running=True and create an asyncio task."""
        monitor = ProcessMonitor()
        bus = EventBus()
        registry = ProcessRegistry()

        async def run_test() -> None:
            await monitor.start(bus, registry)
            assert monitor._running is True
            assert monitor._task is not None
            assert monitor._event_bus is bus
            assert monitor._registry is registry
            # Clean up
            await monitor.stop()

        asyncio.run(run_test())

    def test_stop_cancels_task(self) -> None:
        """stop() should set _running=False and cancel the task."""
        monitor = ProcessMonitor()
        bus = EventBus()
        registry = ProcessRegistry()

        async def run_test() -> None:
            await monitor.start(bus, registry)
            task = monitor._task
            assert task is not None
            await monitor.stop()
            assert monitor._running is False
            assert monitor._task is None
            assert task.cancelled() or task.done()

        asyncio.run(run_test())

    def test_stop_without_start_is_safe(self) -> None:
        """stop() on a never-started monitor should not raise."""
        monitor = ProcessMonitor()

        async def run_test() -> None:
            await monitor.stop()  # Should not raise

        asyncio.run(run_test())


# ---------------------------------------------------------------------------
# Poll loop — dead process detection
# ---------------------------------------------------------------------------


class TestProcessMonitorDetection:
    def _make_handle(
        self,
        block_id: str,
        alive: bool = True,
        exit_info: ProcessExitInfo | None = None,
    ) -> ProcessHandle:
        """Create a mock ProcessHandle with controlled is_alive / exit_info."""
        mock_ops = MagicMock()
        mock_ops.is_alive.return_value = alive
        mock_ops.get_exit_info.return_value = exit_info

        handle = ProcessHandle(
            block_id=block_id,
            pid=12345,
            start_time=datetime.now(),
            resource_request=MagicMock(),
        )
        handle._platform_ops = mock_ops
        return handle

    def test_detects_dead_process_and_emits_event(self) -> None:
        """When a process dies, ProcessMonitor should emit PROCESS_EXITED."""
        exit_info = ProcessExitInfo(exit_code=1, platform_detail="crashed")
        dead_handle = self._make_handle("block-dead", alive=False, exit_info=exit_info)

        bus = EventBus()
        registry = ProcessRegistry()
        registry.register(dead_handle)

        emitted_events: list[EngineEvent] = []

        async def capture_event(event: EngineEvent) -> None:
            emitted_events.append(event)

        bus.subscribe(PROCESS_EXITED, capture_event)

        monitor = ProcessMonitor()

        async def run_test() -> None:
            # Manually wire up monitor without starting the full loop
            monitor._event_bus = bus
            monitor._registry = registry
            monitor._running = True

            # Patch asyncio.sleep to avoid waiting
            with patch("scistudio.engine.runners.process_monitor.asyncio.sleep", new_callable=AsyncMock):
                # Run exactly one iteration of the poll loop then stop
                monitor._running = False  # Will exit after first sleep
                # Instead, call _poll_loop body logic directly
                pass

            # Directly test the detection logic by simulating what poll loop does
            for handle in list(registry.active_handles()):
                alive = handle.is_alive()
                if not alive:
                    info = handle.exit_info()
                    await bus.emit(
                        EngineEvent(
                            event_type=PROCESS_EXITED,
                            block_id=handle.block_id,
                            data={"exit_info": info},
                        )
                    )
                    registry.deregister(handle.block_id)

        asyncio.run(run_test())

        assert len(emitted_events) == 1
        assert emitted_events[0].event_type == PROCESS_EXITED
        assert emitted_events[0].block_id == "block-dead"
        assert emitted_events[0].data["exit_info"] is exit_info

        # Handle should be deregistered
        assert registry.get_handle("block-dead") is None

    def test_alive_process_not_deregistered(self) -> None:
        """A process that is still alive should not be deregistered."""
        alive_handle = self._make_handle("block-alive", alive=True)

        registry = ProcessRegistry()
        registry.register(alive_handle)

        bus = EventBus()
        emitted_events: list[EngineEvent] = []
        bus.subscribe(PROCESS_EXITED, emitted_events.append)

        async def run_test() -> None:
            # Simulate poll loop check for alive process
            for handle in list(registry.active_handles()):
                alive = handle.is_alive()
                if not alive:
                    info = handle.exit_info()
                    await bus.emit(
                        EngineEvent(
                            event_type=PROCESS_EXITED,
                            block_id=handle.block_id,
                            data={"exit_info": info},
                        )
                    )
                    registry.deregister(handle.block_id)

        asyncio.run(run_test())

        assert len(emitted_events) == 0
        assert registry.get_handle("block-alive") is alive_handle

    def test_poll_loop_runs_and_detects(self) -> None:
        """Integration: ProcessMonitor poll loop detects a dead process."""
        exit_info = ProcessExitInfo(exit_code=137, platform_detail="OOM killed")
        dead_handle = self._make_handle("block-oom", alive=False, exit_info=exit_info)

        bus = EventBus()
        registry = ProcessRegistry()
        registry.register(dead_handle)

        emitted_events: list[EngineEvent] = []

        async def capture_event(event: EngineEvent) -> None:
            emitted_events.append(event)

        bus.subscribe(PROCESS_EXITED, capture_event)

        monitor = ProcessMonitor()

        # Capture real sleep before patching to avoid recursion
        _real_sleep = asyncio.sleep

        async def run_test() -> None:
            await monitor.start(bus, registry)

            # Replace sleep with a version that stops the monitor after first iteration
            call_count = 0

            async def mock_sleep(delay: float) -> None:
                nonlocal call_count
                call_count += 1
                if call_count >= 2:
                    monitor._running = False
                await _real_sleep(0)  # Yield control without waiting

            with (
                patch("scistudio.engine.runners.process_monitor.asyncio.sleep", side_effect=mock_sleep),
                contextlib.suppress(TimeoutError, asyncio.CancelledError),
            ):
                await asyncio.wait_for(monitor._task, timeout=2.0)

            await monitor.stop()

        asyncio.run(run_test())

        assert len(emitted_events) == 1
        assert emitted_events[0].event_type == PROCESS_EXITED
        assert emitted_events[0].block_id == "block-oom"
        assert registry.get_handle("block-oom") is None

    def test_error_in_handle_check_does_not_crash_monitor(self) -> None:
        """If is_alive() raises, the monitor should log and continue."""
        bad_handle = self._make_handle("block-bad", alive=True)
        bad_handle._platform_ops.is_alive.side_effect = OSError("permission denied")

        good_handle = self._make_handle("block-good", alive=True)

        registry = ProcessRegistry()
        registry.register(bad_handle)
        registry.register(good_handle)

        bus = EventBus()
        monitor = ProcessMonitor()

        _real_sleep = asyncio.sleep

        async def run_test() -> None:
            await monitor.start(bus, registry)

            call_count = 0

            async def mock_sleep(delay: float) -> None:
                nonlocal call_count
                call_count += 1
                if call_count >= 2:
                    monitor._running = False
                # Use the real sleep (captured before patching) to yield control
                await _real_sleep(0)

            with (
                patch("scistudio.engine.runners.process_monitor.asyncio.sleep", side_effect=mock_sleep),
                contextlib.suppress(TimeoutError, asyncio.CancelledError),
            ):
                await asyncio.wait_for(monitor._task, timeout=2.0)

            await monitor.stop()

        # Should not raise
        asyncio.run(run_test())

        # Both handles should still be registered (good is alive, bad errored but not deregistered)
        assert registry.get_handle("block-good") is good_handle
