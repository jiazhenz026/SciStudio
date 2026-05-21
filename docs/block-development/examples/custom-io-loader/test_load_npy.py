"""Tests for the LoadNpy example block."""

from __future__ import annotations

import numpy as np
import pytest
from load_npy import LoadNpy

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.array import Array
from scistudio.testing import BlockTestHarness


class TestLoadNpyContract:
    def test_validate_block(self):
        harness = BlockTestHarness(LoadNpy)
        errors = harness.validate_block()
        assert not errors, errors


class TestLoadNpyLogic:
    def test_load_2d(self, tmp_path):
        data = np.random.rand(64, 64).astype(np.float32)
        path = tmp_path / "test.npy"
        np.save(str(path), data)

        block = LoadNpy()
        config = BlockConfig(path=str(path))
        output_dir = str(tmp_path / "zarr_out")
        result = block._load_simple(path, config, output_dir)

        assert isinstance(result, Array)
        assert result.axes == ["y", "x"]
        assert result.shape == (64, 64)
        assert result.storage_ref is not None
        np.testing.assert_array_equal(result.to_memory(), data)

    def test_load_3d_with_axes_override(self, tmp_path):
        data = np.random.rand(3, 64, 64).astype(np.float32)
        path = tmp_path / "test.npy"
        np.save(str(path), data)

        block = LoadNpy()
        config = BlockConfig(path=str(path), axes="cyx")
        output_dir = str(tmp_path / "zarr_out")
        result = block._load_simple(path, config, output_dir)

        assert result.axes == ["c", "y", "x"]
        assert result.storage_ref is not None

    def test_file_not_found(self, tmp_path):
        block = LoadNpy()
        config = BlockConfig(path=str(tmp_path / "nonexistent.npy"))
        with pytest.raises(FileNotFoundError):
            block.load(config)

    def test_wrong_extension(self, tmp_path):
        path = tmp_path / "test.csv"
        path.write_text("a,b\n1,2\n")
        block = LoadNpy()
        config = BlockConfig(path=str(path))
        with pytest.raises(ValueError, match=r"expected \.npy"):
            block.load(config)
