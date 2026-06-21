"""Tests for ResourceManager -- ADR-022 / ADR-018."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from scistudio.engine.resources import ResourceManager, ResourceRequest, ResourceSnapshot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_vm(percent: float) -> MagicMock:
    """Create a mock psutil.virtual_memory() return value."""
    vm = MagicMock()
    vm.percent = percent
    return vm


def _run(coro):
    """Run a coroutine synchronously for testing."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# ResourceRequest dataclass
# ---------------------------------------------------------------------------


class TestResourceRequest:
    def test_defaults(self):
        req = ResourceRequest()
        assert req.requires_gpu is False
        assert req.gpu_memory_gb == 0.0
        assert req.cpu_cores == 1

    def test_no_estimated_memory_gb(self):
        """ADR-022: estimated_memory_gb was removed."""
        assert not hasattr(ResourceRequest(), "estimated_memory_gb")


# ---------------------------------------------------------------------------
# ResourceSnapshot dataclass
# ---------------------------------------------------------------------------


class TestResourceSnapshot:
    def test_defaults(self):
        snap = ResourceSnapshot()
        assert snap.available_gpu_slots == 0
        assert snap.available_cpu_workers == 4
        assert snap.system_memory_percent == 0.0


# ---------------------------------------------------------------------------
# ResourceManager -- construction
# ---------------------------------------------------------------------------


class TestResourceManagerInit:
    def test_default_construction(self):
        # ADR-027 D10: gpu_slots=None triggers auto-detect; pass 0 explicitly
        # so this test exercises only the non-GPU defaults.
        rm = ResourceManager(gpu_slots=0)
        assert rm.gpu_slots == 0
        assert rm.max_cpu_workers == 4
        assert rm.memory_high_watermark == 0.90
        assert rm.memory_critical == 0.95
        assert rm._gpu_in_use == 0
        assert rm._cpu_in_use == 0
        assert rm._allocations == {}

    def test_custom_parameters(self):
        rm = ResourceManager(gpu_slots=2, cpu_workers=8, memory_high_watermark=0.70, memory_critical=0.90)
        assert rm.gpu_slots == 2
        assert rm.max_cpu_workers == 8
        assert rm.memory_high_watermark == 0.70
        assert rm.memory_critical == 0.90


# ---------------------------------------------------------------------------
# can_dispatch -- CPU slot limit
# ---------------------------------------------------------------------------


class TestCanDispatchCPU:
    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_cpu_under_limit(self, _mock):
        rm = ResourceManager(gpu_slots=0, cpu_workers=4)
        assert rm.can_dispatch(ResourceRequest(cpu_cores=2))

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_cpu_at_limit(self, _mock):
        rm = ResourceManager(gpu_slots=0, cpu_workers=2)
        rm._cpu_in_use = 2
        assert not rm.can_dispatch(ResourceRequest(cpu_cores=1))

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_cpu_exact_fit(self, _mock):
        rm = ResourceManager(gpu_slots=0, cpu_workers=4)
        rm._cpu_in_use = 3
        assert rm.can_dispatch(ResourceRequest(cpu_cores=1))

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_cpu_overflow(self, _mock):
        rm = ResourceManager(gpu_slots=0, cpu_workers=4)
        rm._cpu_in_use = 3
        assert not rm.can_dispatch(ResourceRequest(cpu_cores=2))


# ---------------------------------------------------------------------------
# can_dispatch -- GPU slot exhaustion
# ---------------------------------------------------------------------------


class TestCanDispatchGPU:
    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_gpu_available(self, _mock):
        rm = ResourceManager(gpu_slots=2)
        assert rm.can_dispatch(ResourceRequest(requires_gpu=True, gpu_memory_gb=4.0))

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_gpu_exhausted(self, _mock):
        rm = ResourceManager(gpu_slots=1)
        rm._gpu_in_use = 1
        assert not rm.can_dispatch(ResourceRequest(requires_gpu=True, gpu_memory_gb=4.0))

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_no_gpu_required_with_zero_slots(self, _mock):
        """Non-GPU request should pass even with zero GPU slots."""
        rm = ResourceManager(gpu_slots=0)
        assert rm.can_dispatch(ResourceRequest(requires_gpu=False))


# ---------------------------------------------------------------------------
# can_dispatch -- memory watermarks
# ---------------------------------------------------------------------------


class TestCanDispatchMemory:
    def test_below_watermark(self):
        rm = ResourceManager(gpu_slots=0, memory_high_watermark=0.80)
        with patch("psutil.virtual_memory", return_value=_mock_vm(50.0)):
            assert rm.can_dispatch(ResourceRequest(), active_count=1)

    def test_above_high_watermark(self):
        rm = ResourceManager(gpu_slots=0, memory_high_watermark=0.80)
        with patch("psutil.virtual_memory", return_value=_mock_vm(85.0)):
            assert not rm.can_dispatch(ResourceRequest(), active_count=1)

    def test_at_high_watermark_boundary(self):
        """Exactly at watermark should still dispatch (> not >=)."""
        rm = ResourceManager(gpu_slots=0, memory_high_watermark=0.80)
        with patch("psutil.virtual_memory", return_value=_mock_vm(80.0)):
            assert rm.can_dispatch(ResourceRequest(), active_count=1)

    def test_above_critical(self):
        rm = ResourceManager(gpu_slots=0, memory_critical=0.95)
        with patch("psutil.virtual_memory", return_value=_mock_vm(96.0)):
            assert not rm.can_dispatch(ResourceRequest(), active_count=1)

    def test_at_critical_boundary(self):
        """At exactly critical should block (>= check)."""
        rm = ResourceManager(gpu_slots=0, memory_critical=0.95)
        with patch("psutil.virtual_memory", return_value=_mock_vm(95.0)):
            assert not rm.can_dispatch(ResourceRequest(), active_count=1)


# ---------------------------------------------------------------------------
# acquire / release round-trip
# ---------------------------------------------------------------------------


class TestAcquireRelease:
    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_acquire_cpu(self, _mock):
        rm = ResourceManager(gpu_slots=0, cpu_workers=4)
        result = _run(rm.acquire(ResourceRequest(cpu_cores=2), block_id="b1"))
        assert result is True
        assert rm._cpu_in_use == 2
        assert "b1" in rm._allocations

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_acquire_gpu(self, _mock):
        rm = ResourceManager(gpu_slots=2)
        result = _run(rm.acquire(ResourceRequest(requires_gpu=True), block_id="g1"))
        assert result is True
        assert rm._gpu_in_use == 1

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_acquire_fails_when_full(self, _mock):
        rm = ResourceManager(gpu_slots=0, cpu_workers=2)
        rm._cpu_in_use = 2
        result = _run(rm.acquire(ResourceRequest(cpu_cores=1), block_id="x"))
        assert result is False
        assert "x" not in rm._allocations

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_release_cpu(self, _mock):
        rm = ResourceManager(gpu_slots=0, cpu_workers=4)
        req = ResourceRequest(cpu_cores=2)
        _run(rm.acquire(req, block_id="b1"))
        rm.release(req, block_id="b1")
        assert rm._cpu_in_use == 0
        assert "b1" not in rm._allocations

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_release_gpu(self, _mock):
        rm = ResourceManager(gpu_slots=2)
        req = ResourceRequest(requires_gpu=True)
        _run(rm.acquire(req, block_id="g1"))
        rm.release(req, block_id="g1")
        assert rm._gpu_in_use == 0

    def test_release_prevents_negative_counters(self):
        rm = ResourceManager(cpu_workers=4, gpu_slots=2)
        rm.release(ResourceRequest(cpu_cores=3, requires_gpu=True))
        assert rm._cpu_in_use == 0
        assert rm._gpu_in_use == 0

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_acquire_without_block_id(self, _mock):
        """Acquire without block_id should still work but not track allocation."""
        rm = ResourceManager(gpu_slots=0, cpu_workers=4)
        result = _run(rm.acquire(ResourceRequest(cpu_cores=1)))
        assert result is True
        assert rm._cpu_in_use == 1
        assert rm._allocations == {}


# ---------------------------------------------------------------------------
# available property
# ---------------------------------------------------------------------------


class TestAvailableProperty:
    @patch("psutil.virtual_memory", return_value=_mock_vm(42.0))
    def test_snapshot_values(self, _mock):
        rm = ResourceManager(gpu_slots=4, cpu_workers=8)
        rm._gpu_in_use = 1
        rm._cpu_in_use = 3
        snap = rm.available
        assert isinstance(snap, ResourceSnapshot)
        assert snap.available_gpu_slots == 3
        assert snap.available_cpu_workers == 5
        assert snap.system_memory_percent == pytest.approx(0.42)

    @patch("psutil.virtual_memory", return_value=_mock_vm(0.0))
    def test_snapshot_zero_memory(self, _mock):
        rm = ResourceManager(gpu_slots=0)
        snap = rm.available
        assert snap.system_memory_percent == 0.0


# ---------------------------------------------------------------------------
# EventBus auto-release (ADR-018)
# ---------------------------------------------------------------------------


class TestEventBusAutoRelease:
    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_auto_release_on_block_done(self, _mock):
        from scistudio.engine.events import BLOCK_DONE, EngineEvent, EventBus

        bus = EventBus()
        rm = ResourceManager(cpu_workers=4, gpu_slots=2, event_bus=bus)

        # Acquire resources
        req = ResourceRequest(cpu_cores=2, requires_gpu=True)
        _run(rm.acquire(req, block_id="block-1"))
        assert rm._cpu_in_use == 2
        assert rm._gpu_in_use == 1
        assert "block-1" in rm._allocations

        # Emit terminal event
        event = EngineEvent(event_type=BLOCK_DONE, block_id="block-1")
        _run(bus.emit(event))

        # Resources should be released
        assert rm._cpu_in_use == 0
        assert rm._gpu_in_use == 0
        assert "block-1" not in rm._allocations

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_auto_release_on_block_error(self, _mock):
        from scistudio.engine.events import BLOCK_ERROR, EngineEvent, EventBus

        bus = EventBus()
        rm = ResourceManager(gpu_slots=0, cpu_workers=4, event_bus=bus)

        req = ResourceRequest(cpu_cores=3)
        _run(rm.acquire(req, block_id="block-err"))
        assert rm._cpu_in_use == 3

        event = EngineEvent(event_type=BLOCK_ERROR, block_id="block-err")
        _run(bus.emit(event))

        assert rm._cpu_in_use == 0
        assert "block-err" not in rm._allocations

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_auto_release_on_block_cancelled(self, _mock):
        from scistudio.engine.events import BLOCK_CANCELLED, EngineEvent, EventBus

        bus = EventBus()
        rm = ResourceManager(gpu_slots=0, cpu_workers=4, event_bus=bus)

        req = ResourceRequest(cpu_cores=1)
        _run(rm.acquire(req, block_id="block-cancel"))

        event = EngineEvent(event_type=BLOCK_CANCELLED, block_id="block-cancel")
        _run(bus.emit(event))

        assert rm._cpu_in_use == 0
        assert "block-cancel" not in rm._allocations

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_event_for_unknown_block_id_is_ignored(self, _mock):
        from scistudio.engine.events import BLOCK_DONE, EngineEvent, EventBus

        bus = EventBus()
        rm = ResourceManager(gpu_slots=0, cpu_workers=4, event_bus=bus)

        req = ResourceRequest(cpu_cores=1)
        _run(rm.acquire(req, block_id="known"))

        # Emit event for a block_id not tracked
        event = EngineEvent(event_type=BLOCK_DONE, block_id="unknown")
        _run(bus.emit(event))  # Should not raise

        # Original allocation still present
        assert rm._cpu_in_use == 1
        assert "known" in rm._allocations

    def test_no_event_bus_no_subscriptions(self):
        """ResourceManager without event_bus should work fine."""
        rm = ResourceManager(gpu_slots=0, cpu_workers=4)
        assert rm._allocations == {}
        # No error, just no auto-release capability


# ---------------------------------------------------------------------------
# max_internal_workers / effective_cpu (#72)
# ---------------------------------------------------------------------------


class TestMaxInternalWorkers:
    def test_default_max_internal_workers(self):
        """Default max_internal_workers is 1, effective_cpu equals cpu_cores."""
        req = ResourceRequest(cpu_cores=2)
        assert req.max_internal_workers == 1
        assert req.effective_cpu == 2

    def test_effective_cpu_with_internal_workers(self):
        """effective_cpu = cpu_cores * max_internal_workers."""
        req = ResourceRequest(cpu_cores=2, max_internal_workers=4)
        assert req.effective_cpu == 8

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_can_dispatch_respects_effective_cpu(self, _mock):
        """can_dispatch blocks when effective CPU exceeds pool."""
        mgr = ResourceManager(gpu_slots=0, cpu_workers=4)
        # 1 core * 8 workers = 8 effective, exceeds 4-core pool
        req = ResourceRequest(cpu_cores=1, max_internal_workers=8)
        assert not mgr.can_dispatch(req)

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_acquire_uses_effective_cpu(self, _mock):
        """acquire() reserves effective_cpu worth of cores."""
        mgr = ResourceManager(gpu_slots=0, cpu_workers=10)
        req = ResourceRequest(cpu_cores=1, max_internal_workers=4)
        result = _run(mgr.acquire(req, block_id="b1"))
        assert result is True
        assert mgr._cpu_in_use == 4  # 1 * 4

    def test_release_uses_effective_cpu(self):
        """release() frees effective_cpu worth of cores."""
        mgr = ResourceManager(gpu_slots=0, cpu_workers=10)
        mgr._cpu_in_use = 8
        req = ResourceRequest(cpu_cores=2, max_internal_workers=4)
        mgr.release(req, block_id="b1")
        assert mgr._cpu_in_use == 0  # 8 - (2*4) = 0

    @patch("psutil.virtual_memory", return_value=_mock_vm(50.0))
    def test_backward_compatible_default(self, _mock):
        """Existing code using ResourceRequest(cpu_cores=N) still works."""
        mgr = ResourceManager(gpu_slots=0, cpu_workers=4)
        req = ResourceRequest(cpu_cores=2)
        assert mgr.can_dispatch(req)  # 2 effective < 4 pool


# ---------------------------------------------------------------------------
# can_dispatch -- deadlock prevention (#495)
# ---------------------------------------------------------------------------


class TestCanDispatchDeadlockPrevention:
    """When active_count == 0, the high watermark must be bypassed so that
    at least one block can start.  Only the critical threshold blocks.
    """

    def test_active_count_zero_bypasses_watermark(self):
        """Memory above watermark but below critical: allow when nothing running."""
        rm = ResourceManager(gpu_slots=0, memory_high_watermark=0.80, memory_critical=0.95)
        with patch("psutil.virtual_memory", return_value=_mock_vm(85.0)):
            assert rm.can_dispatch(ResourceRequest(), active_count=0)

    def test_active_count_zero_blocked_by_critical(self):
        """Memory above critical: block even when nothing running."""
        rm = ResourceManager(gpu_slots=0, memory_high_watermark=0.80, memory_critical=0.95)
        with patch("psutil.virtual_memory", return_value=_mock_vm(96.0)):
            assert not rm.can_dispatch(ResourceRequest(), active_count=0)

    def test_active_count_zero_at_critical_boundary(self):
        """Exactly at critical: block even when nothing running (>= check)."""
        rm = ResourceManager(gpu_slots=0, memory_high_watermark=0.80, memory_critical=0.95)
        with patch("psutil.virtual_memory", return_value=_mock_vm(95.0)):
            assert not rm.can_dispatch(ResourceRequest(), active_count=0)

    def test_active_count_nonzero_watermark_enforced(self):
        """Memory above watermark with tasks running: still blocked."""
        rm = ResourceManager(gpu_slots=0, memory_high_watermark=0.80, memory_critical=0.95)
        with patch("psutil.virtual_memory", return_value=_mock_vm(85.0)):
            assert not rm.can_dispatch(ResourceRequest(), active_count=1)

    def test_default_active_count_is_zero(self):
        """Default active_count=0 bypasses watermark (backward compat)."""
        rm = ResourceManager(gpu_slots=0, memory_high_watermark=0.80, memory_critical=0.95)
        with patch("psutil.virtual_memory", return_value=_mock_vm(85.0)):
            assert rm.can_dispatch(ResourceRequest())
