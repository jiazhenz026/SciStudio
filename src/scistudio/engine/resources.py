"""ResourceManager — GPU slots, CPU workers, OS memory monitoring.

ADR-022: OS-level memory monitoring via psutil replaces estimated_memory_gb.
Reactive dispatch gating instead of predictive static estimates.

ADR-018: Auto-release on terminal block states via EventBus subscription.

ADR-027 D10: ``ResourceManager`` auto-detects physical GPU count when
``gpu_slots`` is ``None`` (the new default). The probe tries
``torch.cuda.device_count()`` first, then ``nvidia-smi -L``, then returns 0.
Explicit integer values are respected unchanged. When auto-detect returns 0
but a block declares ``requires_gpu=True``, a single WARNING is emitted from
``can_dispatch`` pointing the user at the project-config override.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


def _auto_detect_gpu_slots() -> int:
    """Best-effort GPU count detection. Tries torch, then nvidia-smi, then 0.

    ADR-027 D10: returns physical GPU count, not VRAM-aware slot calculation.
    Users with large models on small cards should override via project config.

    Probe order:

    1. ``torch.cuda.is_available()`` + ``torch.cuda.device_count()`` (fast,
       no subprocess). Skipped silently if torch is not installed.
    2. ``nvidia-smi -L`` parsed for lines starting with ``"GPU "``. Skipped
       silently if ``nvidia-smi`` is missing, times out, or returns non-zero.
    3. Returns ``0``.
    """
    try:
        import torch

        if torch.cuda.is_available():
            return int(torch.cuda.device_count())
    except ImportError:
        pass
    except Exception:  # pragma: no cover - defensive: torch present but broken
        pass

    try:
        import subprocess

        result = subprocess.run(
            ["nvidia-smi", "-L"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return sum(1 for line in result.stdout.splitlines() if line.startswith("GPU "))
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return 0


@dataclass
class ResourceRequest:
    """Declares the resources a block needs before it can be scheduled.

    ADR-022: estimated_memory_gb REMOVED. System memory is monitored at OS
    level via psutil, not estimated per-block. GPU memory still declared
    because VRAM is not reliably monitorable cross-platform.
    """

    requires_gpu: bool = False
    gpu_memory_gb: float = 0.0
    cpu_cores: int = 1
    max_internal_workers: int = 1
    """Number of internal worker threads/processes the block spawns.

    ADR-027 D8 (thread policy): the field is formally activated by D8.
    The scheduler treats ``cpu_cores * max_internal_workers`` as the block's
    total CPU footprint via :pyattr:`effective_cpu`, so a block that fans out
    to ``max_internal_workers`` library threads (e.g. ``torch`` DataParallel,
    MKL/OpenBLAS-multiplied numpy ops) is throttled correctly against the
    ``cpu_workers`` pool. Defaults to ``1`` (no internal parallelism).
    """
    # ADR-022: estimated_memory_gb REMOVED

    @property
    def effective_cpu(self) -> int:
        """Total CPU footprint: declared cores times internal parallelism.

        ADR-027 D8 (thread policy context): ``effective_cpu`` is the value
        the scheduler uses for dispatch gating, acquisition, and release.
        Block authors should set ``max_internal_workers`` to the number of
        threads/processes their library will spawn so the global CPU pool is
        not over-subscribed.
        """
        return self.cpu_cores * self.max_internal_workers


@dataclass
class ResourceSnapshot:
    """Read-only view of currently available resources.

    ADR-022: available_memory_gb replaced with system_memory_percent (0.0-1.0).
    """

    available_gpu_slots: int = 0
    available_cpu_workers: int = 4
    system_memory_percent: float = 0.0  # ADR-022: 0.0-1.0, from psutil


class ResourceManager:
    """Track and allocate compute resources for block execution.

    Layer 1 (this class): Dispatch gating (ADR-022).
        - GPU: discrete slot counting (declaration-based)
        - CPU: discrete core counting (declaration-based)
        - Memory: OS-level check via psutil.virtual_memory().percent
        - memory_high_watermark=0.80: pause dispatch above 80%
        - memory_critical=0.95: never dispatch above 95%

    Layer 2 (block-internal): _auto_flush, LazyList, parallel_map(max_workers)
        -- operates independently, not managed here.

    Layer 3 (OS): OS kills subprocess on OOM; the runner observes the
        non-zero exit and the scheduler marks ERROR.

    EventBus integration (ADR-018): automatic resource release on terminal
    block states via _on_block_terminal callback.

    ADR-027 D10: ``gpu_slots`` defaults to ``None``, which triggers
    :func:`_auto_detect_gpu_slots`. Explicit integer values (including ``0``)
    are respected unchanged and bypass auto-detection.
    """

    def __init__(
        self,
        gpu_slots: int | None = None,
        cpu_workers: int = 4,
        memory_high_watermark: float = 0.90,
        memory_critical: float = 0.95,
        event_bus: Any | None = None,
    ) -> None:
        # ADR-027 D10: None triggers auto-detect; explicit ints (including 0)
        # are respected unchanged.
        if gpu_slots is None:
            self._gpu_slots_auto_detected: bool = True
            gpu_slots = _auto_detect_gpu_slots()
        else:
            self._gpu_slots_auto_detected = False
        self.gpu_slots = gpu_slots
        self.max_cpu_workers = cpu_workers
        self.memory_high_watermark = memory_high_watermark
        self.memory_critical = memory_critical
        self._gpu_in_use: int = 0
        self._cpu_in_use: int = 0
        self._allocations: dict[str, ResourceRequest] = {}
        # ADR-027 D10: one-shot guard so the "no GPU but block requires it"
        # warning fires exactly once per ResourceManager instance.
        self._gpu_warning_emitted: bool = False

        if event_bus is not None:
            from scistudio.engine.events import (
                BLOCK_CANCELLED,
                BLOCK_DONE,
                BLOCK_ERROR,
            )

            event_bus.subscribe(BLOCK_DONE, self._on_block_terminal)
            event_bus.subscribe(BLOCK_ERROR, self._on_block_terminal)
            event_bus.subscribe(BLOCK_CANCELLED, self._on_block_terminal)

    def can_dispatch(self, request: ResourceRequest, active_count: int = 0) -> bool:
        """Check if resources are available AND system memory is below watermark.

        Returns False if:
        - GPU is required but all GPU slots are in use
        - Requested CPU cores would exceed the pool
        - System memory percent >= memory_critical (always blocked)
        - System memory percent > memory_high_watermark (paused) — but only
          when ``active_count > 0``

        Deadlock prevention (#495): when ``active_count == 0`` (nothing is
        currently executing), the high watermark is bypassed.  Only the
        critical threshold (0.95) acts as a hard cap.  Without this, a
        system whose baseline memory exceeds the watermark would refuse to
        dispatch any block, guaranteeing deadlock.

        ADR-027 D10: when ``request.requires_gpu`` and ``self.gpu_slots == 0``,
        a single WARNING is logged (per ResourceManager instance) explaining
        that the user can override via project config. The warning fires
        regardless of whether ``gpu_slots == 0`` came from auto-detect or an
        explicit override, because in both cases the GPU dispatch path is
        effectively dead.
        """
        import psutil

        # GPU check
        if request.requires_gpu and self._gpu_in_use >= self.gpu_slots:
            # ADR-027 D10: emit a single WARNING when no GPU is configured
            # but a block declares requires_gpu=True.
            if self.gpu_slots == 0 and not self._gpu_warning_emitted:
                self._gpu_warning_emitted = True
                logger.warning(
                    "No GPU detected (auto-detect returned 0 slots), but a "
                    "block declares requires_gpu=True. Set gpu_slots "
                    "explicitly in your project config to enable GPU dispatch."
                )
            return False
        # CPU check
        if self._cpu_in_use + request.effective_cpu > self.max_cpu_workers:
            return False
        # Memory check via psutil (ADR-022)
        mem_percent = psutil.virtual_memory().percent / 100.0
        if mem_percent >= self.memory_critical:
            return False
        # Deadlock prevention (#495): when nothing is running, skip the high
        # watermark so at least one block can start.  The critical threshold
        # above still acts as a hard cap.
        if active_count == 0:
            return True
        return not mem_percent > self.memory_high_watermark

    async def acquire(self, request: ResourceRequest, block_id: str = "") -> bool:
        """Reserve GPU slots and CPU cores.

        Memory is not reserved -- it drops naturally when subprocess exits
        (ADR-022). Allocation is tracked by block_id for auto-release
        (ADR-018).

        TODO(#887): this method currently has no production caller — the
        scheduler's ``_dispatch`` passes a default ``ResourceRequest()`` to
        ``can_dispatch`` and never calls ``acquire``/``release``, so the
        discrete GPU/CPU counters stay at zero (ADR-022 L1 gating deferred,
        low-risk per #887 / #1595). Kept as forward-compatible scaffolding.

        Returns True if resources were successfully acquired, False otherwise.
        """
        if not self.can_dispatch(request):
            return False
        if request.requires_gpu:
            self._gpu_in_use += 1
        self._cpu_in_use += request.effective_cpu
        if block_id:
            self._allocations[block_id] = request
        return True

    def release(self, request: ResourceRequest, block_id: str = "") -> None:
        """Return previously acquired GPU/CPU resources to the pool.

        Uses max(0, ...) to prevent negative counters in edge cases.
        """
        if request.requires_gpu:
            self._gpu_in_use = max(0, self._gpu_in_use - 1)
        self._cpu_in_use = max(0, self._cpu_in_use - request.effective_cpu)
        if block_id and block_id in self._allocations:
            del self._allocations[block_id]

    def _on_block_terminal(self, event: Any) -> None:
        """Auto-release resources when a block reaches a terminal state.

        Called by EventBus for BLOCK_DONE, BLOCK_ERROR, and
        BLOCK_CANCELLED events (ADR-018).
        """
        block_id = event.block_id
        if block_id and block_id in self._allocations:
            self.release(self._allocations[block_id], block_id)

    @property
    def available(self) -> ResourceSnapshot:
        """Return a snapshot including live system_memory_percent from psutil."""
        import psutil

        return ResourceSnapshot(
            available_gpu_slots=max(0, self.gpu_slots - self._gpu_in_use),
            available_cpu_workers=max(0, self.max_cpu_workers - self._cpu_in_use),
            system_memory_percent=psutil.virtual_memory().percent / 100.0,
        )
