"""SimpleThreshold -- ProcessBlock that produces a binary mask.

Demonstrates:
- Output with different type than input
- Config with enum values
- Metadata propagation for derived data
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.array import Array


class SimpleThreshold(ProcessBlock):
    """Apply a threshold to produce a binary mask."""

    name: ClassVar[str] = "Simple Threshold"
    description: ClassVar[str] = "Threshold an image to produce a binary mask."
    subcategory: ClassVar[str] = "segmentation"
    algorithm: ClassVar[str] = "threshold"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Array], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="mask", accepted_types=[Array]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["manual", "otsu"],
                "default": "manual",
                "title": "Threshold method",
            },
            "value": {
                "type": "number",
                "default": 128.0,
                "title": "Manual threshold value",
                "ui_widget": "slider",
            },
        },
    }

    def process_item(self, item: Array, config: BlockConfig, state: Any = None) -> Array:
        """Threshold a single image.

        Args:
            item: Input Array.
            config: BlockConfig with ``method`` and ``value``.
            state: Unused.

        Returns:
            Binary Array (dtype bool) with same spatial axes.
        """
        data = np.asarray(item.to_memory())
        method = str(config.get("method", "manual"))

        if method == "otsu":
            from skimage.filters import threshold_otsu

            thresh = threshold_otsu(data)
        else:
            thresh = float(config.get("value", 128.0))

        mask = data > thresh

        result = Array(
            axes=list(item.axes),
            shape=tuple(mask.shape),
            dtype=str(mask.dtype),
            framework=item.framework.derive(),
            user=dict(item.user),
        )
        result._data = mask  # type: ignore[attr-defined]
        return result
