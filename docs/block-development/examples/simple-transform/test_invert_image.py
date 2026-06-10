"""Tests for the InvertImage example block."""

from __future__ import annotations

import numpy as np
from invert_image import InvertImage

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.array import Array
from scistudio.testing import BlockTestHarness


class TestInvertImageContract:
    """Validate the block contract using BlockTestHarness."""

    def test_validate_block(self):
        harness = BlockTestHarness(InvertImage)
        errors = harness.validate_block()
        assert not errors, errors


class TestInvertImageLogic:
    """Unit-test the process_item logic directly."""

    def test_invert_uint8(self):
        data = np.array([[0, 100], [200, 255]], dtype=np.uint8)
        item = Array(axes=["y", "x"], shape=data.shape, dtype=str(data.dtype), data=data)

        block = InvertImage()
        result = block.process_item(item, BlockConfig())

        expected = np.array([[255, 155], [55, 0]], dtype=np.uint8)
        np.testing.assert_array_equal(result.to_memory(), expected)

    def test_invert_float(self):
        data = np.array([[0.0, 0.5], [0.75, 1.0]], dtype=np.float64)
        item = Array(axes=["y", "x"], shape=data.shape, dtype=str(data.dtype), data=data)

        block = InvertImage()
        result = block.process_item(item, BlockConfig())

        expected = np.array([[1.0, 0.5], [0.25, 0.0]], dtype=np.float64)
        np.testing.assert_array_almost_equal(result.to_memory(), expected)

    def test_preserves_axes(self):
        data = np.random.rand(3, 64, 64).astype(np.float32)
        item = Array(axes=["c", "y", "x"], shape=data.shape, dtype=str(data.dtype), data=data)

        block = InvertImage()
        result = block.process_item(item, BlockConfig())

        assert result.axes == ["c", "y", "x"]
        assert result.shape == (3, 64, 64)

    def test_preserves_user_metadata(self):
        data = np.zeros((8, 8), dtype=np.float32)
        item = Array(
            axes=["y", "x"],
            shape=data.shape,
            dtype=str(data.dtype),
            user={"experiment": "test-001"},
            data=data,
        )

        block = InvertImage()
        result = block.process_item(item, BlockConfig())

        assert result.user == {"experiment": "test-001"}
