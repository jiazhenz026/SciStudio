"""Tests for broadcast_apply and iter_axis_slices (Phase 3.5)."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import ClassVar

import numpy as np
import pytest

from scistudio.utils.broadcast import BroadcastError, broadcast_apply, iter_axis_slices


@dataclass
class NamedArray:
    """Minimal array wrapper with named axes for testing."""

    data: np.ndarray  # type: ignore[type-arg]
    axes: ClassVar[list[str]]

    def __array__(self) -> np.ndarray:  # type: ignore[type-arg]
        return self.data


class Mask2D(NamedArray):
    """2D mask with (y, x) axes."""

    axes: ClassVar[list[str]] = ["y", "x"]


class Cube3D(NamedArray):
    """3D cube with (y, x, mz) axes."""

    axes: ClassVar[list[str]] = ["y", "x", "mz"]


# ---------------------------------------------------------------------------
# iter_axis_slices
# ---------------------------------------------------------------------------


class TestIterAxisSlices:
    """Test named-axis-aware slice generation."""

    def test_iterate_over_axis(self) -> None:
        data = np.arange(24).reshape(2, 3, 4)
        axes = ["y", "x", "ch"]
        slices = list(iter_axis_slices(data, axes, "ch"))
        assert len(slices) == 4
        for _idx, sl in slices:
            assert sl.shape == (2, 3)

    def test_iterate_first_axis(self) -> None:
        data = np.arange(12).reshape(3, 4)
        axes = ["row", "col"]
        slices = list(iter_axis_slices(data, axes, "row"))
        assert len(slices) == 3
        for _idx, sl in slices:
            assert sl.shape == (4,)

    def test_missing_axis_raises(self) -> None:
        data = np.arange(12).reshape(3, 4)
        with pytest.raises(BroadcastError, match="not found"):
            list(iter_axis_slices(data, ["y", "x"], "z"))


# ---------------------------------------------------------------------------
# broadcast_apply: 2D mask x 3D cube
# ---------------------------------------------------------------------------


class TestBroadcastApply:
    """Test broadcast_apply with named-axis arrays."""

    def test_2d_mask_times_3d_cube(self) -> None:
        """Apply a 2D mask (y, x) to each mz slice of a 3D cube (y, x, mz)."""
        mask = Mask2D(data=np.ones((4, 5), dtype="float64"))
        cube = Cube3D(data=np.arange(60, dtype="float64").reshape(4, 5, 3))

        results = broadcast_apply(
            source=mask,
            target=cube,
            func=lambda src, tgt: src * tgt,
            over_axes=["mz"],
        )

        assert len(results) == 3  # one per mz channel
        for r in results:
            assert r.shape == (4, 5)

    def test_result_values(self) -> None:
        """Verify actual computation: multiplying by a mask of 2s."""
        mask = Mask2D(data=np.full((2, 3), 2.0))
        cube = Cube3D(data=np.ones((2, 3, 4), dtype="float64"))

        results = broadcast_apply(
            source=mask,
            target=cube,
            func=lambda src, tgt: src * tgt,
            over_axes=["mz"],
        )

        for r in results:
            np.testing.assert_array_equal(r, np.full((2, 3), 2.0))

    def test_axis_mismatch_raises(self) -> None:
        """Source axes not a subset of target minus over_axes should fail."""

        @dataclass
        class WrongAxes(NamedArray):
            axes: ClassVar[list[str]] = ["z", "w"]  # Not in cube's remaining axes

        wrong = WrongAxes(data=np.zeros((2, 3)))
        cube = Cube3D(data=np.zeros((4, 5, 3)))

        with pytest.raises(BroadcastError, match="not a subset"):
            broadcast_apply(
                source=wrong,
                target=cube,
                func=lambda s, t: s + t,
                over_axes=["mz"],
            )

    def test_target_without_axes_raises(self) -> None:
        """Target must have named axes."""
        mask = Mask2D(data=np.ones((4, 5)))
        plain_array = np.zeros((4, 5, 3))

        with pytest.raises(BroadcastError, match="named axes"):
            broadcast_apply(
                source=mask,
                target=plain_array,
                func=lambda s, t: s + t,
                over_axes=["mz"],
            )

    def test_over_axis_not_in_target_raises(self) -> None:
        """over_axes must be in target's axis names."""
        mask = Mask2D(data=np.ones((4, 5)))
        cube = Cube3D(data=np.zeros((4, 5, 3)))

        with pytest.raises(BroadcastError, match="not found"):
            broadcast_apply(
                source=mask,
                target=cube,
                func=lambda s, t: s + t,
                over_axes=["nonexistent"],
            )

    def test_multiple_over_axes(self) -> None:
        """Iterate over two axes at once."""

        @dataclass
        class Data4D(NamedArray):
            axes: ClassVar[list[str]] = ["y", "x", "ch", "t"]

        @dataclass
        class Source1D(NamedArray):
            axes: ClassVar[list[str]] = ["y", "x"]

        src = Source1D(data=np.ones((3, 4)))
        tgt = Data4D(data=np.ones((3, 4, 2, 5)))

        results = broadcast_apply(
            source=src,
            target=tgt,
            func=lambda s, t: s + t,
            over_axes=["ch", "t"],
        )
        assert len(results) == 2 * 5  # 2 channels x 5 timepoints


# ---------------------------------------------------------------------------
# Memory guard
# ---------------------------------------------------------------------------


class TestMemoryGuard:
    """Test ResourceWarning for large combined input sizes."""

    def test_no_warning_for_small_arrays(self) -> None:
        """No ResourceWarning for arrays well under 2 GB."""
        source = Mask2D(data=np.zeros((10, 10)))
        target = Cube3D(data=np.zeros((10, 10, 3)))
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            broadcast_apply(source, target, lambda s, t: s + t, over_axes=["mz"])

    def test_warning_for_large_arrays(self) -> None:
        """ResourceWarning triggered when combined size > threshold."""
        import scistudio.utils.broadcast as bmod

        original = bmod._MEMORY_WARN_BYTES
        try:
            bmod._MEMORY_WARN_BYTES = 100  # 100 bytes for testing
            source = Mask2D(data=np.zeros((10, 10)))
            target = Cube3D(data=np.zeros((10, 10, 3)))
            with pytest.warns(ResourceWarning, match="broadcast_apply"):
                broadcast_apply(source, target, lambda s, t: s + t, over_axes=["mz"])
        finally:
            bmod._MEMORY_WARN_BYTES = original
