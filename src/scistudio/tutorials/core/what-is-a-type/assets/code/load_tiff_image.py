"""An IOBlock that teaches SciStudio to read a TIFF file as an ``Image``.

Core tutorial 2 writes this block into the tutorial project after you have met
the real error it exists to fix: ``Load: no load capability is registered for
type 'Image'``. A data type is a name and a shape; *reading a file into it* is
a separate skill, and IO blocks are where that skill lives.

The interesting part is not the reading — ``tifffile`` does that in one line —
but the declaration. ``SimpleLoader`` turns the three class attributes below
(``output_type``, ``format_id``, ``extensions``) into a **format capability**:
a registered statement that *this block can load an Image from a .tif file*.
The Load block on your canvas never changes; when you press Run it asks the
registry for a capability matching (Image, .tif), and from the moment this
file lands, there is one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import tifffile
from image import Image

from scistudio.blocks.base import OutputPort
from scistudio.blocks.io import SimpleLoader


class LoadTiffImage(SimpleLoader):
    """Read one TIFF micrograph from disk and hand it on as an ``Image``."""

    name: ClassVar[str] = "Load TIFF Image"
    type_name: ClassVar[str] = "load_tiff_image"
    description: ClassVar[str] = "Read a .tif/.tiff micrograph into this project's Image type."

    # The three attributes SimpleLoader turns into a load capability.
    output_type: ClassVar[type[Image]] = Image
    format_id: ClassVar[str] = "tiff"
    extensions: ClassVar[tuple[str, ...]] = (".tif", ".tiff")

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[Image], description="The loaded micrograph"),
    ]

    def load_file(self, path: Path, config: dict[str, Any]) -> Image:
        """Read *path* with tifffile and wrap the pixels in an ``Image``.

        Args:
            path: The file the Load block was pointed at.
            config: The block's config params (unused here).

        Returns:
            An :class:`Image` carrying the pixel grid on ``y`` and ``x`` axes.
        """
        pixels = np.asarray(tifffile.imread(path))
        if pixels.ndim != 2:
            raise ValueError(f"expected a single 2-D plane, got shape {pixels.shape} — this tutorial keeps it simple.")
        return Image(axes=["y", "x"], data=pixels)
