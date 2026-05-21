"""T-IMG-010 AxisSplit / AxisMerge impl tests."""

from __future__ import annotations

import importlib

import numpy as np
import pytest
from scistudio_blocks_imaging.preprocess.axis_ops import AxisMerge, AxisSplit
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.meta import ChannelInfo
from scistudio.core.types.collection import Collection


def _make_image(arr: np.ndarray, axes: list[str], *, meta: Image.Meta | None = None) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype, meta=meta)
    img._data = arr
    return img


def test_t_img_010_module_importable() -> None:
    importlib.import_module("scistudio_blocks_imaging.preprocess.axis_ops")


def test_axis_split_c_returns_collection_per_channel() -> None:
    meta = Image.Meta(source_file="sample.tif", channels=["c0", "c1"])
    img = _make_image(np.arange(24, dtype=np.float32).reshape(2, 3, 4), ["c", "y", "x"], meta=meta)
    result = AxisSplit().run({"image": Collection(items=[img], item_type=Image)}, BlockConfig(params={"axis": "c"}))
    out = result["images"]
    assert isinstance(out, Collection)
    assert len(out) == 2
    assert out[0].axes == ["y", "x"]
    assert out[0].shape == (3, 4)
    assert out[0].meta.source_file.endswith("__c=0.tif")
    assert out[0].meta.channels == [ChannelInfo(name="c0")]
    assert out[1].meta.channels == [ChannelInfo(name="c1")]


def test_axis_merge_inverse_of_split() -> None:
    arr = np.arange(24, dtype=np.float32).reshape(2, 3, 4)
    img = _make_image(arr, ["c", "y", "x"])
    split = AxisSplit().run({"image": Collection(items=[img], item_type=Image)}, BlockConfig(params={"axis": "c"}))
    merged = AxisMerge().run({"images": split["images"]}, BlockConfig(params={"axis": "c"}))
    out = merged["image"][0]
    assert out.axes == ["c", "y", "x"]
    assert np.array_equal(np.asarray(out._data), arr)


def test_axis_merge_inconsistent_shapes_raises() -> None:
    a = _make_image(np.zeros((3, 4), dtype=np.float32), ["y", "x"])
    b = _make_image(np.zeros((4, 4), dtype=np.float32), ["y", "x"])
    with pytest.raises(ValueError, match="identical shapes"):
        AxisMerge().run(
            {"images": Collection(items=[a, b], item_type=Image)},
            BlockConfig(params={"axis": "c"}),
        )


def test_axis_split_invalid_axis_raises() -> None:
    img = _make_image(np.zeros((3, 4), dtype=np.float32), ["y", "x"])
    with pytest.raises(ValueError, match="not in image axes"):
        AxisSplit().run({"image": Collection(items=[img], item_type=Image)}, BlockConfig(params={"axis": "c"}))
