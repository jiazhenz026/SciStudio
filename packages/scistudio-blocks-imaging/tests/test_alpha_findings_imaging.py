"""Imaging/full-registry engine findings — tracked as strict xfails.

These need the imaging plugin importable, so they live in the package
suite (not collected by the core repo ``testpaths``). See
``~/Desktop/scistudio-tests/alpha-test-suite/FINDINGS.md``.

* FIND-E: ``Render Movie`` calls ``TiffWriter.write(..., fps=...)``;
  ``tifffile`` 2026 removed the ``fps`` kwarg, so the block raises.
* FIND-C: with a full (plugin) registry, ``reconstruct_from_file`` picks
  a sibling type by extension despite an explicit ``target_type`` —
  e.g. an ``Array`` saved to ``.zarr`` reloads as ``Image``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection
from scistudio.engine.materialisation import materialise_to_file, reconstruct_from_file


def _full_registry() -> BlockRegistry:
    reg = BlockRegistry()
    reg.scan(include_monorepo=True)
    return reg


@pytest.mark.xfail(strict=True, reason="FIND-E: Render Movie uses tifffile fps= kwarg removed in 2026")
def test_find_e_render_movie_runs(tmp_path: Path) -> None:
    pytest.importorskip("tifffile")
    reg = _full_registry()
    cls = BlockRegistry._resolve_class(reg._registry["Render Movie"])
    assert cls is not None
    arr = np.stack([(np.arange(64).reshape(8, 8) + k).astype(np.float32) for k in range(3)], axis=0)
    img = Image(axes=["t", "y", "x"], shape=arr.shape, dtype=str(arr.dtype))
    img._data = arr
    out = cls().run({"image": Collection(items=[img], item_type=Image)}, BlockConfig(params={}))
    assert any(len(list(coll)) for coll in out.values())


@pytest.mark.xfail(strict=True, reason="FIND-C: full-registry reconstruct picks Image for an Array .zarr")
def test_find_c_array_zarr_reconstructs_as_array(tmp_path: Path) -> None:
    reg = _full_registry()
    data = np.arange(12, dtype=np.float64).reshape(3, 4)
    src = Array(axes=["y", "x"], shape=(3, 4), dtype="float64", data=data)
    path = materialise_to_file(src, tmp_path, ".zarr", filename_stem="a", registry=reg)
    back = reconstruct_from_file(path, Array, registry=reg)
    # Image IS-A Array, so check the exact type: the bug returns an Image.
    assert type(back) is Array
