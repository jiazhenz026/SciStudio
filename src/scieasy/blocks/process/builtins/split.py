"""SplitBlock — filter, subset, train-test split."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pyarrow as pa

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.blocks.process.utils import to_arrow
from scieasy.core.types.dataframe import DataFrame

if TYPE_CHECKING:
    from scieasy.core.types.collection import Collection


class SplitBlock(ProcessBlock):
    """Filter, subset, or split input data.

    Config params:
        mode: "filter" (column-based filter), "head" (first N rows),
              or "ratio" (train-test split).  Default: "head".
        n: Number of rows for "head" mode.  Default: 100.
        ratio: Fraction for the first split in "ratio" mode.  Default: 0.8.
        column: Column name for "filter" mode.
        value: Value to match for "filter" mode.
    """

    name: ClassVar[str] = "Split"
    algorithm: ClassVar[str] = "split"
    description: ClassVar[str] = "Filter, subset, or split tabular data"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[DataFrame], description="Input table"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="out", accepted_types=[DataFrame], description="Primary output"),
        OutputPort(name="remainder", accepted_types=[DataFrame], required=False, description="Complement (ratio mode)"),
    ]

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Split the input DataFrame.

        Accepts both raw DataFrame and Collection[DataFrame] inputs for
        backward compatibility during the ADR-020 transition.
        """
        from scieasy.core.types.collection import Collection

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

    from scieasy.core.storage.arrow_backend import ArrowBackend
    from scieasy.core.storage.flush_context import get_output_dir
    from scieasy.core.storage.ref import StorageReference

    result = DataFrame(columns=table.column_names, row_count=table.num_rows)
    output_dir = get_output_dir()
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="scieasy_split_")
    ref = StorageReference(backend="arrow", path=str(Path(output_dir) / f"{uuid.uuid4()}.parquet"))
    backend = ArrowBackend()
    result._storage_ref = backend.write(table, ref)
    return result
