"""Process block utilities — shared helpers for process builtins."""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from scistudio.core.types.dataframe import DataFrame


def to_arrow(obj: Any) -> pa.Table:
    """Extract an Arrow Table from a DataFrame or raw Table.

    ViewProxy and ``_arrow_table`` backdoor removed.
    All data access routes through ``get_in_memory_data()`` ->
    ``to_memory()`` -> storage backend.

    Internal: process-builtins helper; the canonical author path to
    the Arrow form is ``DataFrame.to_memory()``. Not part of the public surface.
    """
    # Development references: ADR-031, ADR-052.
    if isinstance(obj, pa.Table):
        return obj
    if isinstance(obj, DataFrame):
        return obj.get_in_memory_data()
    raise TypeError(f"Cannot extract Arrow Table from {type(obj).__name__}")
