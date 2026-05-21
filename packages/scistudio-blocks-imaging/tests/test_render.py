"""Tests for imaging visualization blocks."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import numpy as np
import pytest
from scistudio_blocks_imaging.types import Image, Label, Mask
from scistudio_blocks_imaging.visualization.render import (
    RenderHistogram,
    RenderMontage,
    RenderMovie,
    RenderOverlay,
    RenderPseudoColor,
)

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.array import Array


def _make_image(arr: np.ndarray, axes: list[str] | None = None) -> Image:
    image = Image(axes=axes or ["y", "x"], shape=arr.shape, dtype=arr.dtype)
    image._data = arr  # type: ignore[attr-defined]
    return image


def _make_mask(arr: np.ndarray, axes: list[str] | None = None) -> Mask:
    mask = Mask(axes=axes or ["y", "x"], shape=arr.shape, dtype=bool)
    mask._data = arr.astype(bool)  # type: ignore[attr-defined]
    return mask


def _make_label(arr: np.ndarray, axes: list[str] | None = None) -> Label:
    raster = Array(axes=axes or ["y", "x"], shape=arr.shape, dtype=arr.dtype)
    raster._data = arr  # type: ignore[attr-defined]
    return Label(slots={"raster": raster})


def test_render_pseudo_color_returns_png_artifact() -> None:
    pytest.importorskip("matplotlib")
    image = _make_image(np.arange(16, dtype=np.float32).reshape(4, 4))

    artifact = RenderPseudoColor().process_item(image, BlockConfig(params={"lut": "viridis"}))

    assert artifact.mime_type == "image/png"
    assert artifact.file_path is not None
    assert artifact.file_path.exists()
    assert artifact.file_path.suffix == ".png"


def test_render_pseudo_color_invalid_lut_raises() -> None:
    pytest.importorskip("matplotlib")
    image = _make_image(np.arange(16, dtype=np.float32).reshape(4, 4))

    with pytest.raises(ValueError, match="unknown LUT"):
        RenderPseudoColor().process_item(image, BlockConfig(params={"lut": "not-a-real-map"}))


def test_render_overlay_mask_returns_png_artifact() -> None:
    pytest.importorskip("matplotlib")
    image = _make_image(np.arange(25, dtype=np.float32).reshape(5, 5))
    mask = _make_mask(np.eye(5, dtype=bool))

    result = RenderOverlay().run(
        {"image": image, "overlay": mask},
        BlockConfig(params={"alpha": 0.7, "outline_only": False}),
    )

    artifact = result["artifact"]
    assert artifact.mime_type == "image/png"
    assert artifact.file_path is not None
    assert artifact.file_path.exists()


def test_render_overlay_label_outline_returns_png_artifact() -> None:
    pytest.importorskip("matplotlib")
    image = _make_image(np.arange(25, dtype=np.float32).reshape(5, 5))
    label = _make_label(np.array([[0, 0, 1, 1, 0]] * 5, dtype=np.int32))

    result = RenderOverlay().run(
        {"image": image, "overlay": label},
        BlockConfig(params={"alpha": 0.5, "outline_only": True}),
    )

    artifact = result["artifact"]
    assert artifact.file_path is not None
    assert artifact.file_path.exists()


def test_render_montage_returns_png_artifact() -> None:
    pytest.importorskip("matplotlib")
    image = _make_image(np.arange(3 * 4 * 4, dtype=np.float32).reshape(3, 4, 4), ["t", "y", "x"])

    artifact = RenderMontage().process_item(image, BlockConfig(params={"axis": "t", "ncols": 2}))

    assert artifact.mime_type == "image/png"
    assert artifact.file_path is not None
    assert artifact.file_path.exists()


def test_render_movie_writes_mp4(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    imageio = pytest.importorskip("imageio.v2")
    image = _make_image(np.arange(3 * 4 * 4, dtype=np.float32).reshape(3, 4, 4), ["t", "y", "x"])
    written: dict[str, object] = {}

    def _fake_mimwrite(path: Path, frames: list[np.ndarray], **kwargs: object) -> None:
        Path(path).write_bytes(b"fake-movie")
        written["path"] = Path(path)
        written["frames"] = frames
        written["kwargs"] = kwargs

    monkeypatch.setattr(imageio, "mimwrite", _fake_mimwrite)

    artifact = RenderMovie().process_item(image, BlockConfig(params={"fps": 12, "codec": "libx264"}))

    assert artifact.mime_type == "video/mp4"
    assert artifact.file_path is not None
    assert artifact.file_path.exists()
    assert written["path"] == artifact.file_path
    assert len(cast(list[np.ndarray], written["frames"])) == 3
    assert cast(dict[str, object], written["kwargs"])["fps"] == 12


def test_render_histogram_svg_output() -> None:
    pytest.importorskip("matplotlib")
    image = _make_image(np.arange(64, dtype=np.float32).reshape(8, 8))

    artifact = RenderHistogram().process_item(image, BlockConfig(params={"bins": 16, "format": "svg"}))

    assert artifact.mime_type == "image/svg+xml"
    assert artifact.file_path is not None
    assert artifact.file_path.exists()
    assert artifact.file_path.suffix == ".svg"
