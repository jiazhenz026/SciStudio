"""A segmentation block: turn a micrograph into a labelled cell map.

Core tutorial 2 writes this block into the tutorial project. It is ordinary
SciStudio block code — a ``ProcessBlock`` under ``blocks/`` — and every line of
the science is real: a global threshold (or a local adaptive one) picks the
foreground, and a hand-written flood fill gives each connected patch its own
integer label. No scikit-image, no scipy; NumPy and patience.

Both methods genuinely run, and neither is perfect on the tutorial image —
which is the lesson. ``threshold`` finds the six cells and also a nine-pixel
debris speck. ``adaptive`` chases *local* contrast, and on an image that is
mostly background that promotes every noise grain to an object of its own.
Imperfection here is not staged; it is what segmentation is like.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
from image import Image

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock

# The adaptive method's fixed shape: the local mean is taken over a
# (2 * radius + 1)-pixel square, and a pixel must beat it by ``offset`` grey
# levels to count as foreground.
ADAPTIVE_RADIUS = 7
ADAPTIVE_OFFSET = 8.0


def _local_mean(pixels: np.ndarray, radius: int) -> np.ndarray:
    """The mean of the square neighbourhood around every pixel, via an integral image."""
    padded = np.pad(pixels, radius + 1, mode="edge")
    integral = padded.cumsum(axis=0).cumsum(axis=1)
    size = 2 * radius + 1
    height, width = pixels.shape
    total = (
        integral[size : size + height, size : size + width]
        - integral[0:height, size : size + width]
        - integral[size : size + height, 0:width]
        + integral[0:height, 0:width]
    )
    return total / float(size * size)


def _label_connected(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Give every 4-connected patch of True pixels its own integer label.

    A plain flood fill with an explicit stack: labels are handed out in scan
    order (top-to-bottom, left-to-right), starting at 1; 0 is background.
    """
    labels = np.zeros(mask.shape, dtype=np.int32)
    height, width = mask.shape
    current = 0
    for seed_y, seed_x in zip(*np.nonzero(mask), strict=True):
        if labels[seed_y, seed_x]:
            continue
        current += 1
        labels[seed_y, seed_x] = current
        stack = [(int(seed_y), int(seed_x))]
        while stack:
            y, x = stack.pop()
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not labels[ny, nx]:
                    labels[ny, nx] = current
                    stack.append((ny, nx))
    return labels, current


class SegmentCellsBlock(ProcessBlock):
    """Threshold a micrograph and label each connected foreground patch.

    Input: one ``Image``. Output: one ``Image`` of the same size whose pixel
    values are object labels — 0 for background, 1..N for the N objects found.
    """

    name: ClassVar[str] = "Segment Cells"
    type_name: ClassVar[str] = "segment_cells"
    description: ClassVar[str] = "Threshold a micrograph and label connected cells."
    algorithm: ClassVar[str] = "threshold_flood_fill_labelling"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], description="The micrograph to segment"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="labels", accepted_types=[Image], description="Label map: 0 background, 1..N objects"),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["threshold", "adaptive"],
                "default": "threshold",
                "title": "Method",
                "description": "threshold: one global cut-off. adaptive: each pixel against its local mean.",
            },
            "threshold": {
                "type": "number",
                "default": 70,
                "title": "Threshold",
                "description": "Pixels brighter than this are foreground (threshold method only).",
            },
        },
        "required": [],
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        """Segment one micrograph into a label map.

        Args:
            item: The micrograph, as an ``Image``.
            config: Supplies ``method`` (default ``threshold``) and, for the
                threshold method, ``threshold`` (default 70).
            state: Unused; part of the ProcessBlock signature.

        Returns:
            An ``Image`` of int32 labels on the same ``y``/``x`` grid.
        """
        pixels = np.asarray(item.to_memory(), dtype=float)
        method = str(config.get("method", "threshold"))
        if method == "adaptive":
            mask = pixels > _local_mean(pixels, ADAPTIVE_RADIUS) + ADAPTIVE_OFFSET
        else:
            mask = pixels > float(config.get("threshold", 70))
        labels, _count = _label_connected(mask)
        return Image(axes=["y", "x"], data=labels)
