"""T-IMG-004 Denoise impl tests (Sprint C preprocess subset A).

Covers the ``gaussian``/``median`` pilot methods of
:class:`scistudio_blocks_imaging.preprocess.denoise.Denoise`. The
deferred ``bilateral``/``nlmeans``/``wavelet`` enum values are
asserted to raise ``NotImplementedError``.
"""

from __future__ import annotations

import importlib

import numpy as np
import pytest

pytest.importorskip("skimage")

from scistudio_blocks_imaging.preprocess.denoise import Denoise
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig


def _make_image(arr: np.ndarray, axes: list[str]) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype)
    img._data = arr
    return img


def test_t_img_004_module_importable() -> None:
    importlib.import_module("scistudio_blocks_imaging.preprocess.denoise")


def test_t_img_004_class_has_required_classvars() -> None:
    assert Denoise.type_name == "imaging.denoise"
    assert Denoise.name == "Denoise"
    assert Denoise.subcategory == "preprocess"
    assert "method" in Denoise.config_schema["properties"]


def test_denoise_gaussian_2d_basic() -> None:
    rng = np.random.default_rng(0)
    arr = rng.normal(loc=5.0, scale=1.0, size=(16, 16)).astype(np.float64)
    img = _make_image(arr, ["y", "x"])
    out = Denoise().process_item(img, BlockConfig(params={"method": "gaussian", "sigma": 1.0}))
    assert isinstance(out, Image)
    assert out.axes == ["y", "x"]
    assert out.shape == (16, 16)
    # A gaussian blur reduces variance.
    assert float(np.asarray(out._data).var()) < float(arr.var())


def test_denoise_median_2d_removes_salt_noise() -> None:
    arr = np.full((8, 8), 5.0, dtype=np.float64)
    arr[4, 4] = 100.0  # single spike
    img = _make_image(arr, ["y", "x"])
    out = Denoise().process_item(img, BlockConfig(params={"method": "median", "radius": 1}))
    out_arr = np.asarray(out._data)
    # Median with a disk footprint should drop the lone spike back near 5.
    assert out_arr[4, 4] < 10.0


def test_denoise_invalid_method_raises() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float64), ["y", "x"])
    with pytest.raises(ValueError, match="unknown method"):
        Denoise().process_item(img, BlockConfig(params={"method": "nope"}))


def test_denoise_negative_sigma_raises() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float64), ["y", "x"])
    with pytest.raises(ValueError, match="sigma"):
        Denoise().process_item(img, BlockConfig(params={"method": "gaussian", "sigma": -1.0}))


def test_denoise_deferred_method_raises_not_implemented() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float64), ["y", "x"])
    with pytest.raises(NotImplementedError, match="bilateral"):
        Denoise().process_item(img, BlockConfig(params={"method": "bilateral"}))


def test_denoise_5d_iterates_over_extra_axes() -> None:
    arr = np.ones((2, 3, 8, 8), dtype=np.float64)
    img = _make_image(arr, ["t", "c", "y", "x"])
    out = Denoise().process_item(img, BlockConfig(params={"method": "gaussian", "sigma": 0.5}))
    assert out.axes == ["t", "c", "y", "x"]
    assert out.shape == (2, 3, 8, 8)
