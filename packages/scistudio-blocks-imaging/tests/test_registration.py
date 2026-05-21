"""Tests for imaging registration blocks."""

from __future__ import annotations

import numpy as np
import pytest
from scistudio_blocks_imaging.registration.apply_transform import ApplyTransform
from scistudio_blocks_imaging.registration.compute_registration import ComputeRegistration
from scistudio_blocks_imaging.registration.register_series import RegisterSeries
from scistudio_blocks_imaging.types import Image, Transform

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection


def _make_image(arr: np.ndarray, axes: list[str] | None = None) -> Image:
    axes = axes or ["y", "x"]
    image = Image(axes=axes, shape=arr.shape, dtype=arr.dtype)
    image._data = arr  # type: ignore[attr-defined]
    return image


def _make_transform(matrix: np.ndarray) -> Transform:
    transform = Transform(
        axes=["row", "col"],
        shape=tuple(matrix.shape),
        dtype=matrix.dtype,
        meta=Transform.Meta(transform_type="affine"),
    )
    transform._data = matrix  # type: ignore[attr-defined]
    return transform


def test_compute_registration_phase_correlation_recovers_translation() -> None:
    pytest.importorskip("skimage")
    fixed = np.zeros((32, 32), dtype=np.float32)
    fixed[10:18, 12:20] = 1.0
    moving = np.roll(fixed, shift=(3, -2), axis=(0, 1))

    result = ComputeRegistration().run(
        {
            "moving": Collection(items=[_make_image(moving)], item_type=Image),
            "fixed": Collection(items=[_make_image(fixed)], item_type=Image),
        },
        BlockConfig(params={"method": "phase_correlation"}),
    )

    transform = result["transform"][0]
    matrix = np.asarray(transform._data)
    assert matrix.shape == (2, 3)
    assert matrix[0, 2] == pytest.approx(2.0, abs=0.2)
    assert matrix[1, 2] == pytest.approx(-3.0, abs=0.2)
    assert transform.meta is not None
    assert transform.meta.transform_type == "phase_correlation"


@pytest.mark.parametrize(("method", "shape"), [("rigid", (3, 3)), ("affine", (3, 3))])
def test_compute_registration_rigid_and_affine_methods_return_transforms(method: str, shape: tuple[int, int]) -> None:
    pytest.importorskip("skimage")
    fixed = np.zeros((24, 24), dtype=np.float32)
    fixed[8:16, 8:16] = 1.0
    moving = np.roll(fixed, shift=(1, 1), axis=(0, 1))

    result = ComputeRegistration().run(
        {
            "moving": Collection(items=[_make_image(moving)], item_type=Image),
            "fixed": Collection(items=[_make_image(fixed)], item_type=Image),
        },
        BlockConfig(params={"method": method}),
    )

    transform = result["transform"][0]
    assert np.asarray(transform._data).shape == shape
    assert transform.meta is not None
    assert transform.meta.transform_type == method


def test_compute_registration_invalid_method_raises() -> None:
    with pytest.raises(ValueError, match="method"):
        ComputeRegistration().run(
            {
                "moving": Collection(items=[_make_image(np.zeros((8, 8), dtype=np.float32))], item_type=Image),
                "fixed": Collection(items=[_make_image(np.zeros((8, 8), dtype=np.float32))], item_type=Image),
            },
            BlockConfig(params={"method": "bogus"}),
        )


def test_apply_transform_translates_image() -> None:
    pytest.importorskip("skimage")
    arr = np.zeros((16, 16), dtype=np.float32)
    arr[6:10, 6:10] = 1.0
    image = _make_image(arr)
    transform = _make_transform(np.asarray([[1.0, 0.0, 2.0], [0.0, 1.0, -1.0]], dtype=np.float64))

    result = ApplyTransform().run(
        {
            "image": Collection(items=[image], item_type=Image),
            "transform": Collection(items=[transform], item_type=Transform),
        },
        BlockConfig(params={"interpolation": "nearest"}),
    )

    warped = np.asarray(result["warped"][0]._data)
    expected = np.zeros_like(arr)
    expected[5:9, 8:12] = 1.0
    assert np.array_equal(warped, expected)


def test_apply_transform_invalid_transform_shape_raises() -> None:
    pytest.importorskip("skimage")
    image = _make_image(np.zeros((8, 8), dtype=np.float32))
    broken = Transform(
        axes=["row", "col"],
        shape=(3, 3),
        dtype=np.float64,
        meta=Transform.Meta(transform_type="affine"),
    )
    broken._data = np.eye(4, dtype=np.float64)  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="shape"):
        ApplyTransform().run(
            {
                "image": Collection(items=[image], item_type=Image),
                "transform": Collection(items=[broken], item_type=Transform),
            },
            BlockConfig(params={"interpolation": "nearest"}),
        )


def test_register_series_aligns_frames_to_reference() -> None:
    pytest.importorskip("skimage")
    frame = np.zeros((24, 24), dtype=np.float32)
    frame[8:14, 9:15] = 1.0
    shifted = np.roll(frame, shift=(2, -3), axis=(0, 1))
    series = _make_image(np.stack([frame, shifted], axis=0), ["t", "y", "x"])

    result = RegisterSeries().run(
        {"series": Collection(items=[series], item_type=Image)},
        BlockConfig(params={"axis": "t", "reference_frame": 0, "method": "phase_correlation"}),
    )

    registered = np.asarray(result["registered"][0]._data)
    assert np.array_equal(registered[0], frame)
    assert np.array_equal(registered[1], frame)


def test_register_series_invalid_axis_raises() -> None:
    series = _make_image(np.zeros((2, 8, 8), dtype=np.float32), ["t", "y", "x"])

    with pytest.raises(ValueError, match="axis"):
        RegisterSeries().run(
            {"series": Collection(items=[series], item_type=Image)},
            BlockConfig(params={"axis": "c", "reference_frame": 0}),
        )
