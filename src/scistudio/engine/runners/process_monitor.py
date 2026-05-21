"""ProcessMonitor — background coroutine polling for unexpected process exits.

ADR-019: Polls active ProcessHandles every 1 second. Detects crashes, OOM kills,
and external termination. Emits PROCESS_EXITED events via EventBus.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ProcessMonitor:
    """Background asyncio coroutine that watches for unexpected process death.

    Design:
        - Runs as asyncio.Task in the engine event loop.
        - Every 1 second, iterates all active ProcessHandles in ProcessRegistry.
        - For each handle, calls handle.is_alive().
        - If process has exited unexpectedly:
            1. Retrieve exit_info from handle.
            2. Emit PROCESS_EXITED event with ProcessExitInfo details.
            3. Subscribers (DAGScheduler, ResourceManager) react via EventBus.
        - Detects: crashes, OOM kills, user killing via OS task manager.

    Lifecycle:
        start(event_bus, registry) -- create and start the background task.
        stop() -- cancel the background task.
    """

    def __init__(self) -> None:
        self._event_bus: Any | None = None
        self._registry: Any | None = None
        self._task: asyncio.Task[None] | None = None
        self._running: bool = False

    async def start(self, event_bus: Any, registry: Any) -> None:
        """Start the background polling coroutine.

        Parameters
        ----------
        event_bus:
            EventBus instance for emitting PROCESS_EXITED events.
        registry:
            ProcessRegistry instance to query for active handles.
        """
        self._event_bus = event_bus
        self._registry = registry
        self._running = True
        self._task = asyncio.ensure_future(self._poll_loop())

    async def stop(self) -> None:
        """Stop the background polling coroutine."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _poll_loop(self) -> None:
        """Poll all active handles at 1-second intervals.

        For each handle in registry.active_handles():
            if not handle.is_alive():
                info = handle.exit_info()
                emit PROCESS_EXITED event with info
                registry.deregister(handle.block_id)
        """
        from scistudio.engine.events import PROCESS_EXITED, EngineEvent

        while self._running:
            await asyncio.sleep(1.0)
            if self._registry is None:
                continue
            for handle in list(self._registry.active_handles()):
                try:
                    alive = handle.is_alive()
                    if not alive:
                        info = handle.exit_info()
                        if self._event_bus is not None:
                            await self._event_bus.emit(
                                EngineEvent(
                                    event_type=PROCESS_EXITED,
                                    block_id=handle.block_id,
                                    data={"exit_info": info},
                                )
                            )
                        self._registry.deregister(handle.block_id)
                except Exception:
                    logger.exception(
                        "ProcessMonitor: error checking handle for block %s",
                        handle.block_id,
                    )
