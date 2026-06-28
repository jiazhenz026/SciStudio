"""BlockState (internal), ExecutionMode (public) enums."""

from __future__ import annotations

from enum import Enum

from scistudio.stability import stable


class BlockState(Enum):
    """Lifecycle state of a block instance.

    Internal (ADR-052 §4.4): the engine-owned scheduler is the authoritative
    state machine (ADR-018); block authors never set this. Not part of the
    public ``scistudio.blocks.base`` surface.
    """

    IDLE = "idle"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"  # ADR-018: user explicitly terminated this block
    SKIPPED = "skipped"  # ADR-018: block cannot execute — required upstream inputs missing


@stable(since="0.3.1")
class ExecutionMode(Enum):
    """How the block is executed by the runtime.

    Authors set ``execution_mode`` on a block class to one of these values
    (ADR-052 §4.4).
    """

    AUTO = "auto"
    INTERACTIVE = "interactive"
    EXTERNAL = "external"


# ADR-020: BatchMode enum REMOVED — engine no longer iterates collections.
# Collection iteration is block-internal (see process_item(), map_items(), parallel_map()).


# ADR-020: InputDelivery enum REMOVED — CodeBlock uses Collection auto-unpack
# only (LazyList for length>1, to_memory() for length=1). PROXY and CHUNKED
# delivery modes superseded by ProcessBlock for framework-aware code.

# ADR-020: BatchErrorStrategy enum REMOVED — block authors handle item-level
# errors internally. Engine only sees DONE, ERROR, CANCELLED, SKIPPED.
