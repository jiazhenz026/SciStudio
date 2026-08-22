"""Host-safety admission tests for ADR-022 Addendum 1."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import patch

import pytest

from scistudio.engine.resources import (
    AdmissionWaitReason,
    ResourceManager,
    ResourceSnapshot,
)


def _memory(percent: float) -> Any:
    return patch("psutil.virtual_memory", return_value=type("Memory", (), {"percent": percent})())


class TestResourceManagerConfiguration:
    def test_defaults_to_255_global_permits(self) -> None:
        manager = ResourceManager()
        assert manager.max_concurrent_blocks == 255
        assert manager.memory_high_watermark == 0.90
        assert manager.memory_critical == 0.95

    @pytest.mark.parametrize("value", [0, -1, True, 1.5, "2", None])
    def test_limit_must_be_a_positive_integer(self, value: object) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            ResourceManager(max_concurrent_blocks=value)  # type: ignore[arg-type]

    def test_explicit_serial_and_above_default_limits_are_supported(self) -> None:
        assert ResourceManager(max_concurrent_blocks=1).max_concurrent_blocks == 1
        assert ResourceManager(max_concurrent_blocks=512).max_concurrent_blocks == 512

    @pytest.mark.parametrize(
        ("high", "critical"),
        [(0.9, 0.9), (0.95, 0.90), (-0.1, 0.95), (0.9, 1.01)],
    )
    def test_memory_watermarks_are_ordered_probabilities(self, high: float, critical: float) -> None:
        with pytest.raises(ValueError, match="memory watermarks"):
            ResourceManager(memory_high_watermark=high, memory_critical=critical)


class TestRuntimeGlobalPermits:
    def test_default_rejects_the_256th_active_block(self) -> None:
        manager = ResourceManager()
        with _memory(10.0):
            decisions = [manager.try_acquire() for _ in range(256)]

        assert all(decision.admitted for decision in decisions[:255])
        assert decisions[255].admitted is False
        assert decisions[255].wait_reason is AdmissionWaitReason.CONCURRENCY_LIMIT
        assert manager.available.active_blocks == 255

    def test_release_is_idempotent(self) -> None:
        manager = ResourceManager(max_concurrent_blocks=1)
        with _memory(10.0):
            permit = manager.try_acquire().permit
        assert permit is not None
        assert manager.release(permit) is True
        assert manager.release(permit) is False
        assert manager.available.active_blocks == 0

    def test_manager_rejects_a_foreign_permit(self) -> None:
        first = ResourceManager(max_concurrent_blocks=1)
        second = ResourceManager(max_concurrent_blocks=1)
        with _memory(10.0):
            permit = first.try_acquire().permit
        assert permit is not None
        assert second.release(permit) is False
        assert first.available.active_blocks == 1

    def test_concurrent_acquire_is_atomic(self) -> None:
        manager = ResourceManager(max_concurrent_blocks=7)
        with _memory(10.0), ThreadPoolExecutor(max_workers=32) as executor:
            decisions = list(executor.map(lambda _: manager.try_acquire(), range(64)))
        assert sum(decision.admitted for decision in decisions) == 7
        assert manager.available.active_blocks == 7

    def test_release_listener_failure_does_not_block_other_listeners(self) -> None:
        manager = ResourceManager(max_concurrent_blocks=1)
        calls: list[str] = []

        def broken() -> None:
            calls.append("broken")
            raise RuntimeError("listener failed")

        def healthy() -> None:
            calls.append("healthy")

        manager.subscribe_release(broken)
        manager.subscribe_release(healthy)
        with _memory(10.0):
            permit = manager.try_acquire().permit
        assert permit is not None
        assert manager.release(permit) is True
        assert sorted(calls) == ["broken", "healthy"]

    def test_unsubscribe_release_stops_notifications(self) -> None:
        manager = ResourceManager(max_concurrent_blocks=1)
        calls: list[str] = []

        def listener() -> None:
            calls.append("called")

        manager.subscribe_release(listener)
        manager.unsubscribe_release(listener)
        with _memory(10.0):
            permit = manager.try_acquire().permit
        assert permit is not None
        assert manager.release(permit) is True
        assert calls == []


class TestMemoryAdmission:
    def test_low_memory_defers_to_concurrency_limit(self) -> None:
        manager = ResourceManager(max_concurrent_blocks=2, memory_high_watermark=0.80, memory_critical=0.95)
        with _memory(80.0):
            assert manager.try_acquire().admitted is True
            assert manager.try_acquire().admitted is True
            denied = manager.try_acquire()
        assert denied.wait_reason is AdmissionWaitReason.CONCURRENCY_LIMIT

    @pytest.mark.parametrize("percent", [95.0, 99.0])
    def test_critical_memory_is_a_hard_stop(self, percent: float) -> None:
        manager = ResourceManager(memory_high_watermark=0.80, memory_critical=0.95)
        with _memory(percent):
            denied = manager.try_acquire()
        assert denied.admitted is False
        assert denied.wait_reason is AdmissionWaitReason.MEMORY_PRESSURE_CRITICAL

    def test_high_memory_allows_one_block_when_runtime_is_idle(self) -> None:
        manager = ResourceManager(max_concurrent_blocks=5, memory_high_watermark=0.80, memory_critical=0.95)
        with _memory(90.0):
            first = manager.try_acquire()
            second = manager.try_acquire()
        assert first.admitted is True
        assert second.admitted is False
        assert second.wait_reason is AdmissionWaitReason.MEMORY_PRESSURE_HIGH

    def test_high_memory_escape_resets_after_release(self) -> None:
        manager = ResourceManager(max_concurrent_blocks=5, memory_high_watermark=0.80, memory_critical=0.95)
        with _memory(90.0):
            first = manager.try_acquire()
            assert first.permit is not None
            assert manager.release(first.permit) is True
            assert manager.try_acquire().admitted is True


def test_snapshot_reports_only_host_safety_state() -> None:
    manager = ResourceManager(max_concurrent_blocks=3)
    with _memory(42.0):
        decision = manager.try_acquire()
        snapshot = manager.available
    assert decision.admitted is True
    assert snapshot == ResourceSnapshot(active_blocks=1, max_concurrent_blocks=3, system_memory_percent=0.42)
    assert snapshot.available_concurrency_permits == 2
    assert not hasattr(snapshot, "available_gpu_slots")
    assert not hasattr(snapshot, "available_cpu_workers")
