"""Block ABC and core machinery — ports, config, state, results."""

from __future__ import annotations

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.package_info import PackageInfo
from scistudio.blocks.base.ports import (
    InputPort,
    OutputPort,
    Port,
    port_accepts_signature,
    port_accepts_type,
    validate_connection,
    validate_port_constraint,
)
from scistudio.blocks.base.result import BlockResult
from scistudio.blocks.base.state import (
    # ADR-020: BatchErrorStrategy, BatchMode, InputDelivery REMOVED
    BlockState,
    ExecutionMode,
)

__all__ = [
    # ADR-020: "BatchErrorStrategy", "BatchMode", "BatchResult", "InputDelivery" REMOVED
    "Block",
    "BlockConfig",
    "BlockResult",
    "BlockState",
    "ExecutionMode",
    "InputPort",
    "OutputPort",
    "PackageInfo",
    "Port",
    "port_accepts_signature",
    "port_accepts_type",
    "validate_connection",
    "validate_port_constraint",
]
