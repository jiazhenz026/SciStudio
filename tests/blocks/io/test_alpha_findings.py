"""Engine round-trip findings surfaced by the alpha IO suite.

These were originally tracked as strict xfails (FIND-A/B/D) so each defect
stayed visible until fixed. The underlying defects are now fixed under #1740,
so every test asserts the correct round-trip behaviour and is retained as a
regression guard. See the alpha test-suite FINDINGS registry for the original
defect write-ups.

Scope: core ``LoadData`` / ``SaveData`` only (no plugin scan).
FIND-A / FIND-B are also exercised in the coverage matrix
(``test_io_coverage_matrix.py``), which no longer marks those slots broken.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyarrow as pa

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


def test_find_a_composite_json_roundtrips(tmp_path: Path) -> None:
    """A core ``CompositeData`` should round-trip through its only IO format."""
    sub = Array(axes=["x"], shape=(3,), dtype="float64", data=np.array([1.0, 2.0, 3.0]))
    comp = CompositeData(slots={"array_slot": sub})
    path = materialise_to_file(comp, tmp_path, ".json", filename_stem="c", registry=REG)
    back = reconstruct_from_file(path, CompositeData, registry=REG)
    assert isinstance(back, CompositeData)
    np.testing.assert_array_equal(np.asarray(back.get("array_slot").to_memory()), np.array([1.0, 2.0, 3.0]))


def test_find_b_dataframe_pickle_roundtrips(tmp_path: Path) -> None:
    """``DataFrame`` ``.pkl`` (allow_pickle) should reload to a DataFrame."""
    df = DataFrame(columns=["a"], row_count=3, data=pa.table({"a": [1, 2, 3]}))
    params = {"path": str(tmp_path / "df.pkl"), "core_type": "DataFrame", "allow_pickle": True}
    SaveData(config={"params": params}).save(df, BlockConfig(params=params))
    back = LoadData(config={"params": params}).load(BlockConfig(params=params))
    if hasattr(back, "items") and not isinstance(back, DataFrame):
        back = next(iter(back))
    assert isinstance(back, DataFrame)


def test_find_d_array_zarr_preserves_shape_metadata(tmp_path: Path) -> None:
    """Reloading an ``Array`` from ``.zarr`` should restore ``shape``/``axes``."""
    data = np.arange(12, dtype=np.float64).reshape(3, 4)
    src = Array(axes=["y", "x"], shape=(3, 4), dtype="float64", data=data)
    path = materialise_to_file(src, tmp_path, ".zarr", filename_stem="a", registry=REG)
    back = reconstruct_from_file(path, Array, registry=REG)
    assert back.shape == (3, 4)
    assert back.axes == ["y", "x"]
