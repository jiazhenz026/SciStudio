"""Runtime-global host-safety admission for block execution.

ADR-022 Addendum 1 deliberately keeps local scheduling resource-agnostic.
Blocks choose their own CPU, accelerator, batching, and internal parallelism
behavior. The engine only bounds automatic subprocess fan-out and delays new
work while live host-memory pressure is unsafe.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class AdmissionWaitReason(StrEnum):
    """Machine-readable reason that a READY block could not acquire a permit."""

    CONCURRENCY_LIMIT = "concurrency_limit"
    MEMORY_PRESSURE_HIGH = "memory_pressure_high"
    MEMORY_PRESSURE_CRITICAL = "memory_pressure_critical"


class ResourcePermit:
    """Opaque proof that one block execution was admitted.

    Identity, rather than a block id, distinguishes executions so same-named
    nodes in concurrent workflows cannot release each other's capacity.
    """

    __slots__ = ("_manager_marker",)

    def __init__(self, manager_marker: object) -> None:
        self._manager_marker = manager_marker


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    """Result of one atomic host-safety admission attempt."""

    permit: ResourcePermit | None = None
    wait_reason: AdmissionWaitReason | None = None

    @property
    def admitted(self) -> bool:
        """Return whether the caller owns a permit."""
        return self.permit is not None


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    """Read-only diagnostics for the host-safety boundary."""

    active_blocks: int = 0
    max_concurrent_blocks: int = 255
    system_memory_percent: float = 0.0

    @property
    def available_concurrency_permits(self) -> int:
        """Return unclaimed block-execution permits."""
        return max(0, self.max_concurrent_blocks - self.active_blocks)


class ResourceManager:
    """Atomically admit block executions using concurrency and memory guards.

    One instance is owned by a runtime and shared by every scheduler created by
    that runtime. The default limit of 255 is a runaway process-launch guard,
    not a promise of CPU, GPU, memory, or performance isolation.
    """

    def __init__(
        self,
        max_concurrent_blocks: int = 255,
        memory_high_watermark: float = 0.90,
        memory_critical: float = 0.95,
    ) -> None:
        if (
            isinstance(max_concurrent_blocks, bool)
            or not isinstance(max_concurrent_blocks, int)
            or max_concurrent_blocks <= 0
        ):
            raise ValueError("max_concurrent_blocks must be a positive integer")
        if not 0.0 <= memory_high_watermark < memory_critical <= 1.0:
            raise ValueError("memory watermarks must satisfy 0 <= high < critical <= 1")

        self.max_concurrent_blocks = max_concurrent_blocks
        self.memory_high_watermark = memory_high_watermark
        self.memory_critical = memory_critical
        self._manager_marker = object()
        self._active_permits: set[ResourcePermit] = set()
        self._release_listeners: set[Callable[[], None]] = set()
        self._lock = threading.Lock()

    def subscribe_release(self, listener: Callable[[], None]) -> None:
        """Register a scheduler wakeup callback for successful releases."""
        with self._lock:
            self._release_listeners.add(listener)

    def unsubscribe_release(self, listener: Callable[[], None]) -> None:
        """Remove a previously registered release callback."""
        with self._lock:
            self._release_listeners.discard(listener)

    def try_acquire(self) -> AdmissionDecision:
        """Atomically inspect live memory and claim one execution permit.

        The critical watermark always blocks. Above the high watermark, one
        block may start only when the runtime is otherwise idle, preventing a
        high-baseline-memory deadlock while avoiding additional fan-out.
        """
        import psutil

        with self._lock:
            memory_percent = psutil.virtual_memory().percent / 100.0
            active_blocks = len(self._active_permits)

            if memory_percent >= self.memory_critical:
                return AdmissionDecision(wait_reason=AdmissionWaitReason.MEMORY_PRESSURE_CRITICAL)
            if memory_percent > self.memory_high_watermark and active_blocks > 0:
                return AdmissionDecision(wait_reason=AdmissionWaitReason.MEMORY_PRESSURE_HIGH)
            if active_blocks >= self.max_concurrent_blocks:
                return AdmissionDecision(wait_reason=AdmissionWaitReason.CONCURRENCY_LIMIT)

            permit = ResourcePermit(self._manager_marker)
            self._active_permits.add(permit)
            return AdmissionDecision(permit=permit)

    def release(self, permit: ResourcePermit) -> bool:
        """Release *permit* once; return whether this call released capacity.

        Repeated release and permits from another manager are harmless. This
        makes terminal-event and task-finally cleanup safe to overlap.
        """
        with self._lock:
            if permit._manager_marker is not self._manager_marker:
                return False
            if permit not in self._active_permits:
                return False
            self._active_permits.remove(permit)
            listeners = tuple(self._release_listeners)
        for listener in listeners:
            try:
                listener()
            except Exception:
                logger.exception("Resource permit release listener failed")
        return True

    @property
    def available(self) -> ResourceSnapshot:
        """Return current host-safety diagnostics without CPU/GPU claims."""
        import psutil

        with self._lock:
            active_blocks = len(self._active_permits)
        return ResourceSnapshot(
            active_blocks=active_blocks,
            max_concurrent_blocks=self.max_concurrent_blocks,
            system_memory_percent=psutil.virtual_memory().percent / 100.0,
        )
