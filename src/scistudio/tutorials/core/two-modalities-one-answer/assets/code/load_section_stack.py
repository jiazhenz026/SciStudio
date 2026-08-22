# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/tutorials/core/']`, which the
# CI-side run honours but the pre-commit hook (explicit file list) does not
# (#2115): this file ships as project *data* the reader opens and edits, and it
# is imported by the product's drop-in scan, never by the package.
"""Read the scanner's section stack: one file, one Image per section.

Core tutorial 3 puts this block in the project at bootstrap, because it is not
this level's lesson — tutorial 2 already taught what an IO block is and why a
type without a capability cannot be loaded. What ships here is the reader for
*this dataset's* instrument, the way a facility hands you its export format
along with the export.

Two things about it are worth the reader's time, and both are true of the
product rather than of this file:

**One file can hold several data objects.** A TIFF may carry more than one
page, and this loader turns each page into its own :class:`Image` and hands
back a :class:`~scistudio.core.types.collection.Collection` of them. Every
downstream block then runs once per section without anyone writing a loop —
that is what a Collection is for.

**An item carries its own name.** The scanner writes each slide's label into
the page's ``PageName`` tag, and this loader copies it to
``user["display_name"]``, the product's canonical presentation override. That
one line is why the Pair Editor's two lists read ``S05`` / ``S09`` / ``S01``
instead of three identical filenames — an interactive panel can only show you
what the producing block bothered to name.

The TIFF reading itself is the same narrow, standard-library contract tutorial
2's loader used — a byte-order mark, a chain of tag directories, uncompressed
8-bit strips — extended by the one thing that loader refused by name: the
second page, and the third.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
from image import Image

from scistudio.blocks.base import OutputPort
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.io import FormatCapability, IOBlock
from scistudio.core.types.collection import Collection

# The TIFF tags this reader needs, by their numbers in the TIFF 6.0 spec.
# ``PAGE_NAME`` (285) is the standard place a scanner records what a page is.
_WIDTH, _HEIGHT, _BITS, _COMPRESSION, _PAGE_NAME, _STRIP_OFFSETS, _SAMPLES, _STRIP_COUNTS = (
    256,
    257,
    258,
    259,
    285,
    273,
    277,
    279,
)

# TIFF field types this reader can decode: BYTE, ASCII, SHORT, LONG.
_FIELD_FORMATS = {1: "B", 2: "s", 3: "H", 4: "I"}
_FIELD_SIZES = {1: 1, 2: 1, 3: 2, 4: 4}


def _read_ifd(data: bytes, order: str, offset: int) -> tuple[dict[int, Any], int]:
    """Read one image file directory: its tags, and where the next one starts."""
    (entry_count,) = struct.unpack_from(order + "H", data, offset)
    tags: dict[int, Any] = {}
    for index in range(entry_count):
        entry_offset = offset + 2 + 12 * index
        tag, field_type, count = struct.unpack_from(order + "HHI", data, entry_offset)
        item = _FIELD_FORMATS.get(field_type)
        if item is None:
            continue  # a field type (rationals, floats) nothing below asks for
        size = _FIELD_SIZES[field_type] * count
        values_at = entry_offset + 8 if size <= 4 else struct.unpack_from(order + "I", data, entry_offset + 8)[0]
        if field_type == 2:
            raw = struct.unpack_from(order + f"{count}s", data, values_at)[0]
            tags[tag] = raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")
        else:
            tags[tag] = struct.unpack_from(order + item * count, data, values_at)
    (next_ifd,) = struct.unpack_from(order + "I", data, offset + 2 + 12 * entry_count)
    return tags, int(next_ifd)


def _read_page(data: bytes, order: str, tags: dict[int, Any], name: str) -> np.ndarray:
    """Decode one page's pixels, refusing by name anything outside the contract."""
    if tags.get(_COMPRESSION, (1,))[0] != 1:
        raise ValueError(f"page {name!r} is compressed; this loader reads uncompressed TIFF only.")
    if set(tags.get(_BITS, (1,))) != {8} or tags.get(_SAMPLES, (1,))[0] != 1:
        raise ValueError(f"page {name!r} is not 8-bit single-channel grayscale.")
    width = int(tags[_WIDTH][0])
    height = int(tags[_HEIGHT][0])
    strips = b"".join(
        data[offset : offset + count] for offset, count in zip(tags[_STRIP_OFFSETS], tags[_STRIP_COUNTS], strict=True)
    )
    return np.frombuffer(strips, dtype=np.uint8).reshape(height, width)


def read_section_stack(path: Path) -> list[tuple[str, np.ndarray]]:
    """Read every page of a multi-page baseline TIFF as ``(label, pixels)``.

    Pages come back in the order the file stores them — acquisition order, for
    a scanner — which is not necessarily the order anything else uses.
    """
    data = path.read_bytes()
    if len(data) < 8 or data[:2] not in (b"II", b"MM"):
        raise ValueError(f"{path.name} is not a TIFF file (no II/MM byte-order mark).")
    order = "<" if data[:2] == b"II" else ">"
    magic, ifd_offset = struct.unpack_from(order + "HI", data, 2)
    if magic != 42:
        raise ValueError(f"{path.name} is not a classic TIFF file (magic {magic}, expected 42).")

    pages: list[tuple[str, np.ndarray]] = []
    while ifd_offset:
        tags, ifd_offset = _read_ifd(data, order, ifd_offset)
        label = str(tags.get(_PAGE_NAME) or f"page_{len(pages) + 1}")
        pages.append((label, _read_page(data, order, tags, label)))
    if not pages:
        raise ValueError(f"{path.name} holds no image pages.")
    return pages


class LoadSectionStack(IOBlock):
    """Load a multi-page section stack as a Collection of ``Image`` objects."""

    direction: ClassVar[str] = "input"
    name: ClassVar[str] = "Load Section Stack"
    type_name: ClassVar[str] = "load_section_stack"
    description: ClassVar[str] = "Read a multi-page TIFF section stack into one Image per section."
    subcategory: ClassVar[str] = "io"

    # Declared rather than synthesized, because this capability needs two things
    # SimpleLoader does not offer: a Collection result, and a priority. The
    # priority only matters if some other block also claims (Image, .tif) — then
    # the registry picks the more specific reader instead of refusing both as
    # ambiguous, which would strand a reader mid-tutorial.
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id="tutorial.image.tiff_stack.load",
            direction="load",
            data_type=Image,
            format_id="tiff_stack",
            extensions=(".tif", ".tiff"),
            label="TIFF section stack",
            block_type="LoadSectionStack",
            handler="load",
            priority=10,
        ),
    )

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[Image], description="One Image per section in the stack"),
    ]

    def load(self, config: BlockConfig, output_dir: str = "") -> Collection:
        """Read the configured stack and return one ``Image`` per page.

        Args:
            config: The block config; reads ``path``.
            output_dir: Unused — an Array-backed type persists itself.

        Returns:
            A ``Collection`` of ``Image`` objects, in the file's page order,
            each named by its page label.
        """
        raw = config.get("path")
        if raw is None:
            raise ValueError("Load Section Stack requires a 'path' config field")
        pages = read_section_stack(Path(str(raw)))
        return Collection(
            [Image(axes=["y", "x"], data=pixels, user={"display_name": label}) for label, pixels in pages]
        )

    def save(self, obj: Any, config: BlockConfig) -> None:
        """Always raises — this block reads stacks, it does not write them.

        ``IOBlock`` declares both directions abstract, and ``direction="input"``
        is what tells the framework only :meth:`load` is ever called.
        """
        raise TypeError("Load Section Stack is a loader and does not implement save().")
