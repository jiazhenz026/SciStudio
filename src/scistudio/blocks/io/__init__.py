"""IO blocks — abstract base + core dynamic-port concrete loaders/savers.

The :class:`IOBlock` ABC (post-T-TRK-004) is the base every IO block
must inherit from; the concrete core loader :class:`LoadData` is added
in T-TRK-007 per ADR-028 Addendum 1 §C5 / §C9. The concrete core saver
``SaveData`` arrives in T-TRK-008.
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
    normalize_extension,
    normalize_extensions,
)
from scistudio.blocks.io.io_block import IOBlock
from scistudio.blocks.io.loaders.load_data import LoadData
from scistudio.blocks.io.savers.save_data import SaveData
from scistudio.blocks.io.simple_io import SimpleLoader, SimpleSaver

__all__ = [
    "CapabilityDirection",
    "CapabilityValidationError",
    "FormatCapability",
    "IOBlock",
    "InvalidExtensionError",
    "InvalidFormatCapabilityError",
    "InvalidMetadataFidelityError",
    "LoadData",
    "MetadataFidelity",
    "MetadataFidelityLevel",
    "SaveData",
    "SimpleIODeclarationError",
    "SimpleLoader",
    "SimpleSaver",
    "normalize_extension",
    "normalize_extensions",
]
