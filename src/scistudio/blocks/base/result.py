"""BlockResult and BatchResult — execution outcome containers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BlockResult:
    """Outcome of a single block execution.

    Internal (ADR-052 §4.6): the engine's execution-outcome container; block
    authors return ``dict[str, Collection]`` from :meth:`Block.run`. Not part of
    the public ``scistudio.blocks.base`` surface.
    """

    outputs: dict[str, Any]
    duration_ms: int = 0
    error: Exception | None = None


# ADR-020: BatchResult REMOVED — engine no longer performs batch iteration.
# Collection iteration is block-internal. Blocks handle item-level errors
# themselves (see process_item(), map_items(), parallel_map() on Block).
