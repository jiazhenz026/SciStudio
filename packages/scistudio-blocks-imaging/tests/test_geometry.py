"""T-IMG-008 Geometry impl tests."""

from __future__ import annotations

import importlib

import numpy as np
import pytest

pytest.importorskip("skimage")

from scistudio_blocks_imaging.preprocess.geometry import Crop, Flip, Pad, Resize, Rotate
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.core.units import PhysicalQuantity


def _make_image(arr: np.ndarray, axes: list[str], *, meta: Image.Meta | None = None) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype, meta=meta)
    img._data = arr
    return img


def test_t_img_008_module_importable() -> None:
    importlib.import_module("scistudio_blocks_imaging.preprocess.geometry")


def test_rotate_90_degrees_2d() -> None:
    arr = np.array([[1, 2], [3, 4]], dtype=np.float32)
    img = _make_image(arr, ["y", "x"])
    out = Rotate().process_item(img, BlockConfig(params={"angle": 90}))
    assert np.array_equal(np.asarray(out._data), np.array([[2, 4], [1, 3]], dtype=np.float32))


def test_rotate_invalid_interpolation_raises() -> None:
    img = _make_image(np.zeros((2, 2), dtype=np.float32), ["y", "x"])
    with pytest.raises(ValueError, match="interpolation"):
        Rotate().process_item(img, BlockConfig(params={"angle": 10, "interpolation": "lanczos"}))


def test_flip_y_axis_2d() -> None:
    arr = np.array([[1, 2], [3, 4]], dtype=np.float32)
    img = _make_image(arr, ["y", "x"])
    out = Flip().process_item(img, BlockConfig(params={"axis": "y"}))
    assert np.array_equal(np.asarray(out._data), np.array([[3, 4], [1, 2]], dtype=np.float32))


def test_crop_bbox_basic() -> None:
    arr = np.arange(25, dtype=np.float32).reshape(5, 5)
    img = _make_image(arr, ["y", "x"])
    out = Crop().run(
        {"image": Collection(items=[img], item_type=Image)},
        BlockConfig(params={"bbox": [1, 4, 2, 5]}),
    )["image"][0]
    assert out.shape == (3, 3)
    assert np.array_equal(np.asarray(out._data), arr[1:4, 2:5])


def test_pad_constant_mode() -> None:
    arr = np.array([[1, 2], [3, 4]], dtype=np.float32)
    img = _make_image(arr, ["y", "x"])
    out = Pad().process_item(img, BlockConfig(params={"pad": [1, 0, 2, 1], "mode": "constant", "value": 9}))
    assert out.shape == (3, 5)
    out_arr = np.asarray(out._data)
    assert np.all(out_arr[0] == 9)
    assert np.all(out_arr[:, :2] == 9)


def test_resize_target_shape_updates_pixel_size() -> None:
    meta = Image.Meta(pixel_size=PhysicalQuantity(2.0, "um"))
    img = _make_image(np.arange(16, dtype=np.float32).reshape(4, 4), ["y", "x"], meta=meta)
    out = Resize().process_item(img, BlockConfig(params={"target_shape": [2, 2]}))
    assert out.shape == (2, 2)
    assert out.meta.pixel_size == PhysicalQuantity(4.0, "um")
