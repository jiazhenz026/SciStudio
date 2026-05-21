"""T-IMG-006 Normalize impl tests (Sprint C preprocess subset A)."""

from __future__ import annotations

import importlib

import numpy as np
import pytest
from scistudio_blocks_imaging.preprocess.normalize import Normalize
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig


def _make_image(arr: np.ndarray, axes: list[str]) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype)
    img._data = arr
    return img


def test_t_img_006_module_importable() -> None:
    importlib.import_module("scistudio_blocks_imaging.preprocess.normalize")


def test_t_img_006_class_has_required_classvars() -> None:
    assert Normalize.type_name == "imaging.normalize"
    assert Normalize.subcategory == "preprocess"


def test_normalize_minmax_2d_to_0_1() -> None:
    arr = np.array([[0.0, 5.0], [10.0, 20.0]], dtype=np.float64)
    img = _make_image(arr, ["y", "x"])
    out = Normalize().process_item(img, BlockConfig(params={"method": "minmax"}))
    out_arr = np.asarray(out._data)
    assert float(out_arr.min()) == 0.0
    assert float(out_arr.max()) == 1.0


def test_normalize_zscore_mean_zero_std_one() -> None:
    rng = np.random.default_rng(2)
    arr = rng.normal(loc=10.0, scale=3.0, size=(16, 16)).astype(np.float64)
    img = _make_image(arr, ["y", "x"])
    out = Normalize().process_item(img, BlockConfig(params={"method": "zscore"}))
    out_arr = np.asarray(out._data)
    assert abs(float(out_arr.mean())) < 1e-9
    assert abs(float(out_arr.std()) - 1.0) < 1e-9


def test_normalize_percentile_clips_and_rescales() -> None:
    arr = np.linspace(0, 100, 101, dtype=np.float64).reshape(101, 1)
    # Pad to 2D (y, x).
    arr = np.broadcast_to(arr, (101, 4)).copy()
    img = _make_image(arr, ["y", "x"])
    out = Normalize().process_item(img, BlockConfig(params={"method": "percentile", "low_pct": 10, "high_pct": 90}))
    out_arr = np.asarray(out._data)
    assert float(out_arr.min()) == 0.0
    assert float(out_arr.max()) == 1.0


def test_normalize_zero_variance_safe_zscore() -> None:
    arr = np.full((4, 4), 7.0, dtype=np.float64)
    img = _make_image(arr, ["y", "x"])
    out = Normalize().process_item(img, BlockConfig(params={"method": "zscore"}))
    out_arr = np.asarray(out._data)
    assert not np.isnan(out_arr).any()
    assert np.allclose(out_arr, 0.0)


def test_normalize_zero_variance_safe_minmax() -> None:
    arr = np.full((4, 4), 7.0, dtype=np.float64)
    img = _make_image(arr, ["y", "x"])
    out = Normalize().process_item(img, BlockConfig(params={"method": "minmax"}))
    assert np.allclose(np.asarray(out._data), 0.0)


def test_normalize_invalid_method_raises() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float64), ["y", "x"])
    with pytest.raises(ValueError, match="unknown method"):
        Normalize().process_item(img, BlockConfig(params={"method": "bogus"}))


def test_normalize_histogram_match_deferred() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float64), ["y", "x"])
    with pytest.raises(NotImplementedError, match="histogram_match"):
        Normalize().process_item(img, BlockConfig(params={"method": "histogram_match"}))


def test_normalize_invalid_percentile_bounds_raises() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float64), ["y", "x"])
    with pytest.raises(ValueError, match="low_pct"):
        Normalize().process_item(
            img,
            BlockConfig(params={"method": "percentile", "low_pct": 90, "high_pct": 10}),
        )


def test_normalize_5d_per_slice_each_slice_to_0_1() -> None:
    arr = np.zeros((2, 2, 4, 4), dtype=np.float64)
    arr[0, 0] = np.arange(16).reshape(4, 4)
    arr[0, 1] = np.arange(16, 32).reshape(4, 4)
    arr[1, 0] = np.arange(32, 48).reshape(4, 4)
    arr[1, 1] = np.arange(48, 64).reshape(4, 4)
    img = _make_image(arr, ["t", "c", "y", "x"])
    out = Normalize().process_item(img, BlockConfig(params={"method": "minmax", "per_slice": True}))
    out_arr = np.asarray(out._data)
    # Each (y, x) slice is rescaled independently.
    for t in range(2):
        for c in range(2):
            sl = out_arr[t, c]
            assert float(sl.min()) == 0.0
            assert float(sl.max()) == 1.0


def test_normalize_5d_per_image_when_per_slice_false() -> None:
    arr = np.arange(64, dtype=np.float64).reshape(2, 2, 4, 4)
    img = _make_image(arr, ["t", "c", "y", "x"])
    out = Normalize().process_item(img, BlockConfig(params={"method": "minmax", "per_slice": False}))
    out_arr = np.asarray(out._data)
    assert float(out_arr.min()) == 0.0
    assert float(out_arr.max()) == 1.0
    # With whole-image minmax, the global min cell is 0 and max cell is 1;
    # individual slices will NOT each span [0, 1].
    assert float(out_arr[0, 0].max()) < 1.0
