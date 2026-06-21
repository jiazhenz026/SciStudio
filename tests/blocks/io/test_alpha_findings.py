"""Engine round-trip findings surfaced by the alpha IO suite — tracked as
strict xfails so each defect stays visible and a fix is detected.

Every test here asserts the *correct* (post-fix) behaviour and is marked
``xfail(strict=True)``: it shows as ``xfailed`` while the bug exists, and
turns into a hard ``xpass`` failure the moment the engine is fixed —
prompting removal of the marker (and the matching workaround in
``test_io_coverage_matrix.py`` / the generator). See
``~/Desktop/scistudio-tests/alpha-test-suite/FINDINGS.md``.

Scope: core ``LoadData`` / ``SaveData`` only (no plugin scan).
FIND-A / FIND-B are also exercised as xfails in the coverage matrix; they
are restated here so this file is the single registry of engine defects.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.io.loaders.load_data import LoadData
from scistudio.blocks.io.savers.save_data import SaveData
from scistudio.blocks.registry import BlockRegistry, _spec_from_class
from scistudio.core.types.array import Array
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.engine.materialisation import materialise_to_file, reconstruct_from_file


def _core_registry() -> BlockRegistry:
    reg = BlockRegistry()
    reg._register_spec(_spec_from_class(LoadData, source="alpha-findings"))
    reg._register_spec(_spec_from_class(SaveData, source="alpha-findings"))
    return reg


REG = _core_registry()


@pytest.mark.xfail(strict=True, reason="FIND-A: composite .json saver writes slot key 'file', loader reads 'path'")
def test_find_a_composite_json_roundtrips(tmp_path: Path) -> None:
    """A core ``CompositeData`` should round-trip through its only IO format."""
    sub = Array(axes=["x"], shape=(3,), dtype="float64", data=np.array([1.0, 2.0, 3.0]))
    comp = CompositeData(slots={"array_slot": sub})
    path = materialise_to_file(comp, tmp_path, ".json", filename_stem="c", registry=REG)
    back = reconstruct_from_file(path, CompositeData, registry=REG)
    assert isinstance(back, CompositeData)


@pytest.mark.xfail(strict=True, reason="FIND-B: tabular pickle saves the Arrow Table, loader expects the object")
def test_find_b_dataframe_pickle_roundtrips(tmp_path: Path) -> None:
    """``DataFrame`` ``.pkl`` (allow_pickle) should reload to a DataFrame."""
    df = DataFrame(columns=["a"], row_count=3, data=pa.table({"a": [1, 2, 3]}))
    params = {"path": str(tmp_path / "df.pkl"), "core_type": "DataFrame", "allow_pickle": True}
    SaveData(config={"params": params}).save(df, BlockConfig(params=params))
    back = LoadData(config={"params": params}).load(BlockConfig(params=params))
    if hasattr(back, "items") and not isinstance(back, DataFrame):
        back = next(iter(back))
    assert isinstance(back, DataFrame)


@pytest.mark.xfail(strict=True, reason="FIND-D: Array .zarr reload restores data but drops shape/axes metadata")
def test_find_d_array_zarr_preserves_shape_metadata(tmp_path: Path) -> None:
    """Reloading an ``Array`` from ``.zarr`` should restore ``shape``/``axes``."""
    data = np.arange(12, dtype=np.float64).reshape(3, 4)
    src = Array(axes=["y", "x"], shape=(3, 4), dtype="float64", data=data)
    path = materialise_to_file(src, tmp_path, ".zarr", filename_stem="a", registry=REG)
    back = reconstruct_from_file(path, Array, registry=REG)
    assert back.shape == (3, 4)
    assert back.axes == ["y", "x"]
