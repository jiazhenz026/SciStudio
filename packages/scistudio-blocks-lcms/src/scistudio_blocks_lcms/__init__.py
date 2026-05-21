"""SciStudio LC-MS plugin — Phase 11.

User-facing entry surface for ``scistudio-blocks-lcms``. Re-exports the
four LC-MS types plus public block classes across the sub-packages
(``io``, ``external``, ``isotope_tracing``).
"""

from __future__ import annotations

from scistudio.blocks.base.package_info import PackageInfo
from scistudio_blocks_lcms.external import AccuCorR, ElMAVENBlock
from scistudio_blocks_lcms.io import (
    LoadMIDTable,
    LoadMzMLFiles,
    LoadPeakTable,
    LoadSampleMetadata,
    SaveTable,
)
from scistudio_blocks_lcms.isotope_tracing import (
    FluxEstimate,
    PoolSizeNormalize,
)
from scistudio_blocks_lcms.types import (
    MIDTable,
    MSRawFile,
    PeakTable,
    SampleMetadata,
    get_types,
)

__version__ = "0.1.0.dev0"

_LCMS_BLOCKS: tuple[type, ...] = (
    # IO
    LoadMzMLFiles,
    LoadPeakTable,
    LoadMIDTable,
    LoadSampleMetadata,
    SaveTable,
    # External
    ElMAVENBlock,
    AccuCorR,
    # Isotope tracing
    FluxEstimate,
    PoolSizeNormalize,
)


def get_package_info() -> PackageInfo:
    """Return package metadata for the ``scistudio.blocks`` registry."""
    return PackageInfo(
        name="scistudio-blocks-lcms",
        description="LC-MS / stable-isotope tracing blocks for SciStudio workflows.",
        author="SciStudio Contributors",
        version=__version__,
    )


def get_blocks() -> list[type]:
    """Return the LC-MS plugin's exported concrete block classes."""
    return list(_LCMS_BLOCKS)


def get_block_package() -> tuple[PackageInfo, list[type]]:
    """Return package metadata and block classes for ``scistudio.blocks``."""
    return get_package_info(), get_blocks()


__all__ = [
    "AccuCorR",
    "ElMAVENBlock",
    "FluxEstimate",
    "LoadMIDTable",
    "LoadMzMLFiles",
    "LoadPeakTable",
    "LoadSampleMetadata",
    "MIDTable",
    "MSRawFile",
    "PeakTable",
    "PoolSizeNormalize",
    "SampleMetadata",
    "SaveTable",
    "get_block_package",
    "get_blocks",
    "get_package_info",
    "get_types",
]
