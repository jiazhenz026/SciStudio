"""A QC block that flags outlying samples instead of silently deleting them.

The scripted agent in core tutorial 4 writes this block into the tutorial
project. It is ordinary SciStudio block code: a module under ``blocks/`` that
subclasses a block base, picked up by the registry when the file lands.

The science, in two sentences. Plate measurements fail in ways that produce
wild values — a bubble in a well, a dispense that never happened, a sensor
dropout — and those rows must not reach the statistics. The filter scores each
sample by how far its fluorescence sits from the plate's centre, in robust
sigma units (median and MAD rather than mean and SD, because one 9840 in a
column of 1200s drags the mean toward itself and then hides its own
accomplice), and *flags* rows instead of dropping them: good QC never throws
data away silently, it marks it so a human can look.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pyarrow as pa

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import DataFrame

# The measurement column this plate's QC is scored on.
METRIC_COLUMN = "fluorescence"

# MAD-to-sigma for a normal distribution; 1 / Phi^-1(3/4).
MAD_TO_SIGMA = 1.4826


class QcOutlierFilterBlock(ProcessBlock):
    """Flag samples whose fluorescence is an outlier, or missing.

    Adds three columns to the table it is given:

    * ``qc_robust_z`` — how many robust sigmas the sample sits from the plate
      median (blank for a missing measurement);
    * ``qc_keep`` — ``True`` when the measurement is present and within the
      configured threshold;
    * ``qc_reason`` — why a sample was flagged, in words.

    Every row survives. Downstream blocks decide what to do with the flags,
    which keeps the decision visible in the data instead of buried in a filter.
    """

    name: ClassVar[str] = "QC Outlier Filter"
    type_name: ClassVar[str] = "qc_outlier_filter"
    description: ClassVar[str] = "Flag samples whose fluorescence is missing or a robust-sigma outlier."
    algorithm: ClassVar[str] = "robust_z_outlier_flagging"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="table", accepted_types=[DataFrame], description="Raw measurement table"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="annotated", accepted_types=[DataFrame], description="Same table plus qc_* columns"),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "sigma_threshold": {
                "type": "number",
                "default": 3,
                "title": "Sigma threshold",
                "description": "Samples farther than this many robust sigmas from the plate median are flagged.",
            },
        },
        "required": [],
    }

    def process_item(self, item: DataFrame, config: BlockConfig, state: Any = None) -> DataFrame:
        """Score each sample against the plate's robust centre and flag it.

        Args:
            item: The measurement table. Must carry the metric column.
            config: Supplies ``sigma_threshold`` (default 3).
            state: Unused; part of the ProcessBlock signature.

        Returns:
            The same table with ``qc_robust_z``, ``qc_keep`` and ``qc_reason``
            columns added.
        """
        df = item.to_memory().to_pandas()
        threshold = float(config.get("sigma_threshold", 3))

        values = df[METRIC_COLUMN]
        median = float(values.median())
        mad = float((values - median).abs().median())
        robust_sigma = MAD_TO_SIGMA * mad
        if robust_sigma == 0:
            raise ValueError(f"{METRIC_COLUMN} has zero spread; robust z-scores are undefined.")

        z = (values - median) / robust_sigma
        present = values.notna()
        keep = present & (z.abs() <= threshold)

        df["qc_robust_z"] = z.round(2)
        df["qc_keep"] = keep
        df["qc_reason"] = ""
        df.loc[~present, "qc_reason"] = f"missing {METRIC_COLUMN}"
        outlier = present & ~keep
        df.loc[outlier, "qc_reason"] = [f"outlier (robust z = {value:+.1f})" for value in z[outlier].round(1)]
        return DataFrame(data=pa.Table.from_pandas(df, preserve_index=False))
