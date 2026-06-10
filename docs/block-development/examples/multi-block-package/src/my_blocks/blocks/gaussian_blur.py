"""GaussianBlur -- ProcessBlock example with config_schema.

Demonstrates:
- config_schema with ui_widget hints
- process_item with the three-argument signature
- Output Array construction with propagated metadata
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.array import Array


class GaussianBlur(ProcessBlock):
    """Apply Gaussian blur to each image."""

    name: ClassVar[str] = "Gaussian Blur"
    description: ClassVar[str] = "Smooth an image with a Gaussian kernel."
    subcategory: ClassVar[str] = "preprocess"
    algorithm: ClassVar[str] = "gaussian_blur"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Array], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Array]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "sigma": {
                "type": "number",
                "default": 1.0,
                "minimum": 0.1,
                "maximum": 50.0,
                "title": "Sigma (blur radius)",
                "ui_widget": "slider",
            },
        },
    }

    def process_item(self, item: Array, config: BlockConfig, state: Any = None) -> Array:
        """Apply Gaussian blur to a single image.

        Args:
            item: Input Array.
            config: BlockConfig with ``sigma`` parameter.
            state: Unused.

        Returns:
            Blurred Array with same axes and shape.
        """
        from scipy.ndimage import gaussian_filter

        sigma = float(config.get("sigma", 1.0))
        data = np.asarray(item.to_memory())
        blurred = gaussian_filter(data, sigma=sigma)

        return Array(
            axes=list(item.axes),
            shape=tuple(blurred.shape),
            dtype=str(blurred.dtype),
            framework=item.framework.derive(),
            user=dict(item.user),
            data=blurred,
        )
