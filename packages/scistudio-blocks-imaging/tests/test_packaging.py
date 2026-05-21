from __future__ import annotations

import tomllib
from pathlib import Path

from scistudio_blocks_imaging import (
    __version__,
    get_block_package,
    get_blocks,
    get_package_info,
    get_types,
)
from scistudio_blocks_imaging.tracking.track_objects import TrackObjects
from scistudio_blocks_imaging.types import Image, Label, Mask, Transform

from scistudio.blocks.base.package_info import PackageInfo


def test_get_blocks_returns_all_concrete_imaging_blocks() -> None:
    blocks = get_blocks()

    assert len(blocks) == 49
    assert TrackObjects not in blocks
    assert len({cls.type_name for cls in blocks}) == len(blocks)


def test_get_types_returns_exported_imaging_types() -> None:
    assert get_types() == [Image, Mask, Label, Transform]


def test_get_package_info_matches_release_metadata() -> None:
    info = get_package_info()

    assert info == PackageInfo(
        name="scistudio-blocks-imaging",
        description="Microscopy imaging blocks for SciStudio Phase 11 workflows.",
        author="SciStudio Contributors",
        version="0.1.0",
    )


def test_get_block_package_returns_package_info_and_blocks() -> None:
    info, blocks = get_block_package()

    assert info == get_package_info()
    assert blocks == get_blocks()


def test_pyproject_declares_release_entry_points() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    project = data["project"]
    assert project["name"] == "scistudio-blocks-imaging"
    assert project["version"] == "0.1.0"
    assert project["optional-dependencies"]["cellpose"] == ["cellpose>=3.0"]
    assert project["entry-points"]["scistudio.blocks"]["imaging"] == "scistudio_blocks_imaging:get_block_package"
    assert project["entry-points"]["scistudio.types"]["imaging"] == "scistudio_blocks_imaging:get_types"


def test_pyproject_lists_runtime_dependencies() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    dependencies = set(data["project"]["dependencies"])
    assert {
        "scistudio>=0.2",
        "numpy>=1.24",
        "scipy>=1.11",
        "scikit-image>=0.22",
        "tifffile>=2024.1",
        "zarr>=3.0",
        "matplotlib>=3.8",
        "imageio>=2.33",
        "pydantic>=2.0",
    }.issubset(dependencies)


def test_version_constant_matches_pyproject() -> None:
    assert __version__ == "0.1.0"
