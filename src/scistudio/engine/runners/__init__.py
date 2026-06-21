"""Block runner implementations.

ADR-019: New submodules for cross-platform process lifecycle management.
ADR-017: LocalRunner + worker.py for subprocess-based block execution.
"""

from scistudio.engine.runners.local import LocalRunner
from scistudio.engine.runners.platform import PlatformOps, get_platform_ops
from scistudio.engine.runners.process_handle import (
    ProcessExitInfo,
    ProcessHandle,
    ProcessRegistry,
    spawn_block_process,
)
from scistudio.engine.runners.terminal_state import BlockTerminalStateReportedError

__all__ = [
    "BlockTerminalStateReportedError",
    "LocalRunner",
    "PlatformOps",
    "ProcessExitInfo",
    "ProcessHandle",
    "ProcessRegistry",
    "get_platform_ops",
    "spawn_block_process",
]
