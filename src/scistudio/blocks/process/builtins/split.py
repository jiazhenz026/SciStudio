"""SplitBlock — filter, subset, train-test split."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pyarrow as pa

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.blocks.process.utils import to_arrow
from scistudio.core.types.dataframe import DataFrame

if TYPE_CHECKING:
    from scistudio.core.types.collection import Collection


class SplitBlock(ProcessBlock):
    """Take a slice of a table, or split it into two.

    Reduces one table to a smaller one, or divides it into a primary part and
    a remainder. Use it to keep the first N rows, hold out a fraction for a
    train/test split, or keep only the rows whose column matches a value.

    Ports: reads one table on ``data`` and emits the result on ``out``; in
    ``"ratio"`` mode it also emits the held-out rows on the optional
    ``remainder`` port. Config:

    - ``mode`` -- ``"head"`` (the default) keeps the first ``n`` rows,
      ``"ratio"`` splits into two parts at ``ratio``, ``"filter"`` keeps rows
      where ``column`` equals ``value``.
    - ``n`` -- row count for ``"head"`` mode (default ``100``).
    - ``ratio`` -- fraction kept in the first part for ``"ratio"`` mode
      (default ``0.8``); the rest goes to ``remainder``.
    - ``column`` / ``value`` -- the column to test and the value to match for
      ``"filter"`` mode.

    Example:
        >>> block = SplitBlock({"mode": "head", "n": 10})
    """

    name: ClassVar[str] = "Split"
    """Display name shown in the block palette and on the canvas node."""

    algorithm: ClassVar[str] = "split"
    """Stable identifier for this block's transform; recorded in metadata."""

    description: ClassVar[str] = "Filter, subset, or split tabular data"
    """One-line summary shown in the palette and node tooltip."""

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[DataFrame], description="Input table"),
    ]
    """The single input port ``data``, accepting a DataFrame."""

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="out", accepted_types=[DataFrame], description="Primary output"),
        OutputPort(name="remainder", accepted_types=[DataFrame], required=False, description="Complement (ratio mode)"),
    ]
    """The output ports: ``out`` (always emitted) and the optional
    ``remainder`` (only in ``"ratio"`` mode), each carrying a DataFrame.
    """

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Slice or split the input table according to ``mode``.

        The input may arrive either as a raw DataFrame or as a length-one
        Collection wrapping one; a Collection is unwrapped before processing.

        Args:
            inputs: Mapping with ``data``, a DataFrame or a Collection holding
                one DataFrame.
            config: The block configuration. ``mode`` selects the operation
                (defaults to ``"head"``); the remaining fields are read per
                mode (see the class docstring).

        Returns:
            Mapping of ``out`` to the result Collection. In ``"ratio"`` mode it
            also includes ``remainder`` with the held-out rows.

        Raises:
            TypeError: If the input does not resolve to an Arrow table.
            ValueError: If ``mode`` is ``"filter"`` without ``column`` and
                ``value``, or if ``mode`` is not one of the supported values.
        """
        from scistudio.core.types.collection import Collection

        data_obj = inputs["data"]

        # ADR-020: Unpack Collection input if present.
        if isinstance(data_obj, Collection):
            data_obj = self.unpack_single(data_obj)
        data = to_arrow(data_obj)

        if not isinstance(data, pa.Table):
            raise TypeError(f"Expected Arrow Table, got {type(data).__name__}")

        mode = config.get("mode", "head")

        if mode == "head":
            n = int(config.get("n", 100))
            out_table = data.slice(0, n)
            result = _persist_arrow_result(out_table)
            return {"out": Collection([result], item_type=DataFrame)}

        elif mode == "ratio":
            ratio = float(config.get("ratio", 0.8))
            split_idx = int(data.num_rows * ratio)
            first = data.slice(0, split_idx)
            second = data.slice(split_idx)
            r1 = _persist_arrow_result(first)
            r2 = _persist_arrow_result(second)
            return {
                "out": Collection([r1], item_type=DataFrame),
                "remainder": Collection([r2], item_type=DataFrame),
            }

        elif mode == "filter":
            column = config.get("column")
            value = config.get("value")
            if column is None or value is None:
                raise ValueError("Filter mode requires 'column' and 'value' in config")
            import pyarrow.compute as pc

            mask = pc.equal(data.column(column), pa.scalar(value))  # type: ignore[attr-defined]  # see #685
            filtered = data.filter(mask)
            result = _persist_arrow_result(filtered)
            return {"out": Collection([result], item_type=DataFrame)}

        else:
            raise ValueError(f"Unknown split mode: {mode}")


def _persist_arrow_result(table: pa.Table) -> DataFrame:
    """Create a DataFrame and persist the Arrow table to storage.

    ADR-031 D3: replaces the former ``result._arrow_table = table``
    pattern. The DataFrame is persisted to Arrow/Parquet storage and
    returned with ``storage_ref`` set.
    """
    import tempfile
    import uuid
    from pathlib import Path

    from scistudio.core.storage.arrow_backend import ArrowBackend
    from scistudio.core.storage.flush_context import get_output_dir
    from scistudio.core.storage.ref import StorageReference

    result = DataFrame(columns=table.column_names, row_count=table.num_rows)
    output_dir = get_output_dir()
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="scistudio_split_")
    ref = StorageReference(backend="arrow", path=str(Path(output_dir) / f"{uuid.uuid4()}.parquet"))
    backend = ArrowBackend()
    result._storage_ref = backend.write(table, ref)
    return result
