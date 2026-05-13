"""Block runner implementations.

ADR-019: New submodules for cross-platform process lifecycle management.
ADR-017: LocalRunner + worker.py for subprocess-based block execution.
"""

from scieasy.engine.runners.local import LocalRunner
from scieasy.engine.runners.platform import PlatformOps, get_platform_ops
from scieasy.engine.runners.process_handle import (
    ProcessExitInfo,
    ProcessHandle,
    ProcessRegistry,
    spawn_block_process,
)
from scieasy.engine.runners.process_monitor import ProcessMonitor
from scieasy.engine.runners.terminal_state import BlockTerminalStateReportedError

__all__ = [
    "BlockTerminalStateReportedError",
    "LocalRunner",
    "PlatformOps",
    "ProcessExitInfo",
    "ProcessHandle",
    "ProcessMonitor",
    "ProcessRegistry",
    "get_platform_ops",
    "spawn_block_process",
]
