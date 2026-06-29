"""Per-item transform over a batch — a ProcessBlock example.

``NormalizeColumns`` rescales every numeric column of each table to the
0..1 range (min-max normalization). It is a ``ProcessBlock`` because every
table is transformed independently and the number of tables does not change.

Copy this file into ``blocks/`` in your project and edit it.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pyarrow as pa

from scistudio.blocks.process import ProcessBlock
from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.core.types import DataFrame


class NormalizeColumns(ProcessBlock):
    """Rescale each numeric column of every table to the 0..1 range."""

    name: ClassVar[str] = "Normalize Columns"
    description: ClassVar[str] = "Min-max normalize every numeric column of each table."

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[DataFrame], description="Table to normalize"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[DataFrame], description="Normalized table"),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            # Leave epsilon alone unless a constant column gives you divide-by-zero.
            "epsilon": {"type": "number", "default": 1e-12, "title": "Zero-range guard"},
        },
    }

    def process_item(self, item: DataFrame, config: BlockConfig, state: Any = None) -> DataFrame:
        epsilon = config.get("epsilon", 1e-12)

        # to_pandas() is the ergonomic accessor: the table is stored as Arrow,
        # but pandas is easier to work with for column maths.
        df = item.to_pandas()

        numeric = df.select_dtypes(include="number").columns
        for col in numeric:
            lo, hi = df[col].min(), df[col].max()
            df[col] = (df[col] - lo) / max(hi - lo, epsilon)

        # Build a DataFrame back from an Arrow table (the canonical form).
        return DataFrame(data=pa.Table.from_pandas(df, preserve_index=False))
