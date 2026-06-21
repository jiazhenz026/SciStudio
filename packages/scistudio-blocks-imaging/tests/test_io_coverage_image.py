"""Alpha IO load+save coverage matrix for the imaging ``Image`` type.

Exercises the full ``load_ext x save_ext`` matrix over the in-scope
image formats (vendor binaries .czi/.lif/.nd2/.oib/.oir are out of scope
for alpha) plus a 10-item collection round-trip via ``LoadImage``
multi-path loading.

Lossy formats (.jpg/.jpeg) are verified by shape (not exact pixels).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from scistudio_blocks_imaging.io.load_image import LoadImage
from scistudio_blocks_imaging.io.save_image import SaveImage
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig

# Lossless + lossy in-scope formats. Build a 2-D uint8 image so every
# format (incl. PNG/JPEG which require uint8) accepts it.
IMAGE_EXTS = [".tif", ".tiff", ".png", ".jpg", ".jpeg", ".zarr"]
LOSSLESS = {".tif", ".tiff", ".png", ".zarr"}


def _make_image(i: int = 0) -> Image:
    arr = (((np.arange(64) + i * 3) % 251).astype(np.uint8)).reshape(8, 8)
    img = Image(axes=["y", "x"], shape=arr.shape, dtype=str(arr.dtype))
    img._data = arr
    return img


def _save(img: Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    SaveImage().save(img, BlockConfig(params={"path": str(path)}))


def _load_one(path: Path) -> Image:
    result = LoadImage().load(BlockConfig(params={"path": str(path)}))
    return result[0]


@pytest.mark.parametrize("save_ext", IMAGE_EXTS)
@pytest.mark.parametrize("load_ext", IMAGE_EXTS)
def test_image_load_save_matrix(tmp_path: Path, load_ext: str, save_ext: str) -> None:
    src = _make_image()
    src_arr = np.asarray(src._data)

    # LOAD under test.
    in_path = tmp_path / f"in{load_ext}"
    _save(src, in_path)
    loaded = _load_one(in_path)

    # SAVE under test.
    out_path = tmp_path / f"out{save_ext}"
    _save(loaded, out_path)
    assert out_path.exists()
    if out_path.is_file():
        assert out_path.stat().st_size > 0
    else:  # .zarr store directory
        assert any(out_path.rglob("*"))

    # Reload and verify. Exact pixels only for lossless load+save chains.
    reloaded = _load_one(out_path)
    out_arr = np.asarray(reloaded.get_in_memory_data())
    assert out_arr.shape == src_arr.shape
    if load_ext in LOSSLESS and save_ext in LOSSLESS:
        np.testing.assert_array_equal(out_arr, src_arr)


@pytest.mark.parametrize("ext", IMAGE_EXTS)
def test_image_collection_roundtrip_10(tmp_path: Path, ext: str) -> None:
    paths: list[str] = []
    for i in range(10):
        p = tmp_path / f"img_{i:02d}{ext}"
        _save(_make_image(i), p)
        paths.append(str(p))
    result = LoadImage().load(BlockConfig(params={"path": paths}))
    items = list(result)
    assert len(items) == 10
    for item in items:
        assert isinstance(item, Image)
