"""Process block utilities — shared helpers for process builtins."""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from scistudio.core.types.dataframe import DataFrame


def to_arrow(obj: Any) -> pa.Table:
    """Extract an Arrow Table from a DataFrame or raw Table.

    ADR-031 D2/D3: ViewProxy and ``_arrow_table`` backdoor removed.
    All data access routes through ``get_in_memory_data()`` ->
    ``to_memory()`` -> storage backend.
    """
    if isinstance(obj, pa.Table):
        return obj
    if isinstance(obj, DataFrame):
        return obj.get_in_memory_data()
    raise TypeError(f"Cannot extract Arrow Table from {type(obj).__name__}")
