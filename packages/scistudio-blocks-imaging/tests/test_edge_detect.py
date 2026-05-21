"""T-IMG-013 EdgeDetect impl tests."""

from __future__ import annotations

import importlib

import numpy as np
import pytest
from scistudio_blocks_imaging.morphology.edge_detect import EdgeDetect
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig


def _make_image(arr: np.ndarray, axes: list[str]) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype)
    img._data = arr
    return img


def test_t_img_013_module_importable() -> None:
    importlib.import_module("scistudio_blocks_imaging.morphology.edge_detect")


def test_t_img_013_class_has_required_classvars() -> None:
    assert EdgeDetect.type_name == "imaging.edge_detect"
    assert EdgeDetect.name == "Edge Detect"
    assert EdgeDetect.subcategory == "filter"
    assert "method" in EdgeDetect.config_schema["properties"]


def test_edge_sobel_2d() -> None:
    arr = np.zeros((16, 16), dtype=np.float32)
    arr[:, 8:] = 1.0
    out = EdgeDetect().process_item(_make_image(arr, ["y", "x"]), BlockConfig(params={"method": "sobel"}))
    out_arr = np.asarray(out._data)
    assert out.shape == (16, 16)
    assert float(out_arr.max()) > 0.0


def test_edge_canny_thresholds_param() -> None:
    arr = np.zeros((16, 16), dtype=np.float32)
    arr[4:12, 4:12] = 1.0
    out = EdgeDetect().process_item(
        _make_image(arr, ["y", "x"]),
        BlockConfig(params={"method": "canny", "sigma": 1.0, "low_threshold": 0.1, "high_threshold": 0.3}),
    )
    out_arr = np.asarray(out._data)
    assert out_arr.dtype == np.bool_
    assert int(out_arr.sum()) > 0


def test_edge_invalid_method_raises() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float32), ["y", "x"])
    with pytest.raises(ValueError, match="unknown method"):
        EdgeDetect().process_item(img, BlockConfig(params={"method": "nope"}))


def test_edge_invalid_threshold_order_raises() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float32), ["y", "x"])
    with pytest.raises(ValueError, match="low_threshold"):
        EdgeDetect().process_item(
            img,
            BlockConfig(params={"method": "canny", "low_threshold": 0.4, "high_threshold": 0.2}),
        )
