# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/tutorials/core/']`, which the
# CI-side run honors but the pre-commit hook (explicit file list) does not
# (#2115): this file ships as project *data* the reader opens and reads.
"""Which genes does one region express differently from the tissue around it?

Core tutorial 4 lands this file in the project's ``blocks/`` directory when it
creates the project.

For each tumor, the spots are split in two — the chosen region, and what it is
compared against: every other spot, or only the spots of one other region —
and each gene is compared across the split:

1. **How different.** The mean expression on each side, back on the counts per
   10,000 scale, and their ratio as a ``log2`` fold change: ``+1`` is twice as
   high in the region, ``-1`` half as high.
2. **How sure.** A Mann-Whitney U test, which asks whether the region's values
   tend to sit above or below the rest's without assuming they follow a bell
   curve. Spot counts are full of zeros, so a test that assumes one would be the
   wrong tool.
3. **Corrected for asking thousands of times.** Test 2,000 genes at p < 0.05
   and about a hundred pass by chance alone. The Benjamini-Hochberg ``q`` value
   corrects for that: of the genes kept at q < 0.05, about 5% are expected to be
   false alarms.

Genes barely expressed on either side are left out before testing. Their fold
changes are ratios of near-zeros — the largest in the table, and the least
meaningful.

Both the test and the correction are written out below, twenty-odd lines of
NumPy, so a reader who opens this file sees the statistics rather than an
import.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar

import numpy as np
import pandas as pd
import pyarrow as pa

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import DataFrame

#: Columns that say which spot this is rather than what it expressed.
DESCRIPTIVE_COLUMNS = ("barcode", "tumor", "region", "x", "y")

REGIONS = ("Invasive cancer", "DCIS", "Stroma", "Lymphocytes", "Normal")

#: The default comparison: the region against every spot outside it.
REST = "Rest of the tissue"

#: Added to both means before taking their ratio, so a gene absent on one side
#: gets a large but finite fold change instead of a division by zero.
PSEUDOCOUNT = 0.1


def mann_whitney_p(inside: np.ndarray, rest: np.ndarray) -> float:
    """Two-sided p-value of the Mann-Whitney U test, by the normal approximation.

    Rank every value together; if the region's values tend to be higher, its
    ranks add up to more than half of the total. ``U`` measures by how much, and
    with hundreds of spots a side it is close enough to normally distributed to
    read a p-value straight off the normal curve. Tied values share their
    average rank, and the variance is corrected for them.
    """
    values = np.concatenate([inside, rest])
    ranks = pd.Series(values).rank().to_numpy()
    n_inside, n_rest = len(inside), len(rest)
    total = n_inside + n_rest
    u = ranks[:n_inside].sum() - n_inside * (n_inside + 1) / 2
    _, ties = np.unique(values, return_counts=True)
    variance = n_inside * n_rest / 12 * ((total + 1) - (ties**3 - ties).sum() / (total * (total - 1)))
    if variance <= 0:
        return 1.0
    z = (u - n_inside * n_rest / 2) / math.sqrt(variance)
    return math.erfc(abs(z) / math.sqrt(2))


def benjamini_hochberg(p_values: np.ndarray) -> np.ndarray:
    """The q value of each p-value: the false discovery rate at which it would pass.

    Sort the p-values; the *k*-th smallest of *m* becomes ``p * m / k``, and each
    q is the smallest such value at or above its own rank, so q never decreases
    as p grows.
    """
    order = np.argsort(p_values)
    ranked = p_values[order] * len(p_values) / np.arange(1, len(p_values) + 1)
    q_values = np.empty_like(p_values)
    q_values[order] = np.minimum.accumulate(ranked[::-1])[::-1]
    return np.clip(q_values, 0.0, 1.0)


class CompareRegionsBlock(ProcessBlock):
    """Compare one region's expression against the rest of the tissue, per tumor."""

    name: ClassVar[str] = "Compare Regions"
    type_name: ClassVar[str] = "compare_regions"
    description: ClassVar[str] = "Per tumor, test every gene in one region against all other spots."
    algorithm: ClassVar[str] = "mann_whitney_bh"
    # Any lucide icon name; it draws this block's node on the canvas and its entry in the palette.
    ui_icon: ClassVar[str] = "diff"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="spots", accepted_types=[DataFrame], description="Normalized counts with a region column"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="genes", accepted_types=[DataFrame], description="One row per tested gene"),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "region": {
                "type": "string",
                "enum": list(REGIONS),
                "default": "Invasive cancer",
                "title": "Region",
                "description": "The region compared against every other spot.",
            },
            "against": {
                "type": "string",
                "enum": [REST, *REGIONS],
                "default": REST,
                "title": "Compare against",
                "description": "Every other spot, or only the spots of one other region.",
            },
            "min_expression": {
                "type": "number",
                "minimum": 0,
                "default": 5.0,
                "title": "Minimum expression",
                "description": "Skip genes whose mean is below this many counts per 10,000 on both sides.",
            },
        },
        "required": [],
    }

    def process_item(self, item: DataFrame, config: BlockConfig, state: Any = None) -> DataFrame:
        """Compare one tumor's chosen region against the rest of it, or one other region.

        Args:
            item: One tumor's normalized counts, with ``tumor`` and ``region``.
            config: Supplies ``region``, ``against`` and ``min_expression``.
            state: Unused; part of the ProcessBlock signature.

        Returns:
            One row per tested gene: the mean on each side, the ``log2`` fold
            change, and the p and q values, largest fold change first.

        Raises:
            ValueError: if either side of the comparison holds no spots.
        """
        frame = item.to_memory().to_pandas()
        region = str(config.get("region", "Invasive cancer"))
        against = str(config.get("against", REST))
        min_expression = float(config.get("min_expression", 5.0))
        tumor = str(frame["tumor"].iloc[0]) if "tumor" in frame.columns and len(frame) else "?"

        inside = (frame["region"] == region).to_numpy()
        other = ~inside if against == REST else (frame["region"] == against).to_numpy()
        if not inside.any() or not other.any():
            raise ValueError(
                f"{tumor}: {int(inside.sum())} spots are {region} and {int(other.sum())} are {against}, "
                "so there is nothing to compare."
            )

        genes = np.array([column for column in frame.columns if column not in DESCRIPTIVE_COLUMNS])
        logged = frame[genes].to_numpy(dtype=float)
        level = np.expm1(logged)  # back to counts per 10,000
        mean_inside = level[inside].mean(axis=0)
        mean_other = level[other].mean(axis=0)
        tested = np.maximum(mean_inside, mean_other) >= min_expression

        p_values = np.array([mann_whitney_p(logged[inside, g], logged[other, g]) for g in np.flatnonzero(tested)])
        result = pd.DataFrame(
            {
                "tumor": tumor,
                "region": region,
                "against": against,
                "gene": genes[tested],
                "mean_in_region": mean_inside[tested],
                "mean_in_other": mean_other[tested],
                "log2_fold_change": np.log2(mean_inside[tested] + PSEUDOCOUNT)
                - np.log2(mean_other[tested] + PSEUDOCOUNT),
                "p_value": p_values,
                "q_value": benjamini_hochberg(p_values) if len(p_values) else p_values,
            }
        )
        result = result.sort_values("log2_fold_change", ascending=False).reset_index(drop=True)
        return DataFrame(
            data=pa.Table.from_pandas(result, preserve_index=False),
            user={"display_name": f"{tumor}: {region} vs {against}"},
        )
