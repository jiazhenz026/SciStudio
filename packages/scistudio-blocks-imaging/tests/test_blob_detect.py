"""Tests for T-IMG-020 BlobDetect."""

from __future__ import annotations

import importlib

import numpy as np
import pytest
from scistudio_blocks_imaging.segmentation.blob_detect import BlobDetect
from scistudio_blocks_imaging.types import Image, Label

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection


def _make_image(arr: np.ndarray, axes: list[str] | None = None) -> Image:
    image = Image(axes=axes or ["y", "x"], shape=arr.shape, dtype=arr.dtype)
    image._data = arr  # type: ignore[attr-defined]
    return image


def _blob_image(shape: tuple[int, int] = (64, 64)) -> np.ndarray:
    from skimage.draw import disk
    from skimage.filters import gaussian

    image = np.zeros(shape, dtype=np.float32)
    rr1, cc1 = disk((18, 18), 6, shape=shape)
    rr2, cc2 = disk((44, 44), 7, shape=shape)
    image[rr1, cc1] = 1.0
    image[rr2, cc2] = 0.9
    return np.asarray(gaussian(image, sigma=1.0), dtype=np.float32)


def test_t_img_020_module_importable() -> None:
    """The T-IMG-020 module imports cleanly."""
    importlib.import_module("scistudio_blocks_imaging.segmentation.blob_detect")


def test_t_img_020_class_has_required_classvars() -> None:
    """BlobDetect declares the mandatory ProcessBlock/IOBlock ClassVars."""
    mod = importlib.import_module("scistudio_blocks_imaging.segmentation.blob_detect")
    cls = mod.BlobDetect
    assert hasattr(cls, "type_name")
    assert hasattr(cls, "name")
    assert hasattr(cls, "subcategory")
    assert hasattr(cls, "config_schema")


def test_blob_log_basic() -> None:
    pytest.importorskip("skimage")
    label = BlobDetect().process_item(
        _make_image(_blob_image()),
        BlockConfig(params={"method": "LoG", "min_sigma": 2.0, "max_sigma": 8.0, "threshold": 0.05}),
    )

    assert isinstance(label, Label)
    assert label.meta is not None
    assert label.meta.n_objects >= 2


def test_blob_invalid_method_raises() -> None:
    pytest.importorskip("skimage")
    with pytest.raises(ValueError, match="unknown method"):
        BlobDetect().process_item(_make_image(_blob_image()), BlockConfig(params={"method": "bad"}))


def test_blob_dog_and_doh_methods_detect_objects() -> None:
    pytest.importorskip("skimage")
    block = BlobDetect()
    image = _make_image(_blob_image())

    dog = block.process_item(
        image,
        BlockConfig(params={"method": "DoG", "min_sigma": 2.0, "max_sigma": 8.0, "threshold": 0.05}),
    )
    doh = block.process_item(
        image,
        BlockConfig(params={"method": "DoH", "min_sigma": 2.0, "max_sigma": 8.0, "threshold": 0.005}),
    )

    assert dog.meta is not None and dog.meta.n_objects >= 1
    assert doh.meta is not None and doh.meta.n_objects >= 1


def test_blob_run_returns_collection_of_label() -> None:
    pytest.importorskip("skimage")
    image = _make_image(_blob_image())

    result = BlobDetect().run(
        {"image": Collection(items=[image], item_type=Image)},
        BlockConfig(params={"method": "LoG", "min_sigma": 2.0, "max_sigma": 8.0}),
    )

    assert result["label"].item_type is Label
    assert isinstance(result["label"][0], Label)


def test_blob_5d_broadcast() -> None:
    pytest.importorskip("skimage")
    base = _blob_image()
    image = np.stack([base, base], axis=0)
    image = np.stack([image, image], axis=0)[:, :, None, :, :]

    label = BlobDetect().process_item(
        _make_image(image, ["t", "z", "c", "y", "x"]),
        BlockConfig(params={"method": "LoG", "min_sigma": 2.0, "max_sigma": 8.0, "threshold": 0.05}),
    )

    raster = np.asarray(label.slots["raster"]._data)
    assert raster.shape == image.shape
    assert label.meta is not None
    assert label.meta.n_objects >= 8
