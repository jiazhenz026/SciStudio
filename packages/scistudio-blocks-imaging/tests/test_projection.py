"""Tests for imaging projection blocks."""

from __future__ import annotations

import numpy as np
import pytest
from scistudio_blocks_imaging.projection.projection import AxisProjection, SelectSlice
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig


def _make_image(arr: np.ndarray, axes: list[str], *, channels: list[str] | None = None) -> Image:
    meta = Image.Meta(channels=channels) if channels is not None else None
    image = Image(axes=axes, shape=arr.shape, dtype=arr.dtype, meta=meta)
    image._data = arr  # type: ignore[attr-defined]
    return image


def test_axis_projection_max_drops_axis() -> None:
    image = _make_image(np.arange(2 * 4 * 4, dtype=np.float32).reshape(2, 4, 4), ["z", "y", "x"])

    projected = AxisProjection().process_item(image, BlockConfig(params={"axis": "z", "method": "max"}))

    assert projected.axes == ["y", "x"]
    assert projected.shape == (4, 4)
    assert np.array_equal(projected._data, np.max(image._data, axis=0))


def test_axis_projection_clears_channel_metadata() -> None:
    image = _make_image(
        np.arange(2 * 3 * 3, dtype=np.float32).reshape(2, 3, 3),
        ["c", "y", "x"],
        channels=["DNA", "RNA"],
    )

    projected = AxisProjection().process_item(image, BlockConfig(params={"axis": "c", "method": "mean"}))

    assert projected.meta is not None
    assert projected.meta.channels is None


def test_axis_projection_invalid_axis_raises() -> None:
    image = _make_image(np.zeros((3, 3), dtype=np.float32), ["y", "x"])

    with pytest.raises(ValueError, match="axis"):
        AxisProjection().process_item(image, BlockConfig(params={"axis": "z", "method": "max"}))


def test_select_slice_drops_axis() -> None:
    image = _make_image(np.arange(2 * 3 * 4, dtype=np.float32).reshape(2, 3, 4), ["c", "y", "x"])

    selected = SelectSlice().process_item(image, BlockConfig(params={"axis": "c", "index": 1}))

    assert selected.axes == ["y", "x"]
    assert selected.shape == (3, 4)
    assert np.array_equal(selected._data, image._data[1])


def test_select_slice_rejects_spatial_axis() -> None:
    image = _make_image(np.zeros((3, 3), dtype=np.float32), ["y", "x"])

    with pytest.raises(ValueError, match="spatial"):
        SelectSlice().process_item(image, BlockConfig(params={"axis": "y", "index": 0}))


def test_select_slice_out_of_bounds_raises() -> None:
    image = _make_image(np.zeros((2, 3, 3), dtype=np.float32), ["c", "y", "x"])

    with pytest.raises(IndexError, match="out of bounds"):
        SelectSlice().process_item(image, BlockConfig(params={"axis": "c", "index": 5}))
