"""In-repo fake SciStudio block package used as a test fixture.

This package mirrors the *shape* of a real domain package (imaging / lcms /
spectroscopy / srs) — ``get_block_package()`` / ``get_types()`` /
``get_previewers()`` factories, a ``types`` module of DataObject subtypes,
an ``io`` module with a loader + saver declaring ``FormatCapability``
records, and a ``previewers`` module — but carries ZERO real scientific
behaviour. Trivial stubs only.

It exists so core machinery tests (serialization round-trip, registry /
type discovery, IO capability dispatch, previewer routing) can exercise a
plugin stand-in after the real domain packages are decoupled into their own
repositories (issue #1770). It is never globally installed; tests that need
entry-point discovery inject its entry points per-test via monkeypatch, and
a conftest prepends its ``src`` to ``sys.path`` so the package is importable.
"""

from __future__ import annotations

from scistudio.blocks.base.package_info import PackageInfo
from scistudio_blocks_fixture.io.load_image import LoadImageFixture
from scistudio_blocks_fixture.io.save_data import SaveDataFixture
from scistudio_blocks_fixture.previewers import get_previewers
from scistudio_blocks_fixture.process_noop import FixtureNoop
from scistudio_blocks_fixture.types import Image, Label, Mask

__version__ = "0.1.0"

_FIXTURE_TYPES: tuple[type, ...] = (Image, Mask, Label)
_FIXTURE_BLOCKS: tuple[type, ...] = (LoadImageFixture, SaveDataFixture, FixtureNoop)


def get_package_info() -> PackageInfo:
    """Return package metadata for the ``scistudio.blocks`` registry."""
    return PackageInfo(
        name="scistudio-blocks-fixture",
        description="Fake in-repo block package fixture for core machinery tests.",
        author="SciStudio Contributors",
        version=__version__,
    )


def get_types() -> list[type]:
    """Return the fixture package's exported type classes."""
    return list(_FIXTURE_TYPES)


def get_blocks() -> list[type]:
    """Return the fixture package's exported concrete block classes."""
    return list(_FIXTURE_BLOCKS)


def get_block_package() -> tuple[PackageInfo, list[type]]:
    """Return package metadata and block classes for ``scistudio.blocks``."""
    return get_package_info(), get_blocks()


__all__ = [
    "FixtureNoop",
    "Image",
    "Label",
    "LoadImageFixture",
    "Mask",
    "SaveDataFixture",
    "__version__",
    "get_block_package",
    "get_blocks",
    "get_package_info",
    "get_previewers",
    "get_types",
]
