"""Tests for ADR-031 Addendum 2: _transient_data slot + typed data= constructor.

Verifies:
1. Array(data=...) sets _transient_data
2. DataFrame(data=...) sets _transient_data
3. Series(data=...) sets _transient_data
4. obj._data = arr (backward compat bridge) writes _transient_data
5. df._arrow_table = table (backward compat bridge) writes _transient_data
6. get_in_memory_data() returns _transient_data when storage_ref is None
7. to_memory() returns _transient_data when storage_ref is None (Array)
8. _serialise_one(obj_with_transient_data_and_storage_ref) excludes _transient_data
9. _reconstruct_one(wire) produces _transient_data=None
10. No hasattr(self, "_data") / hasattr(self, "_arrow_table") in base.py/array.py
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest

from scistudio.core.types.array import Array
from scistudio.core.types.base import DataObject
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series

# ---------------------------------------------------------------------------
# 1. Array(data=...) sets _transient_data
# ---------------------------------------------------------------------------


class TestArrayDataConstructor:
    def test_array_data_parameter_sets_transient(self):
        arr = np.zeros((100, 100), dtype="float32")
        obj = Array(axes=["y", "x"], shape=(100, 100), dtype="float32", data=arr)
        assert obj._transient_data is arr

    def test_array_data_none_leaves_transient_none(self):
        obj = Array(axes=["y", "x"], shape=(100, 100), dtype="float32")
        assert obj._transient_data is None


# ---------------------------------------------------------------------------
# 2. DataFrame(data=...) sets _transient_data
# ---------------------------------------------------------------------------


class TestDataFrameDataConstructor:
    def test_dataframe_data_parameter_sets_transient(self):
        table = pa.table({"a": [1, 2, 3]})
        obj = DataFrame(data=table)
        assert obj._transient_data is table

    def test_dataframe_data_none_leaves_transient_none(self):
        obj = DataFrame()
        assert obj._transient_data is None


# ---------------------------------------------------------------------------
# 3. Series(data=...) sets _transient_data
# ---------------------------------------------------------------------------


class TestSeriesDataConstructor:
    def test_series_data_parameter_sets_transient(self):
        table = pa.table({"col": [1, 2, 3]})
        obj = Series(data=table)
        assert obj._transient_data is table

    def test_series_data_none_leaves_transient_none(self):
        obj = Series()
        assert obj._transient_data is None


# ---------------------------------------------------------------------------
# 4. obj._data = arr (backward compat bridge) writes _transient_data
# ---------------------------------------------------------------------------


class TestDataPropertyBridge:
    def test_data_setter_writes_transient(self):
        obj = Array(axes=["y", "x"], shape=(10, 10), dtype="float32")
        arr = np.ones((10, 10))
        obj._data = arr
        assert obj._transient_data is arr

    def test_data_getter_reads_transient(self):
        arr = np.ones((10, 10))
        obj = Array(axes=["y", "x"], shape=(10, 10), dtype="float32", data=arr)
        assert obj._data is arr

    def test_data_bridge_on_base_dataobject(self):
        obj = DataObject()
        obj._data = "sentinel"
        assert obj._transient_data == "sentinel"
        assert obj._data == "sentinel"


# ---------------------------------------------------------------------------
# 5. df._arrow_table = table (backward compat bridge) writes _transient_data
# ---------------------------------------------------------------------------


class TestArrowTablePropertyBridge:
    def test_arrow_table_setter_writes_transient(self):
        df = DataFrame()
        table = pa.table({"x": [1, 2]})
        df._arrow_table = table
        assert df._transient_data is table

    def test_arrow_table_getter_reads_transient(self):
        table = pa.table({"x": [1, 2]})
        df = DataFrame(data=table)
        assert df._arrow_table is table

    def test_arrow_table_bridge_on_series(self):
        s = Series()
        table = pa.table({"col": [1]})
        s._arrow_table = table
        assert s._transient_data is table
        assert s._arrow_table is table


# ---------------------------------------------------------------------------
# 6. get_in_memory_data() returns _transient_data when storage_ref is None
# ---------------------------------------------------------------------------


class TestGetInMemoryData:
    def test_returns_transient_data_when_no_storage_ref(self):
        arr = np.zeros((5, 5))
        obj = Array(axes=["y", "x"], shape=(5, 5), dtype="float64", data=arr)
        assert obj.get_in_memory_data() is arr

    def test_raises_when_no_transient_and_no_storage_ref(self):
        obj = Array(axes=["y", "x"], shape=(5, 5), dtype="float64")
        with pytest.raises(ValueError, match="no in-memory data"):
            obj.get_in_memory_data()


# ---------------------------------------------------------------------------
# 7. Array.to_memory() returns _transient_data when storage_ref is None
# ---------------------------------------------------------------------------


class TestArrayToMemory:
    def test_returns_transient_data_when_no_storage_ref(self):
        arr = np.ones((3, 3))
        obj = Array(axes=["y", "x"], shape=(3, 3), dtype="float64", data=arr)
        assert obj.to_memory() is arr

    def test_raises_when_no_transient_and_no_storage_ref(self):
        obj = Array(axes=["y", "x"], shape=(3, 3), dtype="float64")
        with pytest.raises(ValueError, match="no storage reference"):
            obj.to_memory()


# ---------------------------------------------------------------------------
# 8. _serialise_one excludes _transient_data from wire format
# ---------------------------------------------------------------------------


class TestSerialiseExcludesTransient:
    def test_transient_data_not_in_wire_format(self, tmp_path: Path):
        """When an object has both storage_ref and _transient_data, the
        wire format must NOT contain _transient_data."""
        import zarr

        from scistudio.core.storage.ref import StorageReference
        from scistudio.core.types.serialization import _serialise_one

        arr = np.zeros((5, 5))
        zarr_path = str(tmp_path / "test.zarr")
        zarr.save(zarr_path, arr)

        obj = Array(
            axes=["y", "x"],
            shape=(5, 5),
            dtype="float64",
            data=arr,
            storage_ref=StorageReference(
                backend="zarr",
                path=zarr_path,
                metadata={"shape": [5, 5], "dtype": "float64"},
            ),
        )
        assert obj._transient_data is arr  # confirm it's set

        wire = _serialise_one(obj)
        # _transient_data must not appear anywhere in the wire dict
        assert "_transient_data" not in wire
        assert "_transient_data" not in wire.get("metadata", {})
        # Also check _data and _arrow_table are absent
        assert "_data" not in wire.get("metadata", {})
        assert "_arrow_table" not in wire.get("metadata", {})


# ---------------------------------------------------------------------------
# 9. _reconstruct_one produces _transient_data=None
# ---------------------------------------------------------------------------


class TestReconstructTransientIsNone:
    def test_reconstructed_object_has_none_transient(self, tmp_path: Path):
        import zarr

        from scistudio.core.types.serialization import _reconstruct_one, _serialise_one

        arr = np.zeros((4, 4))
        zarr_path = str(tmp_path / "test.zarr")
        zarr.save(zarr_path, arr)

        from scistudio.core.storage.ref import StorageReference

        obj = Array(
            axes=["y", "x"],
            shape=(4, 4),
            dtype="float64",
            storage_ref=StorageReference(
                backend="zarr",
                path=zarr_path,
                metadata={"shape": [4, 4], "dtype": "float64"},
            ),
        )
        wire = _serialise_one(obj)
        reconstructed = _reconstruct_one(wire)
        assert reconstructed._transient_data is None


# ---------------------------------------------------------------------------
# 10. No hasattr(self, "_data") / hasattr(self, "_arrow_table") in source
# ---------------------------------------------------------------------------


class TestNoHasattrPatterns:
    """Static analysis: ensure no hasattr probing for _data/_arrow_table
    remains in base.py or array.py."""

    @staticmethod
    def _check_no_hasattr(filepath: Path, attr_name: str) -> list[int]:
        """Return line numbers where hasattr(self, attr_name) appears."""
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
        violations: list[int] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "hasattr"
                and len(node.args) >= 2
            ):
                second = node.args[1]
                if isinstance(second, ast.Constant) and second.value == attr_name:
                    violations.append(node.lineno)
        return violations

    def test_no_hasattr_data_in_base(self):
        base_path = Path(__file__).resolve().parents[2] / "src" / "scistudio" / "core" / "types" / "base.py"
        violations = self._check_no_hasattr(base_path, "_data")
        assert violations == [], f"hasattr(self, '_data') found at lines {violations} in base.py"

    def test_no_hasattr_arrow_table_in_base(self):
        base_path = Path(__file__).resolve().parents[2] / "src" / "scistudio" / "core" / "types" / "base.py"
        violations = self._check_no_hasattr(base_path, "_arrow_table")
        assert violations == [], f"hasattr(self, '_arrow_table') found at lines {violations} in base.py"

    def test_no_hasattr_data_in_array(self):
        array_path = Path(__file__).resolve().parents[2] / "src" / "scistudio" / "core" / "types" / "array.py"
        violations = self._check_no_hasattr(array_path, "_data")
        assert violations == [], f"hasattr(self, '_data') found at lines {violations} in array.py"

    def test_no_hasattr_arrow_table_in_array(self):
        array_path = Path(__file__).resolve().parents[2] / "src" / "scistudio" / "core" / "types" / "array.py"
        violations = self._check_no_hasattr(array_path, "_arrow_table")
        assert violations == [], f"hasattr(self, '_arrow_table') found at lines {violations} in array.py"
