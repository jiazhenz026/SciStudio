"""Tests for the example blocks and package entry-point."""

from __future__ import annotations

import numpy as np

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.array import Array
from scistudio.testing import BlockTestHarness


class TestEntryPoint:
    """Validate the package entry-point callable."""

    def test_entry_point_validates(self):
        from my_blocks import get_block_package

        harness = BlockTestHarness(Block)
        result = get_block_package()
        errors = harness.validate_entry_point_callable(result)
        assert not errors, "\n".join(errors)

    def test_types_registered(self):
        from my_blocks import get_types

        types = get_types()
        assert len(types) > 0
        for t in types:
            assert isinstance(t, type)


class TestGaussianBlur:
    def test_contract(self):
        from my_blocks.blocks.gaussian_blur import GaussianBlur

        harness = BlockTestHarness(GaussianBlur)
        errors = harness.validate_block()
        assert not errors, errors

    def test_blur_reduces_noise(self):
        from my_blocks.blocks.gaussian_blur import GaussianBlur

        # Create noisy image
        rng = np.random.default_rng(42)
        data = rng.standard_normal((64, 64)).astype(np.float32)
        item = Array(axes=["y", "x"], shape=data.shape, dtype=str(data.dtype))
        item._data = data  # type: ignore[attr-defined]

        block = GaussianBlur()
        result = block.process_item(item, BlockConfig(sigma=2.0))

        # Blurred result should have lower variance
        assert result._data.std() < data.std()  # type: ignore[attr-defined]


class TestSimpleThreshold:
    def test_contract(self):
        from my_blocks.blocks.threshold import SimpleThreshold

        harness = BlockTestHarness(SimpleThreshold)
        errors = harness.validate_block()
        assert not errors, errors

    def test_manual_threshold(self):
        from my_blocks.blocks.threshold import SimpleThreshold

        data = np.array([[10, 200], [50, 150]], dtype=np.float32)
        item = Array(axes=["y", "x"], shape=data.shape, dtype=str(data.dtype))
        item._data = data  # type: ignore[attr-defined]

        block = SimpleThreshold()
        result = block.process_item(item, BlockConfig(method="manual", value=100.0))

        expected = np.array([[False, True], [False, True]])
        np.testing.assert_array_equal(result._data, expected)  # type: ignore[attr-defined]
