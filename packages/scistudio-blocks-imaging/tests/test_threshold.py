"""Tests for T-IMG-017 Threshold."""

from __future__ import annotations

import importlib

import numpy as np
import pytest
from scistudio_blocks_imaging.segmentation.threshold import Threshold
from scistudio_blocks_imaging.types import Image, Mask

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection


def _make_image(arr: np.ndarray, axes: list[str] | None = None) -> Image:
    image = Image(axes=axes or ["y", "x"], shape=arr.shape, dtype=arr.dtype)
    image._data = arr  # type: ignore[attr-defined]
    return image


def test_t_img_017_module_importable() -> None:
    """The T-IMG-017 module imports cleanly."""
    importlib.import_module("scistudio_blocks_imaging.segmentation.threshold")


def test_t_img_017_class_has_required_classvars() -> None:
    """Threshold declares the mandatory ProcessBlock/IOBlock ClassVars."""
    mod = importlib.import_module("scistudio_blocks_imaging.segmentation.threshold")
    cls = mod.Threshold
    assert hasattr(cls, "type_name")
    assert hasattr(cls, "name")
    assert hasattr(cls, "subcategory")
    assert hasattr(cls, "config_schema")


def test_threshold_otsu_returns_mask() -> None:
    pytest.importorskip("skimage")
    arr = np.zeros((16, 16), dtype=np.float32)
    arr[5:11, 5:11] = 1.0

    mask = Threshold().process_item(_make_image(arr), BlockConfig(params={"method": "otsu"}))

    assert isinstance(mask, Mask)
    assert mask.dtype == bool
    assert np.count_nonzero(np.asarray(mask._data)) > 0


def test_threshold_manual_without_value_raises() -> None:
    pytest.importorskip("skimage")
    arr = np.ones((8, 8), dtype=np.float32)

    with pytest.raises(ValueError, match="requires 'value'"):
        Threshold().process_item(_make_image(arr), BlockConfig(params={"method": "manual"}))


def test_threshold_invalid_method_raises() -> None:
    pytest.importorskip("skimage")
    arr = np.ones((8, 8), dtype=np.float32)

    with pytest.raises(ValueError, match="unknown method"):
        Threshold().process_item(_make_image(arr), BlockConfig(params={"method": "not-a-method"}))


def test_threshold_adaptive_otsu_broadcasts_5d() -> None:
    pytest.importorskip("skimage")
    arr = np.zeros((2, 3, 1, 12, 12), dtype=np.float32)
    arr[:, :, :, 3:9, 3:9] = 1.0

    mask = Threshold().process_item(
        _make_image(arr, ["t", "z", "c", "y", "x"]),
        BlockConfig(params={"method": "adaptive_otsu", "block_size": 5}),
    )

    assert mask.shape == arr.shape
    assert np.asarray(mask._data).dtype == bool
    assert np.count_nonzero(np.asarray(mask._data)) > 0


def test_threshold_run_returns_collection_of_mask() -> None:
    pytest.importorskip("skimage")
    arr = np.zeros((10, 10), dtype=np.float32)
    arr[2:8, 2:8] = 1.0
    image = _make_image(arr)

    result = Threshold().run(
        {"image": Collection(items=[image], item_type=Image)}, BlockConfig(params={"method": "li"})
    )

    assert result["mask"].item_type is Mask
    assert isinstance(result["mask"][0], Mask)
