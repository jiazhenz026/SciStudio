"""IO block authoring surface (ADR-052 §6).

Canonical root: ``from scistudio.blocks.io import …``. The public surface is
this module's ``__all__`` — the :class:`IOBlock` ABC, the ergonomic
:class:`SimpleLoader` / :class:`SimpleSaver` bases, the ADR-043 capability
declaration types, and the catchable capability-error hierarchy.

The concrete core dynamic-port blocks ``LoadData`` / ``SaveData`` and the
``normalize_extension`` / ``normalize_extensions`` helpers are **internal**
(ADR-052 §6.3, §6.5): they remain importable via their deep paths
(``scistudio.blocks.io.loaders.load_data`` / ``…savers.save_data`` /
``scistudio.blocks.io.capabilities``) for framework callers, but carry no
stability promise and are not re-exported here.
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
