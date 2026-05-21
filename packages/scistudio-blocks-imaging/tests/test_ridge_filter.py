"""T-IMG-014 RidgeFilter impl tests."""

from __future__ import annotations

import importlib

import numpy as np
import pytest
from scistudio_blocks_imaging.morphology.ridge_filter import RidgeFilter
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig


def _make_image(arr: np.ndarray, axes: list[str]) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype)
    img._data = arr
    return img


def test_t_img_014_module_importable() -> None:
    importlib.import_module("scistudio_blocks_imaging.morphology.ridge_filter")


def test_t_img_014_class_has_required_classvars() -> None:
    assert RidgeFilter.type_name == "imaging.ridge_filter"
    assert RidgeFilter.name == "Ridge Filter"
    assert RidgeFilter.subcategory == "filter"
    assert "method" in RidgeFilter.config_schema["properties"]


def test_ridge_frangi_2d() -> None:
    arr = np.zeros((32, 32), dtype=np.float32)
    arr[8:24, 15:17] = 1.0
    out = RidgeFilter().process_item(
        _make_image(arr, ["y", "x"]),
        BlockConfig(params={"method": "frangi", "sigma_min": 1.0, "sigma_max": 2.0, "num_sigma": 2}),
    )
    out_arr = np.asarray(out._data)
    assert out.shape == (32, 32)
    assert float(out_arr.max()) > 0.0


def test_ridge_invalid_method_raises() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float32), ["y", "x"])
    with pytest.raises(ValueError, match="unknown method"):
        RidgeFilter().process_item(img, BlockConfig(params={"method": "nope"}))


def test_ridge_invalid_sigma_range_raises() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float32), ["y", "x"])
    with pytest.raises(ValueError, match="sigma_min"):
        RidgeFilter().process_item(
            img,
            BlockConfig(params={"method": "sato", "sigma_min": 3.0, "sigma_max": 1.0, "num_sigma": 2}),
        )
