"""An IOBlock that teaches SciStudio to read a TIFF file as an ``Image``.

Core tutorial 2 writes this block into the tutorial project after you have met
the real error it exists to fix: ``Load: no load capability is registered for
type 'Image'``. That error is honest about the product: core SciStudio ships
no image decoding at all — TIFF readers live in imaging packages — so a type
called Image can exist while nothing knows how to fill one from a file.

Two things happen in this file, and they are the lesson in miniature.

**The declaration.** ``SimpleLoader`` turns the three class attributes below
(``output_type``, ``format_id``, ``extensions``) into a **format capability**:
a registered statement that *this block can load an Image from a .tif file*.
The Load block on your canvas never changes; when you press Run it asks the
registry for a capability matching (Image, .tif), and from the moment this
file lands, there is one.

**The reading.** With no TIFF library to lean on, this block reads the bytes
itself. A baseline TIFF is a small contract — a byte-order mark, one directory
of numbered tags, and strips of pixel data — and the whole contract this
tutorial's micrograph needs fits in :func:`_read_baseline_tiff` below. It
reads exactly what it claims (single-page, uncompressed, 8-bit grayscale) and
refuses everything else by name, which is what a narrow capability should do:
imaging packages ship the readers for the richer TIFF variants.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
from image import Image

from scistudio.blocks.base import OutputPort
from scistudio.blocks.io import SimpleLoader
from scistudio.core.meta.framework import FrameworkMeta

# The TIFF tags this reader needs, by their numbers in the TIFF 6.0 spec.
_WIDTH, _HEIGHT, _BITS, _COMPRESSION, _STRIP_OFFSETS, _SAMPLES, _STRIP_COUNTS = (
    256,
    257,
    258,
    259,
    273,
    277,
    279,
)

# TIFF field types this reader can decode: BYTE, SHORT, LONG.
_FIELD_FORMATS = {1: "B", 3: "H", 4: "I"}
_FIELD_SIZES = {1: 1, 3: 2, 4: 4}


def _read_baseline_tiff(path: Path) -> np.ndarray:
    """Read a single-page, uncompressed, 8-bit grayscale TIFF as a 2-D array.

    Refuses, by name, everything outside that contract rather than guessing.
    """
    data = path.read_bytes()
    if len(data) < 8 or data[:2] not in (b"II", b"MM"):
        raise ValueError(f"{path.name} is not a TIFF file (no II/MM byte-order mark).")
    order = "<" if data[:2] == b"II" else ">"
    magic, ifd_offset = struct.unpack_from(order + "HI", data, 2)
    if magic != 42:
        raise ValueError(f"{path.name} is not a classic TIFF file (magic {magic}, expected 42).")

    (entry_count,) = struct.unpack_from(order + "H", data, ifd_offset)
    tags: dict[int, tuple[int, ...]] = {}
    for index in range(entry_count):
        entry_offset = ifd_offset + 2 + 12 * index
        tag, field_type, count = struct.unpack_from(order + "HHI", data, entry_offset)
        item = _FIELD_FORMATS.get(field_type)
        if item is None:
            continue  # a field type (rationals, ASCII) nothing below asks for
        if _FIELD_SIZES[field_type] * count <= 4:
            values_at = entry_offset + 8
        else:
            (values_at,) = struct.unpack_from(order + "I", data, entry_offset + 8)
        tags[tag] = struct.unpack_from(order + item * count, data, values_at)
    (next_ifd,) = struct.unpack_from(order + "I", data, ifd_offset + 2 + 12 * entry_count)

    if next_ifd != 0:
        raise ValueError(f"{path.name} has more than one page; this loader reads a single 2-D plane.")
    if tags.get(_COMPRESSION, (1,))[0] != 1:
        raise ValueError(f"{path.name} is compressed; this loader reads uncompressed TIFF only.")
    if set(tags.get(_BITS, (1,))) != {8} or tags.get(_SAMPLES, (1,))[0] != 1:
        raise ValueError(f"{path.name} is not 8-bit single-channel grayscale.")

    width = int(tags[_WIDTH][0])
    height = int(tags[_HEIGHT][0])
    strips = b"".join(
        data[offset : offset + count] for offset, count in zip(tags[_STRIP_OFFSETS], tags[_STRIP_COUNTS], strict=True)
    )
    return np.frombuffer(strips, dtype=np.uint8).reshape(height, width)


class LoadTiffImage(SimpleLoader):
    """Read one TIFF micrograph from disk and hand it on as an ``Image``."""

    name: ClassVar[str] = "Load TIFF Image"
    type_name: ClassVar[str] = "load_tiff_image"
    description: ClassVar[str] = "Read a plain .tif/.tiff micrograph into this project's Image type."

    # The three attributes SimpleLoader turns into a load capability.
    output_type: ClassVar[type[Image]] = Image
    format_id: ClassVar[str] = "tiff"
    extensions: ClassVar[tuple[str, ...]] = (".tif", ".tiff")

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[Image], description="The loaded micrograph"),
    ]

    def load_file(self, path: Path, config: dict[str, Any]) -> Image:
        """Read *path* and wrap the pixels in an ``Image``.

        Args:
            path: The file the Load block was pointed at.
            config: The block's config params (unused here).

        Returns:
            An :class:`Image` carrying the pixel grid on ``y`` and ``x`` axes,
            and the file it was read from.

            The source is not decoration. Everything downstream that has to
            *name* this image reads it: the preview panel labels the card with
            it, and the Save block names the file it writes from it. Without it
            an image is identified by its storage reference — ``data-a0fb0`` —
            which tells the reader nothing about which of their micrographs
            they are looking at.
        """
        return Image(
            axes=["y", "x"],
            data=_read_baseline_tiff(path),
            framework=FrameworkMeta(source=str(path)),
        )
