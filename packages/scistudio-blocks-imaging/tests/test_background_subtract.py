"""T-IMG-005 BackgroundSubtract impl tests (Sprint C preprocess subset A)."""

from __future__ import annotations

import importlib

import numpy as np
import pytest

pytest.importorskip("skimage")

from scistudio_blocks_imaging.preprocess.background_subtract import (
    BackgroundSubtract,
)
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig


def _make_image(arr: np.ndarray, axes: list[str]) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype)
    img._data = arr
    return img


def test_t_img_005_module_importable() -> None:
    importlib.import_module("scistudio_blocks_imaging.preprocess.background_subtract")


def test_t_img_005_class_has_required_classvars() -> None:
    assert BackgroundSubtract.type_name == "imaging.background_subtract"
    assert BackgroundSubtract.subcategory == "preprocess"


def test_background_constant_subtracts_value() -> None:
    arr = np.full((6, 6), 10.0, dtype=np.float64)
    img = _make_image(arr, ["y", "x"])
    out = BackgroundSubtract().process_item(
        img,
        BlockConfig(params={"method": "constant", "value": 3.0, "clip_to_zero": False}),
    )
    out_arr = np.asarray(out._data)
    assert np.allclose(out_arr, 7.0)


def test_background_constant_clip_to_zero_clamps() -> None:
    arr = np.full((5, 5), 2.0, dtype=np.float64)
    img = _make_image(arr, ["y", "x"])
    out = BackgroundSubtract().process_item(
        img,
        BlockConfig(params={"method": "constant", "value": 10.0, "clip_to_zero": True}),
    )
    assert float(np.asarray(out._data).min()) == 0.0


def test_background_tophat_2d_runs() -> None:
    arr = np.zeros((16, 16), dtype=np.float64)
    arr[8, 8] = 5.0
    img = _make_image(arr, ["y", "x"])
    out = BackgroundSubtract().process_item(img, BlockConfig(params={"method": "tophat", "radius": 3}))
    assert out.shape == (16, 16)


def test_background_rollingball_2d_runs() -> None:
    rng = np.random.default_rng(1)
    arr = rng.uniform(0, 1, size=(16, 16)).astype(np.float64)
    img = _make_image(arr, ["y", "x"])
    out = BackgroundSubtract().process_item(img, BlockConfig(params={"method": "rollingball", "radius": 5}))
    assert out.shape == (16, 16)


def test_background_polynomial_2d_runs() -> None:
    yy, xx = np.mgrid[0:8, 0:8]
    arr = (yy + xx).astype(np.float64)
    img = _make_image(arr, ["y", "x"])
    out = BackgroundSubtract().process_item(
        img,
        BlockConfig(params={"method": "polynomial", "degree": 1, "clip_to_zero": False}),
    )
    out_arr = np.asarray(out._data)
    # Degree-1 poly fits a linear gradient exactly → residual ~0.
    assert float(np.abs(out_arr).max()) < 1e-8


def test_background_invalid_method_raises() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float64), ["y", "x"])
    with pytest.raises(ValueError, match="unknown method"):
        BackgroundSubtract().process_item(img, BlockConfig(params={"method": "bogus"}))


def test_background_invalid_radius_raises() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float64), ["y", "x"])
    with pytest.raises(ValueError, match="radius"):
        BackgroundSubtract().process_item(img, BlockConfig(params={"method": "rollingball", "radius": 0}))


def test_background_5d_iterates_over_extra_axes() -> None:
    arr = np.ones((2, 2, 6, 6), dtype=np.float64) * 5.0
    img = _make_image(arr, ["t", "c", "y", "x"])
    out = BackgroundSubtract().process_item(
        img,
        BlockConfig(params={"method": "constant", "value": 2.0, "clip_to_zero": False}),
    )
    assert out.axes == ["t", "c", "y", "x"]
    assert out.shape == (2, 2, 6, 6)
    assert np.allclose(np.asarray(out._data), 3.0)
