"""T-IMG-012 MorphologyOp impl tests."""

from __future__ import annotations

import importlib

import numpy as np
import pytest
from scistudio_blocks_imaging.morphology.morphology_op import MorphologyOp
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig


def _make_image(arr: np.ndarray, axes: list[str]) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype)
    img._data = arr
    return img


def test_t_img_012_module_importable() -> None:
    importlib.import_module("scistudio_blocks_imaging.morphology.morphology_op")


def test_t_img_012_class_has_required_classvars() -> None:
    assert MorphologyOp.type_name == "imaging.morphology_op"
    assert MorphologyOp.name == "Morphology Op"
    assert MorphologyOp.subcategory == "filter"
    assert "op" in MorphologyOp.config_schema["properties"]


def test_morphology_erode_2d() -> None:
    arr = np.zeros((7, 7), dtype=np.float32)
    arr[2:5, 2:5] = 1.0
    out = MorphologyOp().process_item(
        _make_image(arr, ["y", "x"]),
        BlockConfig(params={"op": "erode", "selem_shape": "square", "selem_size": 1}),
    )
    out_arr = np.asarray(out._data)
    assert out.shape == (7, 7)
    assert float(out_arr.sum()) < float(arr.sum())
    assert out_arr[3, 3] == pytest.approx(1.0)


def test_morphology_dilate_2d() -> None:
    arr = np.zeros((7, 7), dtype=np.float32)
    arr[3, 3] = 1.0
    out = MorphologyOp().process_item(
        _make_image(arr, ["y", "x"]),
        BlockConfig(params={"op": "dilate", "selem_shape": "cross", "selem_size": 1}),
    )
    out_arr = np.asarray(out._data)
    assert float(out_arr.sum()) > float(arr.sum())
    assert out_arr[3, 2] == pytest.approx(1.0)
    assert out_arr[2, 3] == pytest.approx(1.0)


def test_morphology_invalid_op_raises() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float32), ["y", "x"])
    with pytest.raises(ValueError, match="unknown op"):
        MorphologyOp().process_item(img, BlockConfig(params={"op": "nope"}))


def test_morphology_iterates_over_extra_axes() -> None:
    arr = np.zeros((2, 7, 7), dtype=np.float32)
    arr[:, 3, 3] = 1.0
    out = MorphologyOp().process_item(
        _make_image(arr, ["c", "y", "x"]),
        BlockConfig(params={"op": "dilate", "selem_shape": "disk", "selem_size": 1}),
    )
    assert out.axes == ["c", "y", "x"]
    assert out.shape == (2, 7, 7)
