"""Tests for the imaging image calculator block."""

from __future__ import annotations

import numpy as np
import pytest
from scistudio_blocks_imaging.math.image_calculator import ImageCalculator
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection


def _make_image(arr: np.ndarray, axes: list[str] | None = None) -> Image:
    image = Image(axes=axes or ["y", "x"], shape=arr.shape, dtype=arr.dtype)
    image._data = arr  # type: ignore[attr-defined]
    return image


def test_image_calculator_default_expression_adds() -> None:
    left = _make_image(np.array([[1.0, 2.0]], dtype=np.float32))
    right = _make_image(np.array([[3.0, 4.0]], dtype=np.float32))

    result = ImageCalculator().run({"a": left, "b": right}, BlockConfig(params={}))

    assert np.allclose(result["result"]._data, np.array([[4.0, 6.0]], dtype=np.float32))


def test_image_calculator_custom_expression_subtracts() -> None:
    left = _make_image(np.array([[5.0, 7.0]], dtype=np.float32))
    right = _make_image(np.array([[2.0, 3.0]], dtype=np.float32))

    result = ImageCalculator().run({"a": left, "b": right}, BlockConfig(params={"expression": "a - b"}))

    assert np.allclose(result["result"]._data, np.array([[3.0, 4.0]], dtype=np.float32))


def test_image_calculator_fret_ratio_expression() -> None:
    left = _make_image(np.array([[6.0, 8.0]], dtype=np.float32))
    right = _make_image(np.array([[2.0, 4.0]], dtype=np.float32))

    result = ImageCalculator().run(
        {"a": left, "b": right},
        BlockConfig(params={"expression": "(a - b) / (a + b)"}),
    )

    expected = (left._data - right._data) / (left._data + right._data)
    assert np.allclose(result["result"]._data, expected)


def test_image_calculator_collection_broadcasts_length_one_side() -> None:
    left = Collection(items=[_make_image(np.ones((2, 2), dtype=np.float32))], item_type=Image)
    right = Collection(
        items=[
            _make_image(np.full((2, 2), 2.0, dtype=np.float32)),
            _make_image(np.full((2, 2), 3.0, dtype=np.float32)),
        ],
        item_type=Image,
    )

    result = ImageCalculator().run(
        {"a": left, "b": right},
        BlockConfig(params={"expression": "a * b"}),
    )

    assert result["result"].length == 2
    assert np.array_equal(result["result"][0]._data, np.full((2, 2), 2.0, dtype=np.float32))
    assert np.array_equal(result["result"][1]._data, np.full((2, 2), 3.0, dtype=np.float32))


def test_image_calculator_invalid_variable_raises() -> None:
    left = _make_image(np.ones((2, 2), dtype=np.float32))
    right = _make_image(np.ones((2, 2), dtype=np.float32))

    with pytest.raises(ValueError, match="unknown variable"):
        ImageCalculator().run({"a": left, "b": right}, BlockConfig(params={"expression": "a + c"}))


def test_image_calculator_function_call_raises() -> None:
    left = _make_image(np.ones((2, 2), dtype=np.float32))
    right = _make_image(np.ones((2, 2), dtype=np.float32))

    with pytest.raises(ValueError, match="forbidden"):
        ImageCalculator().run({"a": left, "b": right}, BlockConfig(params={"expression": "max(a, b)"}))


def test_image_calculator_shape_mismatch_raises() -> None:
    left = _make_image(np.ones((2, 2), dtype=np.float32))
    right = _make_image(np.ones((3, 3), dtype=np.float32))

    with pytest.raises(ValueError, match="shape mismatch"):
        ImageCalculator().run({"a": left, "b": right}, BlockConfig(params={"expression": "a + b"}))


def test_image_calculator_rejects_non_string_expression() -> None:
    left = _make_image(np.ones((2, 2), dtype=np.float32))
    right = _make_image(np.ones((2, 2), dtype=np.float32))

    with pytest.raises(ValueError, match="string"):
        ImageCalculator().run({"a": left, "b": right}, BlockConfig(params={"expression": 123}))
