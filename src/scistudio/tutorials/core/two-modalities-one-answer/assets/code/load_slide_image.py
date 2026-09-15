# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/tutorials/core/']`, which the
# CI-side run honors but the pre-commit hook (explicit file list) does not
# (#2115): this file ships as project *data* the reader opens and edits, and it
# is imported by the product's drop-in scan, never by the package.
"""Read a slide picture — H&E or region mask — as pixels.

SciStudio's Load block already accepts a ``.png``, but it hands back an
:class:`~scistudio.core.types.artifact.Artifact`: the file's bytes, carried and
stored faithfully, and opaque. That is the right default for a format the core
has no opinion about, and it is not enough here — a mask whose colors nobody
can read is a picture, not data.

So this project teaches SciStudio one thing about its own files: that a
``.png`` in *this* project is an :class:`HEImage` or an :class:`HEMask`, a real
pixel array a block can compute on. That is all an IO block is. It declares a
:class:`~scistudio.blocks.io.FormatCapability` — a data type, a format, the
extensions it claims — and the Load block's dispatch does the rest. Nothing
else in the project changes; the same Load node that read the counts table
reads a slide, because the capability is now there to be found.

It reads **one** file, and says so by subclassing
:class:`~scistudio.blocks.io.simple_io.SimpleLoader` and implementing
:meth:`load_file` rather than ``load``. That is what lets a Load node hand it
a list of paths: the core sees a loader that takes files one at a time, calls
it once per path, and collects the results into a
:class:`~scistudio.core.types.collection.Collection` by itself.

The decoding is written out below, with no image library anywhere. SciStudio's
core decodes no image formats — readers for those live in imaging packages —
and a PNG is simple enough to read with the standard library: a signature, a
list of chunks, the pixel rows deflated with ``zlib``, and a one-byte "filter"
in front of each row that says how to predict its bytes from their neighbors.
The pictures this level ships use no filter, so they decode at once. A PNG from
another program usually does, and is decoded too, just more slowly.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
from he_image import HEImage
from he_mask import HEMask

from scistudio.blocks.base import OutputPort
from scistudio.blocks.io import FormatCapability
from scistudio.blocks.io.simple_io import SimpleLoader

#: Every PNG file starts with these eight bytes.
_SIGNATURE = b"\x89PNG\r\n\x1a\n"

#: Bytes per pixel for each 8-bit color type: grayscale, RGB, grayscale with
#: alpha, RGB with alpha. Palette PNGs (type 3) are not read here.
_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}


def _paeth(left: int, above: int, upper_left: int) -> int:
    """The PNG Paeth predictor: whichever neighbor is closest to left + above - upper_left."""
    estimate = left + above - upper_left
    to_left, to_above, to_upper_left = abs(estimate - left), abs(estimate - above), abs(estimate - upper_left)
    if to_left <= to_above and to_left <= to_upper_left:
        return left
    return above if to_above <= to_upper_left else upper_left


def _unfilter(kind: int, line: np.ndarray, previous: np.ndarray, bpp: int) -> np.ndarray:
    """Undo one row's filter. Each filter adds back a prediction from neighbors already decoded.

    None and Up need only the row above, so they work on the whole row at once.
    Sub, Average and Paeth predict from the byte to the left in the *same* row,
    which is known only once it is decoded, so they go byte by byte.
    """
    if kind == 0:  # None
        return line
    if kind == 2:  # Up: the byte above
        return (line + previous) & 0xFF
    raw, above = line.tolist(), previous.tolist()
    current = [0] * len(raw)
    for x, value in enumerate(raw):
        left = current[x - bpp] if x >= bpp else 0
        upper_left = above[x - bpp] if x >= bpp else 0
        if kind == 1:  # Sub: the byte to the left
            prediction = left
        elif kind == 3:  # Average: of left and above
            prediction = (left + above[x]) // 2
        elif kind == 4:
            prediction = _paeth(left, above[x], upper_left)
        else:
            raise ValueError(f"unknown PNG row filter {kind}")
        current[x] = (value + prediction) & 0xFF
    return np.asarray(current, dtype=np.int32)


def read_png(path: Path) -> np.ndarray:
    """Decode an 8-bit, non-interlaced PNG as a ``(y, x, 3)`` array of RGB pixels.

    Grayscale is spread to three equal channels and alpha is dropped, so a
    downstream block can index a pixel's color without first asking what kind
    of picture it came from.
    """
    data = Path(path).read_bytes()
    if not data.startswith(_SIGNATURE):
        raise ValueError(f"{Path(path).name} is not a PNG file")

    header, compressed, position = None, [], len(_SIGNATURE)
    while position < len(data):
        (length,) = struct.unpack(">I", data[position : position + 4])
        kind, body = data[position + 4 : position + 8], data[position + 8 : position + 8 + length]
        position += 12 + length  # length, kind, body, CRC
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            compressed.append(body)
        elif kind == b"IEND":
            break
    if header is None:
        raise ValueError(f"{Path(path).name} has no IHDR chunk")

    width, height, depth, color_type, _compression, _filter_method, interlace = header
    if depth != 8 or color_type not in _CHANNELS or interlace:
        raise ValueError(f"{Path(path).name}: only 8-bit, non-interlaced grayscale or RGB(A) PNGs are read here")
    bpp = _CHANNELS[color_type]

    # Each row is one filter byte followed by width * bpp pixel bytes.
    rows = np.frombuffer(zlib.decompress(b"".join(compressed)), dtype=np.uint8).reshape(height, 1 + width * bpp)
    pixels = np.empty((height, width * bpp), dtype=np.uint8)
    previous = np.zeros(width * bpp, dtype=np.int32)
    for y in range(height):
        previous = _unfilter(int(rows[y, 0]), rows[y, 1:].astype(np.int32), previous, bpp)
        pixels[y] = previous

    picture = pixels.reshape(height, width, bpp)
    if bpp in (1, 2):  # grayscale, with or without alpha
        return np.repeat(picture[..., :1], 3, axis=-1)
    return np.ascontiguousarray(picture[..., :3])


class LoadSlideImage(SimpleLoader):
    """Load a PNG slide picture as an ``HEImage`` or an ``HEMask``."""

    name: ClassVar[str] = "Load Slide Image"
    type_name: ClassVar[str] = "load_slide_image"
    description: ClassVar[str] = "Read a PNG slide picture into an HEImage or HEMask of RGB pixels."
    subcategory: ClassVar[str] = "io"
    # Any lucide icon name; it draws this block's node on the canvas and its entry in the palette.
    ui_icon: ClassVar[str] = "microscope"

    # Declared rather than synthesized: a SimpleLoader builds one capability
    # from output_type/format_id/extensions, and this block claims two — one
    # for each type. The core already claims .png for Artifact; these records
    # claim it for this project's own types, which are different data types and
    # so different capabilities. Dispatch picks by the pair the Load node asks
    # for, so they coexist: ask for an Artifact and you get bytes, ask for an
    # HEImage or an HEMask and you get pixels.
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
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
    )

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[HEImage, HEMask], description="The picture, as RGB pixels"),
    ]

    #: Which class each capability builds. Read off the declarations above so a
    #: capability added there cannot be forgotten here.
    _TYPE_OF: ClassVar[dict[str, type]] = {capability.id: capability.data_type for capability in format_capabilities}

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
        return built(axes=["y", "x", "c"], data=read_png(path), user={"display_name": path.stem})
