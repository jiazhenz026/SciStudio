"""Public tools for writing blocks that read files in and write files out.

Import everything from this root: ``from scistudio.blocks.io import …``. This is
where you start when you want a custom block that loads a file from disk into a
SciStudio data object, or writes a data object back out to a file.

What this module exports:

- :class:`IOBlock` — the abstract base every load/save block inherits from.
- :class:`SimpleLoader` / :class:`SimpleSaver` — short-cut bases for the common
  "one file in, one object out" (or the reverse) case, so you do not have to
  wire up the full capability machinery by hand.
- :class:`FormatCapability` and :class:`MetadataFidelity` — the records a block
  uses to declare which file formats it can read or write, and how much of the
  file's metadata it preserves.
- The capability-error classes (:class:`CapabilityValidationError` and its
  subclasses) — catch these if you want to handle a rejected format declaration
  yourself.

The concrete ``LoadData`` / ``SaveData`` blocks and the ``normalize_extension``
helpers are internal: they stay importable from their deep module paths for the
framework, but they are not part of this stable surface and may change without
notice.
"""

from __future__ import annotations

from scistudio.blocks.io.capabilities import (
    CapabilityDirection,
    CapabilityValidationError,
    FormatCapability,
    InvalidExtensionError,
    InvalidFormatCapabilityError,
    InvalidMetadataFidelityError,
    MetadataFidelity,
    MetadataFidelityLevel,
    SimpleIODeclarationError,
)
from scistudio.blocks.io.io_block import IOBlock
from scistudio.blocks.io.simple_io import SimpleLoader, SimpleSaver

__all__ = [
    "CapabilityDirection",
    "CapabilityValidationError",
    "FormatCapability",
    "IOBlock",
    "InvalidExtensionError",
    "InvalidFormatCapabilityError",
    "InvalidMetadataFidelityError",
    "MetadataFidelity",
    "MetadataFidelityLevel",
    "SimpleIODeclarationError",
    "SimpleLoader",
    "SimpleSaver",
]
