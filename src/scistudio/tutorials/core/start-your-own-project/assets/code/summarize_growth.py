"""A project-level block that summarises a growth run per culture.

The Learning Center writes this file into the tutorial project so the reader
never has to type it. It is ordinary SciStudio block code: a project block is a
module under ``blocks/`` that subclasses one of the block bases, and the
registry picks it up when the file is saved — which is the point the step that
writes it is making.

The science is deliberately small. Core tutorial 6 is about the *project* —
where data goes in, where results land — so the block does the least
processing that still produces a result worth saving: one row per culture with
its start, its end, and the fold change between them.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pyarrow as pa

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import DataFrame


class SummarizeGrowthBlock(ProcessBlock):
    """Summarise a growth curve into one row per culture.

    A growth run is read as a table of repeated measurements — one row per
    culture per day. The summary a lab notebook wants from it is short: where
    each culture started, where it ended, and how many times over it grew.
    """

    name: ClassVar[str] = "Summarize Growth"
    type_name: ClassVar[str] = "summarize_growth"
    description: ClassVar[str] = "One row per culture: start, end, and fold change."
    algorithm: ClassVar[str] = "growth_fold_change_summary"

    # A block chooses how it looks on the canvas and in the palette: a CSS hex
    # and any Lucide icon name (#1839/#1847). Both are optional — leaving them
    # out takes the category's default.
    ui_color: ClassVar[str] = "#0ea5e9"
    ui_icon: ClassVar[str] = "TrendingUp"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="table",
            accepted_types=[DataFrame],
            description="Growth measurements: sample, day, od600",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="summary",
            accepted_types=[DataFrame],
            description="One row per sample: start, end, fold change",
        ),
    ]

    # No knobs on purpose: this level teaches the project's geography, and a
    # block that runs on its defaults keeps the reader's attention there.
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
    }

    def process_item(self, item: DataFrame, config: BlockConfig, state: Any = None) -> DataFrame:
        """Reduce the measurement table to one summary row per sample.

        Args:
            item: The measurements. Must carry ``sample``, ``day`` and
                ``od600`` columns.
            config: Unused; the block has no configuration.
            state: Unused; part of the ProcessBlock signature.

        Returns:
            A table with one row per sample: ``sample``, ``days_measured``,
            ``start_od600``, ``end_od600``, and ``fold_change``.

        Raises:
            ValueError: When a required column is absent, or when a sample's
                first reading is zero so the fold change would divide by zero.
        """
        # to_memory() is the canonical read: it returns this table's
        # pyarrow.Table from storage. pandas is only borrowed for the grouping
        # below, and the result is handed back as Arrow.
        df = item.to_memory().to_pandas()

        required = {"sample", "day", "od600"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Input table is missing columns: {sorted(missing)}")

        samples: list[str] = []
        days_measured: list[int] = []
        start_values: list[float] = []
        end_values: list[float] = []
        fold_changes: list[float] = []
        for sample, group in df.groupby("sample", sort=True):
            ordered = group.sort_values("day")
            start = float(ordered["od600"].iloc[0])
            end = float(ordered["od600"].iloc[-1])
            if start == 0:
                raise ValueError(f"Sample {sample!r} starts at OD600 0, so fold change is undefined.")
            samples.append(str(sample))
            days_measured.append(int(ordered["day"].nunique()))
            start_values.append(start)
            end_values.append(end)
            fold_changes.append(end / start)

        summary = pa.table(
            {
                "sample": samples,
                "days_measured": days_measured,
                "start_od600": start_values,
                "end_od600": end_values,
                "fold_change": fold_changes,
            }
        )
        return DataFrame(data=summary)
