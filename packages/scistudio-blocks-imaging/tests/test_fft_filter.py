"""T-IMG-016 FFTFilter impl tests."""

from __future__ import annotations

import importlib

import numpy as np
import pytest
from scistudio_blocks_imaging.morphology.fft_filter import FFTFilter
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig


def _make_image(arr: np.ndarray, axes: list[str]) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=arr.dtype)
    img._data = arr
    return img


def test_t_img_016_module_importable() -> None:
    importlib.import_module("scistudio_blocks_imaging.morphology.fft_filter")


def test_t_img_016_class_has_required_classvars() -> None:
    assert FFTFilter.type_name == "imaging.fft_filter"
    assert FFTFilter.name == "FFT Filter"
    assert FFTFilter.subcategory == "filter"
    assert "type" in FFTFilter.config_schema["properties"]


def test_fft_lowpass_2d() -> None:
    checker = (np.indices((32, 32)).sum(axis=0) % 2).astype(np.float32)
    out = FFTFilter().process_item(
        _make_image(checker, ["y", "x"]),
        BlockConfig(params={"type": "lowpass", "cutoff_high": 0.15}),
    )
    out_arr = np.asarray(out._data)
    assert out.shape == (32, 32)
    assert float(out_arr.std()) < float(checker.std())


def test_fft_invalid_type_raises() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float32), ["y", "x"])
    with pytest.raises(ValueError, match="unknown type"):
        FFTFilter().process_item(img, BlockConfig(params={"type": "nope"}))


def test_fft_bandpass_requires_ordered_cutoffs() -> None:
    img = _make_image(np.zeros((4, 4), dtype=np.float32), ["y", "x"])
    with pytest.raises(ValueError, match="cutoff_low"):
        FFTFilter().process_item(
            img,
            BlockConfig(params={"type": "bandpass", "cutoff_low": 0.7, "cutoff_high": 0.2}),
        )
