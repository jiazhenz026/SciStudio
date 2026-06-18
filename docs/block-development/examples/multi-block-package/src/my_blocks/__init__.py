"""Example multi-block package for SciStudio.

This package demonstrates the Tier 2 distribution pattern with the canonical
primary entry-point shape:

- ``PackageInfo`` metadata.
- ``get_blocks() -> tuple[PackageInfo, list[type]]`` — the ``scistudio.blocks``
  callable (what ``scistudio init-block-package`` scaffolds).
- ``get_types() -> list[type]`` — the ``scistudio.types`` callable.
- ``scistudio.blocks`` and ``scistudio.types`` entry-points in pyproject.toml.

See ``docs/block-development/publishing.md`` for the full guide and the third
``scistudio.previewers`` entry point (ADR-048).
"""

from __future__ import annotations

from my_blocks.blocks.gaussian_blur import GaussianBlur
from my_blocks.blocks.threshold import SimpleThreshold
from my_blocks.types.custom_image import AnalysisImage
from scistudio.blocks.base.package_info import PackageInfo

__version__ = "0.1.0"

_PACKAGE_INFO = PackageInfo(
    name="scistudio-blocks-example",
    description="Example blocks for the Block Developer SDK guide.",
    author="SciStudio Contributors",
    version=__version__,
)
_TYPES: tuple[type, ...] = (AnalysisImage,)
_BLOCKS: tuple[type, ...] = (GaussianBlur, SimpleThreshold)


def get_blocks() -> tuple[PackageInfo, list[type]]:
    """Return package metadata and the block list for the scistudio.blocks entry-point."""
    return (_PACKAGE_INFO, list(_BLOCKS))


def get_types() -> list[type]:
    """Return exported type classes for the scistudio.types entry-point."""
    return list(_TYPES)
