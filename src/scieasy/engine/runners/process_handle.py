"""ProcessHandle, ProcessExitInfo, ProcessRegistry, spawn_block_process.

ADR-019: Unified abstraction for OS process management across platforms.
ADR-017: spawn_block_process() is the single entry point for ALL subprocess creation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from scieasy.engine.runners.platform import PlatformOps, get_platform_ops

logger = logging.getLogger(__name__)


@dataclass
class ProcessExitInfo:
    """Exit state of a terminated subprocess.

    Populated by PlatformOps when process exits (ADR-019).
    """

    exit_code: int | None = None
    signal_number: int | None = None  # Unix only, None on Windows
    was_killed_by_framework: bool = False
    platform_detail: str = ""


class ProcessHandle:
    """Per-process wrapper tracking lifecycle of a block subprocess.

    Delegates all OS-specific operations to the PlatformOps instance
    obtained at construction time (ADR-019).

    Attributes:
        block_id: Which block owns this process.
        pid: OS process ID.
        start_time: When the process was spawned.
        resource_request: What resources were allocated.
        was_killed_by_framework: Set to True when terminate/kill is called.
    """

    def __init__(
        self,
        block_id: str,
        pid: int,
        start_time: datetime,
        resource_request: Any,
    ) -> None:
        self.block_id = block_id
        self.pid = pid
        self.start_time = start_time
        self.resource_request = resource_request
        self.was_killed_by_framework = False
        self._platform_ops: PlatformOps = get_platform_ops()
        self._popen: subprocess.Popen[bytes] | None = None
        self._stdin_payload: bytes | None = None

    def is_alive(self) -> bool:
        """Non-blocking alive check.

        Delegates to PlatformOps.is_alive(self.pid).
        """
        return self._platform_ops.is_alive(self.pid)

    def exit_info(self) -> ProcessExitInfo | None:
        """Return ProcessExitInfo if process has exited, None if still alive.

        Delegates to PlatformOps.get_exit_info(self.pid).
        """
        return self._platform_ops.get_exit_info(self.pid)

    def terminate(self, grace_period_sec: float = 5.0) -> ProcessExitInfo:
        """Graceful then forced kill.

        Sends SIGTERM (Unix) or begins graceful shutdown (Windows).
        Waits grace_period_sec. If still alive, escalates to kill.
        """
        self.was_killed_by_framework = True
        info: ProcessExitInfo = self._platform_ops.terminate_tree(self.pid, grace_period_sec)
        info.was_killed_by_framework = True
        return info

    def kill(self) -> ProcessExitInfo:
        """Immediate forced termination.

        Delegates to PlatformOps.kill_tree(self.pid).
        """
        self.was_killed_by_framework = True
        info: ProcessExitInfo = self._platform_ops.kill_tree(self.pid)
        info.was_killed_by_framework = True
        return info


class ProcessRegistry:
    """Tracks all active block subprocesses (ADR-019).

    Simple dict-based registry mapping block_id to ProcessHandle.
    """

    def __init__(self) -> None:
        self._handles: dict[str, ProcessHandle] = {}

    def register(self, handle: ProcessHandle) -> None:
        """Register a newly spawned process."""
        self._handles[handle.block_id] = handle

    def deregister(self, block_id: str) -> None:
        """Remove a process after it has exited."""
        self._handles.pop(block_id, None)

    def get_handle(self, block_id: str) -> ProcessHandle | None:
        """Look up the handle for a block."""
        return self._handles.get(block_id)

    def active_handles(self) -> list[ProcessHandle]:
        """Return all currently active process handles."""
        return list(self._handles.values())

    def terminate_all(self, grace_period_sec: float = 5.0) -> None:
        """Terminate all active processes (engine shutdown).

        Iterates all active handles and calls terminate() on each.
        Handles that fail to terminate are logged but do not prevent
        other handles from being terminated.
        """
        for handle in list(self._handles.values()):
            try:
                handle.terminate(grace_period_sec)
            except Exception:
                logger.exception(
                    "Failed to terminate process for block %s (pid=%d)",
                    handle.block_id,
                    handle.pid,
                )


def build_worker_payload(
    block_class: Any,
    inputs_refs: dict[str, Any],
    config: dict[str, Any],
    output_dir: str | None = None,
    block_file_path: str | None = None,
) -> bytes:
    """Build the JSON payload sent to the worker subprocess via stdin.

    Extracted from spawn_block_process() so that LocalRunner can use
    ``asyncio.create_subprocess_exec`` while reusing the same serialization
    logic (#483).

    Parameters
    ----------
    block_file_path:
        Optional absolute path to the ``.py`` file that defines the block
        class. Used for Tier-1 drop-in blocks whose module name only exists
        in the parent process's ``sys.modules`` (see #706). When provided,
        the worker reloads the module via
        ``importlib.util.spec_from_file_location`` before resolving the
        class. When ``None`` (Tier-2 entry-point blocks / builtins), the
        worker uses the standard ``importlib.import_module`` path.
    """
    if isinstance(block_class, str):
        block_class_path = block_class
    else:
        block_class_path = f"{block_class.__module__}.{block_class.__qualname__}"

    payload_dict: dict[str, Any] = {
        "block_class": block_class_path,
        "inputs": inputs_refs,
        "config": config,
        "output_dir": output_dir,
    }
    # #706: only include block_file_path when present, to keep the payload
    # schema unchanged for the common Tier-2 / builtin case.
    if block_file_path is not None:
        payload_dict["block_file_path"] = block_file_path

    payload = json.dumps(payload_dict)
    return payload.encode("utf-8")


def register_async_process(
    pid: int | None,
    block_id: str,
    registry: ProcessRegistry,
    event_bus: Any | None = None,
    resource_request: Any | None = None,
) -> ProcessHandle:
    """Create and register a ProcessHandle for an already-launched async subprocess.

    Used by LocalRunner when processes are launched via
    ``asyncio.create_subprocess_exec`` instead of ``subprocess.Popen`` (#483).
    """
    from scieasy.engine.events import PROCESS_SPAWNED, EngineEvent
    from scieasy.engine.resources import ResourceRequest as ResReq

    rr = resource_request if resource_request is not None else ResReq()
    handle = ProcessHandle(
        block_id=block_id,
        pid=pid if pid is not None else -1,
        start_time=datetime.now(),
        resource_request=rr,
    )

    registry.register(handle)

    if event_bus is not None:
        _event = EngineEvent(
            event_type=PROCESS_SPAWNED,
            block_id=handle.block_id,
            data={"pid": handle.pid},
        )
        try:
            loop = asyncio.get_running_loop()
            _task = loop.create_task(event_bus.emit(_event))  # noqa: RUF006
        except RuntimeError:
            logger.debug("No running event loop; PROCESS_SPAWNED event not emitted")

    return handle


def spawn_block_process(
    block_class: Any,
    inputs_refs: dict[str, Any],
    config: dict[str, Any],
    event_bus: Any,
    registry: ProcessRegistry,
    block_id: str | None = None,
    resource_request: Any | None = None,
    output_dir: str | None = None,
    job_handle: Any | None = None,
    block_file_path: str | None = None,
) -> ProcessHandle:
    """Single entry point for ALL subprocess creation (ADR-017, ADR-019).

    Steps:
        1. Serialize payload: block class path, StorageReference pointers, config.
        2. Create subprocess via Popen with platform-specific process group.
        3. Create ProcessHandle wrapping the Popen.
        4. Register handle in ProcessRegistry.
        5. Emit PROCESS_SPAWNED event via EventBus.
        6. Return the ProcessHandle.

    The subprocess runs ``scieasy.engine.runners.worker`` as entry point.
    """
    from scieasy.engine.events import PROCESS_SPAWNED, EngineEvent
    from scieasy.engine.resources import ResourceRequest as ResReq

    platform_ops = get_platform_ops()

    # Resolve block class path for serialization
    if isinstance(block_class, str):
        block_class_path = block_class
    else:
        block_class_path = f"{block_class.__module__}.{block_class.__qualname__}"

    # Build payload for the worker subprocess.
    # #706: include block_file_path only when set so the worker can reload
    # Tier-1 drop-in modules whose synthetic name is parent-process-local.
    payload_dict: dict[str, Any] = {
        "block_class": block_class_path,
        "inputs": inputs_refs,
        "config": config,
        "output_dir": output_dir,
    }
    if block_file_path is not None:
        payload_dict["block_file_path"] = block_file_path
    payload = json.dumps(payload_dict)

    # Configure Popen kwargs with platform-specific process group
    popen_kwargs: dict[str, Any] = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    popen_kwargs = platform_ops.create_process_group(popen_kwargs)

    # Launch the worker subprocess
    proc = subprocess.Popen(
        [sys.executable, "-m", "scieasy.engine.runners.worker"],
        **popen_kwargs,
    )

    # Assign to Job Object for nested cleanup (Windows; no-op on POSIX).
    if job_handle is not None:
        platform_ops.assign_to_job(job_handle, proc.pid)

    # Build the ProcessHandle
    rr = resource_request if resource_request is not None else ResReq()
    handle = ProcessHandle(
        block_id=block_id or block_class_path,
        pid=proc.pid,
        start_time=datetime.now(),
        resource_request=rr,
    )
    handle._popen = proc
    handle._platform_ops = platform_ops
    handle._stdin_payload = payload.encode("utf-8")

    # Register in the registry
    registry.register(handle)

    # Emit PROCESS_SPAWNED event.  emit() is async but this function is
    # sync, so schedule the coroutine on the running loop if one exists.
    if event_bus is not None:
        _event = EngineEvent(
            event_type=PROCESS_SPAWNED,
            block_id=handle.block_id,
            data={"pid": proc.pid},
        )
        try:
            loop = asyncio.get_running_loop()
            _task = loop.create_task(event_bus.emit(_event))  # noqa: RUF006
        except RuntimeError:
            logger.debug("No running event loop; PROCESS_SPAWNED event not emitted")

    return handle
