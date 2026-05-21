"""T-IMG-015 Sharpen impl tests."""

from __future__ import annotations

import importlib

import numpy as np
import pytest
from scistudio_blocks_imaging.morphology.sharpen import Sharpen
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig


def _make_image(arr: np.ndarray, axes: list[str]) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype)
    img._data = arr
    return img


def test_t_img_015_module_importable() -> None:
    importlib.import_module("scistudio_blocks_imaging.morphology.sharpen")


def test_t_img_015_class_has_required_classvars() -> None:
    assert Sharpen.type_name == "imaging.sharpen"
    assert Sharpen.name == "Sharpen"
    assert Sharpen.subcategory == "filter"
    assert "method" in Sharpen.config_schema["properties"]


def test_sharpen_unsharp_2d() -> None:
    arr = np.zeros((16, 16), dtype=np.float32)
    arr[5:11, 5:11] = 1.0
    out = Sharpen().process_item(
        _make_image(arr, ["y", "x"]),
        BlockConfig(params={"method": "unsharp", "amount": 1.5, "radius": 1.0}),
    )
    out_arr = np.asarray(out._data)
    assert out.shape == (16, 16)
    assert not np.allclose(out_arr, arr)


def test_sharpen_invalid_method_raises() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float32), ["y", "x"])
    with pytest.raises(ValueError, match="unknown method"):
        Sharpen().process_item(img, BlockConfig(params={"method": "nope"}))


def test_sharpen_laplacian_preserves_shape() -> None:
    arr = np.zeros((16, 16), dtype=np.float32)
    arr[8, 8] = 1.0
    out = Sharpen().process_item(
        _make_image(arr, ["y", "x"]),
        BlockConfig(params={"method": "laplacian", "amount": 1.0, "radius": 1.0}),
    )
    assert out.axes == ["y", "x"]
    assert out.shape == (16, 16)
