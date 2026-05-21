"""T-IMG-009 ConvertDType impl tests."""

from __future__ import annotations

import importlib

import numpy as np
import pytest
from scistudio_blocks_imaging.preprocess.convert_dtype import ConvertDType
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig


def _make_image(arr: np.ndarray, axes: list[str]) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype)
    img._data = arr
    return img


def test_t_img_009_module_importable() -> None:
    importlib.import_module("scistudio_blocks_imaging.preprocess.convert_dtype")


def test_t_img_009_class_has_required_classvars() -> None:
    assert ConvertDType.type_name == "imaging.convert_dtype"
    assert ConvertDType.subcategory == "preprocess"
    assert "target_dtype" in ConvertDType.config_schema["properties"]


def test_convert_uint8_to_float32_linear() -> None:
    img = _make_image(np.array([[0, 255]], dtype=np.uint8), ["y", "x"])
    out = ConvertDType().process_item(img, BlockConfig(params={"target_dtype": "float32", "rescale": "linear"}))
    out_arr = np.asarray(out._data)
    assert out_arr.dtype == np.float32
    assert np.allclose(out_arr, np.array([[0.0, 1.0]], dtype=np.float32))


def test_convert_uint16_to_uint8_linear() -> None:
    img = _make_image(np.array([[0, 65535]], dtype=np.uint16), ["y", "x"])
    out = ConvertDType().process_item(img, BlockConfig(params={"target_dtype": "uint8", "rescale": "linear"}))
    out_arr = np.asarray(out._data)
    assert out_arr.dtype == np.uint8
    assert np.array_equal(out_arr, np.array([[0, 255]], dtype=np.uint8))


def test_convert_float32_to_uint8_clip() -> None:
    img = _make_image(np.array([[-5.0, 12.5, 300.0]], dtype=np.float32), ["y", "x"])
    out = ConvertDType().process_item(img, BlockConfig(params={"target_dtype": "uint8", "rescale": "clip"}))
    out_arr = np.asarray(out._data)
    assert np.array_equal(out_arr, np.array([[0, 12, 255]], dtype=np.uint8))


def test_convert_to_bool_thresholds_at_zero() -> None:
    img = _make_image(np.array([[-1.0, 0.0, 2.0]], dtype=np.float32), ["y", "x"])
    out = ConvertDType().process_item(img, BlockConfig(params={"target_dtype": "bool"}))
    out_arr = np.asarray(out._data)
    assert np.array_equal(out_arr, np.array([[False, False, True]], dtype=bool))


def test_convert_invalid_dtype_raises() -> None:
    img = _make_image(np.zeros((2, 2), dtype=np.float32), ["y", "x"])
    with pytest.raises(ValueError, match="target_dtype"):
        ConvertDType().process_item(img, BlockConfig(params={"target_dtype": "complex64"}))


def test_convert_preserves_axes_and_shape() -> None:
    arr = np.arange(16, dtype=np.uint8).reshape(2, 2, 2, 2)
    img = _make_image(arr, ["t", "c", "y", "x"])
    out = ConvertDType().process_item(img, BlockConfig(params={"target_dtype": "float64"}))
    assert out.axes == ["t", "c", "y", "x"]
    assert out.shape == (2, 2, 2, 2)


def test_convert_preserves_meta() -> None:
    meta = Image.Meta(source_file="example.tif", objective="20x")
    img = Image(axes=["y", "x"], shape=(2, 2), dtype=np.uint8, meta=meta)
    img._data = np.array([[0, 1], [2, 3]], dtype=np.uint8)
    out = ConvertDType().process_item(img, BlockConfig(params={"target_dtype": "float32"}))
    assert out.meta is meta
