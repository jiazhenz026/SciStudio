# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/tutorials/core/']`, which the
# CI-side run honors but the pre-commit hook (explicit file list) does not
# (#2115): this file ships as project *data* the reader opens and edits, and it
# is imported by the product's drop-in scan, never by the package.
"""Read a slide picture — H&E or region mask — as pixels.

SciStudio's Load block already accepts a ``.jpg`` or a ``.png``, but it hands
back an :class:`~scistudio.core.types.artifact.Artifact`: the file's bytes,
carried and stored faithfully, and opaque. That is the right default for a
format the core has no opinion about, and it is not enough here — a mask whose
colors nobody can read is a picture, not data.

So this project teaches SciStudio one thing about its own files: that a
``.jpg`` or ``.png`` in *this* project is an :class:`HEImage` or an
:class:`HEMask`, a real pixel array a block can compute on. That is all an IO
block is. It declares a :class:`~scistudio.blocks.io.FormatCapability` — a
data type, a format, the extensions it claims — and the Load block's dispatch
does the rest. Nothing else in the project changes; the same Load node that
read the counts table reads a slide, because the capability is now there to be
found.

It reads **one** file, and says so by subclassing
:class:`~scistudio.blocks.io.simple_io.SimpleLoader` and implementing
:meth:`load_file` rather than ``load``. That is what lets a Load node hand it
a list of paths: the core sees a loader that takes files one at a time, calls
it once per path, and collects the results into a
:class:`~scistudio.core.types.collection.Collection` by itself.

Unlike this project's other readers, the decoding itself is borrowed. JPEG is
a discrete cosine transform, quantization tables and Huffman codes; writing
that by hand would teach nothing about SciStudio. Pillow already does it, and
it is installed wherever SciStudio is, because matplotlib requires it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import numpy as np
from he_image import HEImage
from he_mask import HEMask
from PIL import Image as PILImage

from scistudio.blocks.base import OutputPort
from scistudio.blocks.io import FormatCapability
from scistudio.blocks.io.simple_io import SimpleLoader

#: Pillow decodes to whatever the file holds — palette, grayscale, RGB, RGBA.
#: Everything is converted to plain RGB so a downstream block can index a
#: pixel's color without first asking what kind of picture it came from.
_MODE = "RGB"


def read_slide_image(path: Path) -> np.ndarray:
    """Decode one picture file as an ``(y, x, c)`` array of 8-bit RGB pixels."""
    with PILImage.open(path) as handle:
        return np.asarray(handle.convert(_MODE), dtype=np.uint8)


class LoadSlideImage(SimpleLoader):
    """Load a JPEG or PNG slide picture as an ``HEImage`` or an ``HEMask``."""

    name: ClassVar[str] = "Load Slide Image"
    type_name: ClassVar[str] = "load_slide_image"
    description: ClassVar[str] = "Read a JPEG or PNG slide picture into an HEImage or HEMask of RGB pixels."
    subcategory: ClassVar[str] = "io"

    # Declared rather than synthesized: a SimpleLoader builds one capability
    # from output_type/format_id/extensions, and this block claims four — two
    # types, two formats. The core already claims these extensions for
    # Artifact; these records claim them for this project's own types, which
    # are different data types and so different capabilities. Dispatch picks by
    # the pair the Load node asks for, so they coexist: ask for an Artifact and
    # you get bytes, ask for an HEImage or an HEMask and you get pixels.
    #
    # The slides ship as JPEG and the masks as PNG, but neither type is tied to
    # a format here: which of the two a file becomes is the Load node's
    # ``core_type``, not the file's extension.
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id="tutorial.he_image.jpeg.load",
            direction="load",
            data_type=HEImage,
            format_id="jpeg",
            extensions=(".jpg", ".jpeg"),
            label="JPEG picture",
            block_type="LoadSlideImage",
            handler="load",
            priority=10,
        ),
        FormatCapability(
            id="tutorial.he_image.png.load",
            direction="load",
            data_type=HEImage,
            format_id="png",
            extensions=(".png",),
            label="PNG picture",
            block_type="LoadSlideImage",
            handler="load",
            priority=10,
        ),
        FormatCapability(
            id="tutorial.he_mask.png.load",
            direction="load",
            data_type=HEMask,
            format_id="png",
            extensions=(".png",),
            label="PNG mask",
            block_type="LoadSlideImage",
            handler="load",
            priority=10,
        ),
        FormatCapability(
            id="tutorial.he_mask.jpeg.load",
            direction="load",
            data_type=HEMask,
            format_id="jpeg",
            extensions=(".jpg", ".jpeg"),
            label="JPEG mask",
            block_type="LoadSlideImage",
            handler="load",
            priority=10,
        ),
    )

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[HEImage, HEMask], description="The picture, as RGB pixels"),
    ]

    #: Which class each capability builds. Read off the declarations above so a
    #: capability added there cannot be forgotten here.
    _TYPE_OF: ClassVar[dict[str, type]] = {
        capability.id: capability.data_type for capability in format_capabilities
    }

    def load_file(self, path: Path, config: dict[str, Any]) -> HEImage | HEMask:
        """Read one picture as the type whose capability was selected.

        The Load node's ``core_type`` chose the capability; by the time the
        config reaches here it has been replaced by that capability's id, which
        names the type just as exactly.

        Args:
            path: The picture file to read.
            config: The block's config params as a plain dict.

        Returns:
            An ``HEImage`` or an ``HEMask`` with axes ``y``, ``x`` and ``c``,
            named after the file so the canvas and the Data section show which
            slide this is.
        """
        capability_id = str(config.get("capability_id") or "")
        built = self._TYPE_OF.get(capability_id, HEImage)
        pixels = read_slide_image(path)
        return built(axes=["y", "x", "c"], data=pixels, user={"display_name": path.stem})
