"""Tests for T-IMG-018 Watershed."""

from __future__ import annotations

import importlib

import numpy as np
import pytest
from scistudio_blocks_imaging.segmentation.watershed import Watershed
from scistudio_blocks_imaging.types import Image, Label, Mask

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection


def _make_image(arr: np.ndarray, axes: list[str] | None = None) -> Image:
    image = Image(axes=axes or ["y", "x"], shape=arr.shape, dtype=arr.dtype)
    image._data = arr  # type: ignore[attr-defined]
    return image


def _make_mask(arr: np.ndarray, axes: list[str] | None = None) -> Mask:
    mask = Mask(axes=axes or ["y", "x"], shape=arr.shape, dtype=bool)
    mask._data = np.asarray(arr, dtype=bool)  # type: ignore[attr-defined]
    return mask


def _make_label(arr: np.ndarray, axes: list[str] | None = None) -> Label:
    raster = Array(axes=axes or ["y", "x"], shape=arr.shape, dtype=arr.dtype)
    raster._data = arr  # type: ignore[attr-defined]
    return Label(slots={"raster": raster}, meta=Label.Meta(source_file="markers.tif", n_objects=int(arr.max())))


def test_t_img_018_module_importable() -> None:
    """The T-IMG-018 module imports cleanly."""
    importlib.import_module("scistudio_blocks_imaging.segmentation.watershed")


def test_t_img_018_class_has_required_classvars() -> None:
    """Watershed declares the mandatory ProcessBlock/IOBlock ClassVars."""
    mod = importlib.import_module("scistudio_blocks_imaging.segmentation.watershed")
    cls = mod.Watershed
    assert hasattr(cls, "type_name")
    assert hasattr(cls, "name")
    assert hasattr(cls, "subcategory")
    assert hasattr(cls, "config_schema")


def test_watershed_distance_basic_2d() -> None:
    pytest.importorskip("skimage")
    pytest.importorskip("scipy")
    image = np.zeros((32, 32), dtype=np.float32)
    image[6:14, 6:14] = 1.0
    image[18:26, 18:26] = 1.0
    mask = image > 0

    label = Watershed().run(
        {
            "image": Collection(items=[_make_image(image)], item_type=Image),
            "mask": Collection(items=[_make_mask(mask)], item_type=Mask),
        },
        BlockConfig(params={"method": "distance", "min_distance": 3}),
    )["label"][0]

    raster = label.slots["raster"]
    assert isinstance(label, Label)
    assert raster.shape == image.shape
    assert label.meta is not None
    assert label.meta.n_objects >= 2


def test_watershed_with_markers_input() -> None:
    pytest.importorskip("skimage")
    pytest.importorskip("scipy")
    image = np.zeros((24, 24), dtype=np.float32)
    image[4:20, 4:20] = 1.0
    markers = np.zeros((24, 24), dtype=np.int32)
    markers[7, 7] = 1
    markers[16, 16] = 2

    label = Watershed().run(
        {
            "image": Collection(items=[_make_image(image)], item_type=Image),
            "markers": Collection(items=[_make_label(markers)], item_type=Label),
        },
        BlockConfig(params={"method": "markers"}),
    )["label"][0]

    assert isinstance(label, Label)
    assert label.meta is not None
    assert label.meta.n_objects == 2


def test_watershed_invalid_method_raises() -> None:
    pytest.importorskip("skimage")
    pytest.importorskip("scipy")
    image = np.ones((8, 8), dtype=np.float32)

    with pytest.raises(ValueError, match="unknown method"):
        Watershed().run(
            {"image": Collection(items=[_make_image(image)], item_type=Image)},
            BlockConfig(params={"method": "bogus"}),
        )


def test_watershed_gradient_with_mask_input() -> None:
    pytest.importorskip("skimage")
    pytest.importorskip("scipy")
    image = np.zeros((20, 20), dtype=np.float32)
    image[4:16, 4:16] = np.linspace(0.2, 1.0, 12 * 12, dtype=np.float32).reshape(12, 12)
    mask = np.zeros((20, 20), dtype=bool)
    mask[4:16, 4:16] = True

    label = Watershed().run(
        {
            "image": Collection(items=[_make_image(image)], item_type=Image),
            "mask": Collection(items=[_make_mask(mask)], item_type=Mask),
        },
        BlockConfig(params={"method": "gradient", "min_distance": 2}),
    )["label"][0]

    assert isinstance(label, Label)
    assert np.count_nonzero(np.asarray(label.slots["raster"]._data)) > 0


def test_watershed_5d_broadcast() -> None:
    pytest.importorskip("skimage")
    pytest.importorskip("scipy")
    image = np.zeros((2, 2, 1, 16, 16), dtype=np.float32)
    image[:, :, :, 4:8, 4:8] = 1.0
    image[:, :, :, 9:13, 9:13] = 1.0
    mask = image > 0

    label = Watershed().run(
        {
            "image": Collection(items=[_make_image(image, ["t", "z", "c", "y", "x"])], item_type=Image),
            "mask": Collection(items=[_make_mask(mask, ["t", "z", "c", "y", "x"])], item_type=Mask),
        },
        BlockConfig(params={"method": "distance", "min_distance": 2}),
    )["label"][0]

    raster = np.asarray(label.slots["raster"]._data)
    assert raster.shape == image.shape
    assert label.meta is not None
    assert label.meta.n_objects >= 8
