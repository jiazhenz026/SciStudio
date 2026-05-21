"""Tests for imaging scalar math blocks."""

from __future__ import annotations

import numpy as np
import pytest
from scistudio_blocks_imaging.math.scalar_ops import AddScalar, DivideScalar, MultiplyScalar, SubtractScalar
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig


def _make_image(arr: np.ndarray, axes: list[str] | None = None, *, channels: list[str] | None = None) -> Image:
    meta = Image.Meta(channels=channels) if channels is not None else None
    image = Image(axes=axes or ["y", "x"], shape=arr.shape, dtype=arr.dtype, meta=meta)
    image._data = arr  # type: ignore[attr-defined]
    return image


def test_add_scalar_adds_value() -> None:
    image = _make_image(np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32))

    result = AddScalar().process_item(image, BlockConfig(params={"value": 2.5}))

    assert np.allclose(result._data, image._data + 2.5)
    assert result.axes == image.axes


def test_subtract_scalar_subtracts_value() -> None:
    image = _make_image(np.array([[5.0, 6.0], [7.0, 8.0]], dtype=np.float32))

    result = SubtractScalar().process_item(image, BlockConfig(params={"value": 1.5}))

    assert np.allclose(result._data, image._data - 1.5)


def test_multiply_scalar_broadcasts_over_extra_axes() -> None:
    arr = np.arange(2 * 3 * 4 * 5, dtype=np.float32).reshape(2, 3, 4, 5)
    image = _make_image(arr, ["t", "z", "y", "x"])

    result = MultiplyScalar().process_item(image, BlockConfig(params={"value": 3}))

    assert result.shape == image.shape
    assert np.array_equal(result._data, arr * 3)


def test_divide_scalar_supports_epsilon() -> None:
    image = _make_image(np.array([[2.0, 4.0]], dtype=np.float32))

    result = DivideScalar().process_item(image, BlockConfig(params={"value": 0.0, "epsilon": 2.0}))

    assert np.allclose(result._data, np.array([[1.0, 2.0]], dtype=np.float32))


def test_divide_scalar_zero_denominator_raises() -> None:
    image = _make_image(np.array([[1.0]], dtype=np.float32))

    with pytest.raises(ValueError, match="non-zero"):
        DivideScalar().process_item(image, BlockConfig(params={"value": 0.0, "epsilon": 0.0}))


def test_scalar_ops_preserve_metadata() -> None:
    image = _make_image(
        np.array([[[1.0, 2.0], [3.0, 4.0]]], dtype=np.float32),
        ["c", "y", "x"],
        channels=["DNA"],
    )

    result = AddScalar().process_item(image, BlockConfig(params={"value": 1.0}))

    assert result.meta == image.meta
    assert result.axes == image.axes


def test_scalar_ops_reject_non_numeric_value() -> None:
    image = _make_image(np.array([[1.0]], dtype=np.float32))

    with pytest.raises(ValueError, match="number"):
        AddScalar().process_item(image, BlockConfig(params={"value": "oops"}))
