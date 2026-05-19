"""T-IMG-003 tests — SaveImage TIFF/Zarr pilot scope."""

from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest
from scieasy_blocks_imaging.io.load_image import LoadImage
from scieasy_blocks_imaging.io.save_image import SaveImage
from scieasy_blocks_imaging.types import Image

from scieasy.blocks.base.config import BlockConfig
from scieasy.core.types.collection import Collection


def _make_image(arr: np.ndarray, axes: list[str]) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype)
    img._data = arr
    return img


def test_t_img_003_module_importable() -> None:
    """The T-IMG-003 module imports cleanly."""
    importlib.import_module("scieasy_blocks_imaging.io.save_image")


def test_t_img_003_class_has_required_classvars() -> None:
    """SaveImage declares the mandatory IOBlock ClassVars."""
    assert SaveImage.type_name == "imaging.save_image"
    assert SaveImage.name == "Save Image"
    assert SaveImage.subcategory == "io"
    assert SaveImage.direction == "output"
    assert "path" in SaveImage.config_schema["properties"]
    assert len(SaveImage.input_ports) == 1


def test_save_single_image_to_tiff(tmp_path: Path) -> None:
    """Writing a bare Image to a .tif path materialises a valid TIFF."""
    arr = np.arange(12, dtype=np.uint16).reshape(3, 4)
    img = _make_image(arr, ["y", "x"])

    out_path = tmp_path / "out.tif"
    SaveImage().save(img, BlockConfig(params={"path": str(out_path)}))

    assert out_path.is_file()
    import tifffile

    back = tifffile.imread(str(out_path))
    assert np.array_equal(back, arr)


def test_save_collection_tiff_round_trip_preserves_data_and_axes(
    tmp_path: Path,
) -> None:
    """Length-1 Collection round-trip preserves data, axes, dtype."""
    arr = np.arange(30, dtype=np.int16).reshape(2, 3, 5)
    img = _make_image(arr, ["c", "y", "x"])
    col = Collection(items=[img], item_type=Image)

    out_path = tmp_path / "rt.tif"
    SaveImage().save(col, BlockConfig(params={"path": str(out_path)}))

    loaded = LoadImage().load(BlockConfig(params={"path": str(out_path)}))
    out = loaded[0]
    assert out.axes == ["c", "y", "x"]
    assert out.shape == (2, 3, 5)
    assert out.dtype == np.int16
    assert np.array_equal(out._data, arr)


def test_save_zarr_round_trip(tmp_path: Path) -> None:
    """Zarr save then LoadImage returns equal data."""
    arr = np.arange(60, dtype=np.float32).reshape(3, 4, 5)
    img = _make_image(arr, ["c", "y", "x"])

    out_path = tmp_path / "store.zarr"
    SaveImage().save(img, BlockConfig(params={"path": str(out_path)}))

    loaded = LoadImage().load(BlockConfig(params={"path": str(out_path)}))
    out = loaded[0]
    assert out.axes == ["c", "y", "x"]
    assert np.array_equal(out._data, arr)


def test_save_format_override_forces_tiff(tmp_path: Path) -> None:
    """An explicit config['format']='tiff' writes a TIFF even with a .dat suffix."""
    arr = np.zeros((2, 2), dtype=np.uint8)
    img = _make_image(arr, ["y", "x"])

    out_path = tmp_path / "forced.dat"
    SaveImage().save(
        img,
        BlockConfig(params={"path": str(out_path), "format": "tiff"}),
    )
    assert out_path.is_file()
    import tifffile

    back = tifffile.imread(str(out_path))
    assert np.array_equal(back, arr)


def test_save_unknown_extension_raises(tmp_path: Path) -> None:
    """An unknown extension with no explicit format raises ValueError."""
    arr = np.zeros((2, 2), dtype=np.uint8)
    img = _make_image(arr, ["y", "x"])
    with pytest.raises(ValueError, match="cannot infer format"):
        SaveImage().save(img, BlockConfig(params={"path": str(tmp_path / "mystery.xyz")}))


def test_save_invalid_format_value_raises(tmp_path: Path) -> None:
    """An unsupported explicit format raises ValueError."""
    arr = np.zeros((2, 2), dtype=np.uint8)
    img = _make_image(arr, ["y", "x"])
    with pytest.raises(ValueError, match="unsupported format"):
        SaveImage().save(
            img,
            BlockConfig(params={"path": str(tmp_path / "x.png"), "format": "png"}),
        )


def test_save_batch_collection_to_directory(tmp_path: Path) -> None:
    """Multi-item Collection is saved as auto-numbered files in a directory."""
    arr = np.zeros((2, 2), dtype=np.uint8)
    imgs = [_make_image(arr.copy(), ["y", "x"]) for _ in range(2)]
    col = Collection(items=imgs, item_type=Image)
    out_dir = tmp_path / "batch_out"
    SaveImage().save(col, BlockConfig(params={"path": str(out_dir)}))
    assert (out_dir / "image_0000.tif").exists()
    assert (out_dir / "image_0001.tif").exists()


def test_save_batch_collection_with_format_override(tmp_path: Path) -> None:
    """Multi-item Collection respects explicit format config."""
    arr = np.zeros((2, 2), dtype=np.uint8)
    imgs = [_make_image(arr.copy(), ["y", "x"]) for _ in range(3)]
    col = Collection(items=imgs, item_type=Image)
    out_dir = tmp_path / "batch_zarr"
    SaveImage().save(col, BlockConfig(params={"path": str(out_dir), "format": "zarr"}))
    assert (out_dir / "image_0000.zarr").exists()
    assert (out_dir / "image_0001.zarr").exists()
    assert (out_dir / "image_0002.zarr").exists()


def test_save_empty_collection_raises(tmp_path: Path) -> None:
    """Empty collections are rejected."""
    col = Collection(items=[], item_type=Image)
    with pytest.raises(ValueError, match="empty"):
        SaveImage().save(col, BlockConfig(params={"path": str(tmp_path / "e.tif")}))


def test_save_creates_parent_directory(tmp_path: Path) -> None:
    """Missing parent directories are created automatically."""
    arr = np.zeros((2, 2), dtype=np.uint8)
    img = _make_image(arr, ["y", "x"])
    out_path = tmp_path / "nested" / "deeper" / "image.tif"
    SaveImage().save(img, BlockConfig(params={"path": str(out_path)}))
    assert out_path.is_file()
