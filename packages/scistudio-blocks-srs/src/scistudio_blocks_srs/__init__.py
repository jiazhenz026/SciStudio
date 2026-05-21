"""SciStudio SRS plugin exports."""

from __future__ import annotations

from scistudio.blocks.base.package_info import PackageInfo
from scistudio_blocks_srs.component_analysis import (
    SRSICA,
    SRSPCA,
    SRSVCA,
    SRSKMeansCluster,
    SRSUnmix,
)
from scistudio_blocks_srs.preprocess import SRSBaseline, SRSCalibrate, SRSSpectralDenoise
from scistudio_blocks_srs.spectral_extraction.extract_spectrum import ExtractSpectrum
from scistudio_blocks_srs.types import SRSImage, get_types

__version__ = "0.1.0.dev0"

_SRS_BLOCKS: tuple[type, ...] = (
    # Preprocess
    SRSSpectralDenoise,
    SRSBaseline,
    SRSCalibrate,
    # Component analysis
    SRSPCA,
    SRSICA,
    SRSVCA,
    SRSUnmix,
    SRSKMeansCluster,
    # Spectral extraction
    ExtractSpectrum,
)


def get_package_info() -> PackageInfo:
    """Return package metadata for the ``scistudio.blocks`` registry."""
    return PackageInfo(
        name="scistudio-blocks-srs",
        description="SRS (Stimulated Raman Scattering) blocks for SciStudio workflows.",
        author="SciStudio Contributors",
        version=__version__,
    )


def get_blocks() -> list[type]:
    """Return the SRS plugin's exported concrete block classes."""
    return list(_SRS_BLOCKS)


def get_block_package() -> tuple[PackageInfo, list[type]]:
    """Return package metadata and block classes for ``scistudio.blocks``."""
    return get_package_info(), get_blocks()


__all__ = [
    "SRSICA",
    "SRSPCA",
    "SRSVCA",
    "ExtractSpectrum",
    "SRSBaseline",
    "SRSCalibrate",
    "SRSImage",
    "SRSKMeansCluster",
    "SRSSpectralDenoise",
    "SRSUnmix",
    "get_block_package",
    "get_blocks",
    "get_package_info",
    "get_types",
]
