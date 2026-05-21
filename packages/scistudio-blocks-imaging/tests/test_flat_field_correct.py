"""T-IMG-007 FlatFieldCorrect impl tests (Sprint C preprocess subset A)."""

from __future__ import annotations

import importlib

import numpy as np
import pytest
from scistudio_blocks_imaging.preprocess.flat_field_correct import FlatFieldCorrect
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection


def _make_image(arr: np.ndarray, axes: list[str]) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype)
    img._data = arr
    return img


def _make_col(img: Image) -> Collection:
    return Collection(items=[img], item_type=Image)


def test_t_img_007_module_importable() -> None:
    importlib.import_module("scistudio_blocks_imaging.preprocess.flat_field_correct")


def test_t_img_007_class_has_required_classvars() -> None:
    assert FlatFieldCorrect.type_name == "imaging.flatfield_correct"
    assert FlatFieldCorrect.subcategory == "preprocess"
    assert len(FlatFieldCorrect.input_ports) == 3


def test_flatfield_basic_no_dark_uniform() -> None:
    # Uniform flat and uniform image → corrected ~= image (since scale=mean(flat)).
    image = _make_image(np.full((4, 4), 10.0, dtype=np.float64), ["y", "x"])
    flat = _make_image(np.full((4, 4), 2.0, dtype=np.float64), ["y", "x"])

    block = FlatFieldCorrect()
    result = block.run(
        {"image": _make_col(image), "flat_field": _make_col(flat)},
        BlockConfig(params={"method": "basic"}),
    )
    out_col = result["image"]
    assert isinstance(out_col, Collection)
    out = out_col[0]
    out_arr = np.asarray(out._data)
    # out = image / flat * mean(flat) = 10/2 * 2 = 10.
    assert np.allclose(out_arr, 10.0)


def test_flatfield_basic_with_dark_frame() -> None:
    image = _make_image(np.full((4, 4), 12.0, dtype=np.float64), ["y", "x"])
    flat = _make_image(np.full((4, 4), 4.0, dtype=np.float64), ["y", "x"])
    dark = _make_image(np.full((4, 4), 2.0, dtype=np.float64), ["y", "x"])

    result = FlatFieldCorrect().run(
        {
            "image": _make_col(image),
            "flat_field": _make_col(flat),
            "dark_frame": _make_col(dark),
        },
        BlockConfig(params={"method": "basic"}),
    )
    out = result["image"][0]
    out_arr = np.asarray(out._data)
    # (12-2)/(4-2) * mean(4-2) = 10/2 * 2 = 10.
    assert np.allclose(out_arr, 10.0)


def test_flatfield_shape_mismatch_raises() -> None:
    image = _make_image(np.zeros((4, 4), dtype=np.float64), ["y", "x"])
    flat = _make_image(np.zeros((5, 5), dtype=np.float64), ["y", "x"])
    with pytest.raises(ValueError, match="shape"):
        FlatFieldCorrect().run(
            {"image": _make_col(image), "flat_field": _make_col(flat)},
            BlockConfig(params={"method": "basic"}),
        )


def test_flatfield_invalid_method_raises() -> None:
    image = _make_image(np.zeros((4, 4), dtype=np.float64), ["y", "x"])
    flat = _make_image(np.zeros((4, 4), dtype=np.float64), ["y", "x"])
    with pytest.raises(ValueError, match="unknown method"):
        FlatFieldCorrect().run(
            {"image": _make_col(image), "flat_field": _make_col(flat)},
            BlockConfig(params={"method": "bogus"}),
        )


def test_flatfield_zero_flat_handled_without_nan() -> None:
    image = _make_image(np.full((4, 4), 5.0, dtype=np.float64), ["y", "x"])
    flat = _make_image(np.zeros((4, 4), dtype=np.float64), ["y", "x"])
    result = FlatFieldCorrect().run(
        {"image": _make_col(image), "flat_field": _make_col(flat)},
        BlockConfig(params={"method": "basic"}),
    )
    out_arr = np.asarray(result["image"][0]._data)
    assert not np.isnan(out_arr).any()


def test_flatfield_5d_iterates_per_slice() -> None:
    image_arr = np.full((2, 3, 4, 4), 10.0, dtype=np.float64)
    image = _make_image(image_arr, ["t", "c", "y", "x"])
    flat = _make_image(np.full((4, 4), 2.0, dtype=np.float64), ["y", "x"])
    result = FlatFieldCorrect().run(
        {"image": _make_col(image), "flat_field": _make_col(flat)},
        BlockConfig(params={"method": "basic"}),
    )
    out = result["image"][0]
    assert out.axes == ["t", "c", "y", "x"]
    assert out.shape == (2, 3, 4, 4)
    assert np.allclose(np.asarray(out._data), 10.0)


def test_flatfield_basic_method_default() -> None:
    image = _make_image(np.full((4, 4), 10.0, dtype=np.float64), ["y", "x"])
    flat = _make_image(np.full((4, 4), 2.0, dtype=np.float64), ["y", "x"])
    # No explicit method → default "basic".
    result = FlatFieldCorrect().run(
        {"image": _make_col(image), "flat_field": _make_col(flat)},
        BlockConfig(params={}),
    )
    assert isinstance(result["image"], Collection)
