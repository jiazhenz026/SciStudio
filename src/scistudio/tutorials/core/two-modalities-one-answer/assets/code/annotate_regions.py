# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/tutorials/core/']`, which the
# CI-side run honors but the pre-commit hook (explicit file list) does not
# (#2115): this file ships as project *data* the reader opens and reads.
"""Read each spot's region off the pathologist's mask.

Core tutorial 4 lands this file in the project's ``blocks/`` directory when it
creates the project.

The counts table knows where every spot sits — ``x`` and ``y``, in pixels on
the slide — and what it expressed. The mask knows what each place on the slide
is. Neither knows both. This block is where the two modalities meet: it looks
up the color under each spot on the mask and writes that region's name into
the table. There is no shared identifier and no key column; the two meet
through space alone.

The mask is a picture. Every labeled spot is a disc painted in its region's
color over the slide drained to gray (see ``data/raw/SOURCE.md``). So reading a
region means reading a color:

- a colorful pixel's hue names one of the four colored regions;
- a gray pixel under a spot is Normal tissue, the one region painted in gray.
  The count tables ship labeled spots only, so no spot sits on bare slide.

**Pairing is positional.** Mask *i* is read against table *i*, and nothing
here can check that they are the same tumor: a spot's coordinates land on
*some* pixel of any mask. A wrong pairing does not fail. It labels every spot
from the wrong slide, in a table that looks exactly as trustworthy as the right
one — which is why the Pair Editor sits upstream, where the items still carry
their file names.
"""

from __future__ import annotations

import colorsys
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pyarrow as pa
from he_mask import HEMask

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import DataFrame
from scistudio.core.types.collection import Collection

#: The four colored regions and the color each is painted in, as SOURCE.md
#: lists them. Only the hue matters: the paint is mixed with the gray slide
#: under it, which moves its lightness and saturation but not its hue.
REGION_COLORS = {
    "Invasive cancer": (228, 26, 28),
    "DCIS": (255, 127, 0),
    "Stroma": (55, 126, 184),
    "Lymphocytes": (77, 175, 74),
}

#: The region painted in gray. A gray has no hue to compare, so it is
#: recognized by having almost no saturation instead.
GRAY_REGION = "Normal"
GRAY_SATURATION = 0.15

_HUES = {region: colorsys.rgb_to_hls(*(channel / 255 for channel in rgb))[0] for region, rgb in REGION_COLORS.items()}


def region_of(pixel: np.ndarray) -> str:
    """Name the region whose color *pixel* was painted in."""
    hue, _lightness, saturation = colorsys.rgb_to_hls(*(float(channel) / 255 for channel in pixel[:3]))
    if saturation < GRAY_SATURATION:
        return GRAY_REGION
    # Hue is an angle, so the distance between two hues wraps around.
    return min(_HUES, key=lambda region: min(abs(hue - _HUES[region]), 1 - abs(hue - _HUES[region])))


def tumor_name(table: DataFrame, index: int) -> str:
    """The tumor a count table belongs to, read off the file it was loaded from.

    ``CID4535_counts.csv`` becomes ``CID4535``. A table that did not come from a
    file is named by its position instead.
    """
    source = str(getattr(table.framework, "source", "") or "")
    return Path(source).name.split("_")[0] if source else f"tumor {index + 1}"


def annotate_one(mask: HEMask, table: DataFrame, index: int) -> DataFrame:
    """One tumor's counts, with ``tumor`` and ``region`` columns added."""
    pixels = np.asarray(mask.to_memory())
    frame = table.to_memory().to_pandas()
    ys = frame["y"].to_numpy(dtype=int)
    xs = frame["x"].to_numpy(dtype=int)
    height, width = pixels.shape[:2]
    if (ys < 0).any() or (ys >= height).any() or (xs < 0).any() or (xs >= width).any():
        raise ValueError(
            f"Some spots of {tumor_name(table, index)} fall outside the {width} x {height} mask they were paired "
            "with. Check the pairing."
        )

    name = tumor_name(table, index)
    frame.insert(1, "tumor", name)
    frame.insert(2, "region", [region_of(pixel) for pixel in pixels[ys, xs]])
    return DataFrame(data=pa.Table.from_pandas(frame, preserve_index=False), user={"display_name": name})


class AnnotateRegionsBlock(ProcessBlock):
    """Add each spot's region, read off the mask, to its tumor's count table."""

    name: ClassVar[str] = "Annotate Regions"
    type_name: ClassVar[str] = "annotate_regions"
    description: ClassVar[str] = "Look up the region under every spot on the mask and add it to the counts table."
    algorithm: ClassVar[str] = "mask_color_lookup"
    # Any lucide icon name; it draws this block's node on the canvas and its entry in the palette.
    ui_icon: ClassVar[str] = "tags"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="mask", accepted_types=[HEMask], description="One region mask per tumor"),
        InputPort(name="counts", accepted_types=[DataFrame], description="One spot-by-gene table per tumor"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="annotated", accepted_types=[DataFrame], description="The counts, with tumor and region"),
    ]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        """Annotate every tumor's spots with their regions.

        A ProcessBlock normally walks one input with ``process_item``. This one
        reads two inputs side by side, so it overrides ``run`` and walks them
        together itself.

        Args:
            inputs: ``mask`` and ``counts``, each a Collection with one item per
                tumor, paired by position.
            config: Unused.

        Returns:
            ``{"annotated": Collection([...])}``, one table per tumor.

        Raises:
            ValueError: if the two inputs hold different numbers of tumors.
        """
        masks = _as_items(inputs.get("mask"))
        tables = _as_items(inputs.get("counts"))
        if len(masks) != len(tables):
            raise ValueError(
                f"Annotate Regions received {len(masks)} mask(s) and {len(tables)} count table(s); "
                "pairing is positional, so the counts must match."
            )
        return {
            "annotated": Collection([annotate_one(m, t, i) for i, (m, t) in enumerate(zip(masks, tables, strict=True))])
        }


def _as_items(value: Any) -> list[Any]:
    """Read an input port as a list of items, whether or not it is a Collection."""
    if value is None:
        return []
    return list(value) if isinstance(value, Collection) else [value]
