"""Minimal ProcessBlock example: invert image intensities.

This block demonstrates the Tier 1 pattern -- override process_item()
and let the framework handle iteration, auto-flush, and Collection
packing. Peak memory: O(1 item).

Usage:
    Place this file in ~/.scistudio/blocks/ for Tier 1 discovery,
    or include it in a Tier 2 package.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.array import Array


class InvertImage(ProcessBlock):
    """Invert the intensity of each image in the input Collection.

    For each pixel, computes ``max_value - pixel_value``. Works with
    any numeric dtype. Preserves axes, shape, and user metadata.
    """

    name: ClassVar[str] = "Invert Image"
    description: ClassVar[str] = "Subtract each pixel from the maximum value."
    subcategory: ClassVar[str] = "preprocess"
    algorithm: ClassVar[str] = "invert"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Array], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Array]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
    }

    def process_item(self, item: Array, config: BlockConfig, state: Any = None) -> Array:
        """Invert a single image.

        Args:
            item: Input Array with storage-backed data.
            config: BlockConfig (unused for this block).
            state: Unused (no setup/teardown needed).

        Returns:
            A new Array with inverted intensities.
        """
        # Load data from storage
        data = np.asarray(item.to_memory())

        # Core algorithm
        inverted = data.max() - data

        # Build result with propagated metadata
        result = Array(
            axes=list(item.axes),
            shape=tuple(inverted.shape),
            dtype=str(inverted.dtype),
            framework=item.framework.derive(),
            user=dict(item.user),
        )
        # Transient in-memory data; the framework auto-flushes to zarr
        result._data = inverted  # type: ignore[attr-defined]
        return result
