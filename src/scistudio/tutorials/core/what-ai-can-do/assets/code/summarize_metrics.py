"""A summary-statistics block for QC-annotated measurement tables.

Written into the tutorial project by core tutorial 4's scripted agent. It
turns a wide measurement table into one row of statistics per metric, computed
only over the samples QC kept — which is what makes the QC threshold visible:
tighten it, re-run, and watch ``n_kept`` fall.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pyarrow as pa

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import DataFrame


class SummarizeMetricsBlock(ProcessBlock):
    """Summarise every numeric metric over the QC-kept samples.

    One output row per numeric column: how many samples QC kept for it, how
    many were dropped or missing, and the usual descriptive statistics. The
    ``qc_*`` bookkeeping columns are not metrics and are not summarised.
    """

    name: ClassVar[str] = "Summary Stats"
    type_name: ClassVar[str] = "summarize_metrics"
    description: ClassVar[str] = "One row of descriptive statistics per metric, over QC-kept samples."
    algorithm: ClassVar[str] = "per_metric_descriptive_stats"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="table", accepted_types=[DataFrame], description="QC-annotated measurement table"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="summary", accepted_types=[DataFrame], description="One row of statistics per metric"),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def process_item(self, item: DataFrame, config: BlockConfig, state: Any = None) -> DataFrame:
        """Summarise the numeric metrics of a QC-annotated table.

        Args:
            item: The measurement table. When a boolean ``qc_keep`` column is
                present, statistics run over the kept rows only; without one,
                every row counts.
            config: Unused; the block has no parameters.
            state: Unused; part of the ProcessBlock signature.

        Returns:
            A table with one row per metric: ``metric``, ``n_total``,
            ``n_kept``, ``n_dropped``, ``n_missing``, ``mean``, ``sd``,
            ``min``, ``max``.
        """
        df = item.to_memory().to_pandas()
        kept = df[df["qc_keep"].astype(bool)] if "qc_keep" in df.columns else df

        skip = {"qc_robust_z"}
        rows = []
        for column in df.columns:
            if column in skip or not hasattr(df[column], "dtype"):
                continue
            if df[column].dtype.kind not in "ifu" or column.startswith("qc_"):
                continue
            kept_values = kept[column]
            rows.append(
                {
                    "metric": column,
                    "n_total": len(df),
                    "n_kept": int(kept_values.notna().sum()),
                    "n_dropped": int(len(df) - len(kept)),
                    "n_missing": int(df[column].isna().sum()),
                    "mean": round(float(kept_values.mean()), 2),
                    "sd": round(float(kept_values.std()), 2),
                    "min": round(float(kept_values.min()), 2),
                    "max": round(float(kept_values.max()), 2),
                }
            )
        if not rows:
            raise ValueError("The input table has no numeric metric columns to summarise.")
        import pandas as pd

        return DataFrame(data=pa.Table.from_pandas(pd.DataFrame(rows), preserve_index=False))
