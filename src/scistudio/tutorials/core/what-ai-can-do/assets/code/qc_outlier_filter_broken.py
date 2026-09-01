"""A QC block that flags outlying wells instead of silently deleting them.

The scripted agent in core tutorial 3 writes this block into the tutorial
project. It is ordinary SciStudio block code: a module under ``blocks/`` that
subclasses a block base, picked up by the registry when the file lands.

The science, in three sentences. A dose-response plate reads the same drug at a
dozen concentrations, several replicate wells each, and wells fail in ways that
produce wild values — a bubble reads far too low, a dose that never got
dispensed leaves an untreated well in the middle of the dilution series. Those
wells must not reach the curve fit, because a single 96% at 33 uM drags the top
of the curve up and takes the IC50 with it. So each well is scored against
**its own group** rather than against the plate: viability is
supposed to fall as the dose rises, and a well that is low because the dose was
high is not an outlier.

Robust statistics throughout — median and MAD rather than mean and SD —
because with eight replicates one bad well is an eighth of the evidence, and a
mean would let it hide its own accomplice. And the block *flags* rather than
drops: good QC marks what is suspect so a human can look at it, it does not
throw data away where nobody can see it happen.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pyarrow as pa

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import DataFrame

# The measurement column this plate's QC is scored on.
METRIC_COLUMN = "viability"

# The column that says which wells are replicates of each other.
GROUP_COLUMN = "group"

# MAD-to-sigma for a normal distribution; 1 / Phi^-1(3/4).
MAD_TO_SIGMA = 1.4826


class QcOutlierFilterBlock(ProcessBlock):
    """Flag wells whose viability is an outlier among its replicates, or missing.

    Adds three columns to the table it is given:

    * ``qc_robust_z`` — how many robust sigmas the well sits from the median of
      its own group (blank for a missing measurement);
    * ``qc_keep`` — ``True`` when the measurement is present and within the
      configured threshold;
    * ``qc_reason`` — why a well was flagged, in words.

    **The default threshold is ten sigma, and that is not a typo.** With
    eight replicates the MAD is itself a noisy estimate, so a three-sigma
    rule flags ordinary replicate scatter — wells that are data, not
    errors. Nobody working with a plate wants those thrown away, and a
    tool that does it by default teaches a bad habit. What this block is
    for is the wells that are *broken*: one that never reported, and one
    that cannot be what its group says it is. Those sit tens of sigmas
    out, not three, so a blunt threshold separates them cleanly and
    leaves every judgement call to the person whose experiment it is.

    Every row survives. Downstream blocks decide what to do with the flags,
    which keeps the decision visible in the data instead of buried in a filter.
    """

    name: ClassVar[str] = "QC Outlier Filter"
    type_name: ClassVar[str] = "qc_outlier_filter"
    description: ClassVar[str] = "Flag wells whose viability is missing or an outlier among its replicates."
    algorithm: ClassVar[str] = "grouped_robust_z_outlier_flagging"

    # Written blocks get to look like themselves (#1839). Lime rather than the
    # Process default, so the reader can tell at a glance which two blocks on
    # this canvas the agent wrote; a flag rather than a filter or a bin,
    # because flagging is exactly what it does and deleting is exactly what it
    # does not. The broken twin carries the same two values, so fixing the bug
    # does not change how the block looks.
    ui_color: ClassVar[str] = "#cfe3a3"
    ui_icon: ClassVar[str] = "Flag"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="table", accepted_types=[DataFrame], description="Raw plate reader table"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="annotated", accepted_types=[DataFrame], description="Same table plus qc_* columns"),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "sigma_threshold": {
                "type": "number",
                "default": 10,
                "title": "Sigma threshold",
                "description": (
                    "Wells farther than this many robust sigmas from their own "
                    "group's median are flagged. Deliberately blunt: see the "
                    "class docstring for why three would be wrong here."
                ),
            },
        },
        "required": [],
    }

    def process_item(self, item: DataFrame, config: BlockConfig, state: Any = None) -> DataFrame:
        """Score each well against its replicate group and flag it.

        Args:
            item: The plate table. Must carry the metric and group columns.
            config: Supplies ``sigma_threshold`` (default 10).
            state: Unused; part of the ProcessBlock signature.

        Returns:
            The same table with ``qc_robust_z``, ``qc_keep`` and ``qc_reason``
            columns added.
        """
        df = item.to_memory().to_pandas()
        threshold = float(config.get("sigma_threshold", 10))

        values = df[METRIC_COLUMN]
        median = values.groupby(df[GROUP_COLUMN]).transform("median")
        # MAD within the group: the median of each well's distance from its own
        # group's median.
        mad = (values - median).abs().groupby(df[GROUP_COLUMN]).transform("median")
        robust_sigma = MAD_TO_SIGMA * mad

        # A group whose replicates all read the same value has no spread to
        # score against. That is not a failure — nothing in it can be an
        # outlier — so those wells are simply kept.
        z = (values - median) / robust_sigma.where(robust_sigma > 0)
        present = values.notna()
        keep = present & (z.abs() <= threshold).fillna(True)

        df["qc_robust_z"] = z.round(2)
        df["qc_keep"] = keep
        df["qc_reason"] = ""
        df.loc[~present, "qc_reason"] = f"missing {METRIC_COLUMN}"
        outlier = present & ~keep
        df.loc[outlier, "qc_reason"] = [f"outlier (robust z = {value:+.1f})" for value in z[outlier].round(1)]
        return DataFrame(data=pa.Table.from_pandas(df, preserve_index=False))
