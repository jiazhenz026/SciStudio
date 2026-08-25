"""A segmentation block: turn a micrograph into a labeled cell map.

Core tutorial 2 writes this block into the tutorial project. It is ordinary
SciStudio block code — a ``ProcessBlock`` under ``blocks/`` — and every line of
the science is real: a global threshold (or a local adaptive one) picks the
foreground, and a hand-written flood fill gives each connected patch its own
integer label. No scikit-image, no scipy; NumPy and patience.

Both methods genuinely run, and neither is perfect on the tutorial's
micrographs — which is the lesson. ``threshold`` finds every cell and, on the
first slide, a speck of debris besides. ``adaptive`` chases *local* contrast,
and on an image that is mostly background that promotes every noise grain to
an object of its own.
Imperfection here is not staged; it is what segmentation is like.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
from image import Image

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock

# The adaptive method's fixed shape: the local mean is taken over a
# (2 * radius + 1)-pixel square, and a pixel must beat it by ``offset`` gray
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


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """Close the gaps a threshold leaves inside an object.

    A cell is not uniformly bright. Its nucleus is dimmer than the cytoplasm
    around it and the darker patches between organelles dip below the cut-off
    too, so thresholding a real micrograph returns cells with holes punched
    through them — a ring where there should be a disc, and an area that
    measures the rim rather than the cell.

    The fix does not need morphology. Background that a reader would call
    "outside" is background you can reach from the edge of the image; anything
    else is enclosed, whatever its shape. So this floods the background inward
    from the border and calls everything it could not reach foreground. A
    nucleus becomes part of its cell; the space between two cells, which the
    border flood does reach, stays background.
    """
    height, width = mask.shape
    outside = np.zeros(mask.shape, dtype=bool)
    stack: list[tuple[int, int]] = []
    for y in range(height):
        for x in (0, width - 1):
            if not mask[y, x] and not outside[y, x]:
                outside[y, x] = True
                stack.append((y, x))
    for x in range(width):
        for y in (0, height - 1):
            if not mask[y, x] and not outside[y, x]:
                outside[y, x] = True
                stack.append((y, x))
    while stack:
        y, x = stack.pop()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < height and 0 <= nx < width and not mask[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                stack.append((ny, nx))
    return mask | ~outside


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


def _drop_small(labels: np.ndarray, count: int, min_area: int) -> tuple[np.ndarray, int]:
    """Renumber the label map, keeping only objects of at least *min_area* pixels.

    A camera delivers noise, and every pixel of it that clears the threshold is
    its own connected patch: on a real micrograph this block finds a couple of
    hundred objects, of which a handful are cells and the rest are one or two
    pixels of sensor grain. Dropping them is not a refinement of the method, it
    is part of it — a size below which a bright patch is not a cell is exactly
    the kind of knowledge a segmentation carries.

    The survivors are renumbered 1..N with no gaps, so a label id is still a
    position in the list of objects found.
    """
    if min_area <= 1:
        return labels, count
    kept = np.zeros_like(labels)
    surviving = 0
    for label in range(1, count + 1):
        patch = labels == label
        if int(patch.sum()) >= min_area:
            surviving += 1
            kept[patch] = surviving
    return kept, surviving


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
        OutputPort(
            name="labels",
            accepted_types=[Image],
            description="Two channels on one grid: c=0 the micrograph, c=1 the label map (0 background, 1..N objects)",
        ),
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
            "min_area": {
                "type": "integer",
                "default": 60,
                "title": "Minimum area",
                "description": "Objects smaller than this many pixels are sensor noise, not cells.",
            },
        },
        "required": [],
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        """Segment one micrograph into a label map.

        Args:
            item: The micrograph, as an ``Image``.
            config: Supplies ``method`` (default ``threshold``), the
                ``threshold`` the threshold method cuts at (default 70), and
                ``min_area``, the pixel count below which a bright patch is
                sensor noise rather than a cell (default 60).
            state: Unused; part of the ProcessBlock signature.

        Returns:
            A two-channel ``Image`` on the same ``y``/``x`` grid: ``c=0`` is the
            micrograph this read, ``c=1`` is the int32 label map.

            The picture the reader looks at is the labels *over* the cells they
            came from — a label map on its own is a field of coloured blobs
            with nothing to check them against. A previewer only ever sees the
            one object it was handed, so carrying the micrograph along as a
            second channel is what lets one be drawn on top of the other. An
            Array subclass may name a ``c`` axis for exactly this
            (``scistudio.core.types.array``), so this needs no new type and no
            second output port.
        """
        pixels = np.asarray(item.to_memory(), dtype=float)
        if pixels.ndim == 3:
            # A two-channel input is this block's own output fed back in; the
            # micrograph is the first channel.
            pixels = pixels[0]
        method = str(config.get("method", "threshold"))
        if method == "adaptive":
            mask = pixels > _local_mean(pixels, ADAPTIVE_RADIUS) + ADAPTIVE_OFFSET
        else:
            mask = pixels > float(config.get("threshold", 70))
        labels, count = _label_connected(_fill_holes(mask))
        labels, _kept = _drop_small(labels, count, int(config.get("min_area", 60)))
        # int32 for both channels because the array holds one dtype and the
        # labels are ids, not intensities: a uint8 grid would silently wrap at
        # 255 objects, which the adaptive method can reach.
        stacked = np.stack([pixels.astype(np.int32), labels.astype(np.int32)])
        # The micrograph's own provenance travels with its segmentation, so the
        # preview card for the labels is still named after the slide they were
        # found in rather than after a storage reference.
        return Image(axes=["c", "y", "x"], data=stacked, framework=item.framework)
