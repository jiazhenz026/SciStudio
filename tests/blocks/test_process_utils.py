"""Tests for process block utilities — to_arrow()."""

from __future__ import annotations

import pyarrow as pa
import pytest

from scistudio.blocks.process.utils import to_arrow
from scistudio.core.types.dataframe import DataFrame


class TestToArrow:
    """to_arrow — extract Arrow Table from various input types.

    ADR-031 D2/D3: ViewProxy and _arrow_table backdoor removed.
    All DataFrame data access routes through get_in_memory_data().
    """

    def test_from_arrow_table_passthrough(self) -> None:
        table = pa.table({"a": [1, 2, 3]})
        result = to_arrow(table)
        assert result is table

    def test_from_dataframe_with_storage_ref(self, tmp_path: pytest.TempPathFactory) -> None:
        """DataFrame with storage_ref returns Arrow table via get_in_memory_data."""
        from scistudio.core.storage.arrow_backend import ArrowBackend
        from scistudio.core.storage.ref import StorageReference

        table = pa.table({"x": [10, 20]})
        backend = ArrowBackend()
        ref = StorageReference(backend="arrow", path=str(tmp_path / "test.parquet"))
        written_ref = backend.write(table, ref)

        df = DataFrame(columns=["x"], row_count=2, storage_ref=written_ref)
        result = to_arrow(df)
        assert isinstance(result, pa.Table)
        assert result.column("x").to_pylist() == [10, 20]

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(TypeError, match="Cannot extract Arrow Table"):
            to_arrow("not a table")
