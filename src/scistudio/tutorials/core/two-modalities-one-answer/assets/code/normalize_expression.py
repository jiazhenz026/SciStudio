# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/tutorials/core/']`, which the
# CI-side run honours but the pre-commit hook (explicit file list) does not
# (#2115): this file ships as project *data* the reader opens and reads.
"""Put every position's counts on a comparable scale.

Core tutorial 3 writes this block into the project when the reader presses the
button on the "normalise the expression" step.

Raw counts are not comparable between positions, because positions do not
capture the same amount of material. Normalisation is the correction for that,
and it is a *choice*, not a formality — which is the whole reason this level
ends in a git branch. Two methods ship here, both standard, and neither is
right everywhere:

``total_count``
    Divide each position by its own total and rescale (counts per 10,000),
    then ``log1p``. The workhorse. It assumes the total is a fair proxy for
    how much material a position captured, which holds until a handful of
    genes start dominating the total on their own.

``median_ratio``
    The median-of-ratios size factor (the estimator DESeq made standard).
    Compare each position against a *reference* profile — the geometric mean
    of every position — and take the median of the per-gene ratios as that
    position's scale factor. Because it is a median, a few runaway genes move
    it barely at all. Its own weakness is the opposite one: the geometric mean
    is only defined for genes seen in *every* position, so on shallow, zero-
    heavy data the estimate rests on very few genes and gets noisy.

Both are twenty lines of NumPy each and both are real. Read them: this is not
a library call wearing a costume.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import pyarrow as pa

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import DataFrame

# Columns that describe *which* position this is rather than what it expressed.
# Everything else in the table is a gene.
COORDINATE_COLUMNS = ("position_id", "section", "y", "x")

# Counts-per-10,000, the usual scale for this size of experiment.
TARGET_SCALE = 10_000.0

# Below this many genes present in every position, the median-of-ratios
# reference rests on too thin a basis to be trusted. The block does not refuse
# — a normalisation that refuses is a workflow that stops — it goes ahead on
# what it has, which is exactly how the estimator behaves in the wild.
MIN_REFERENCE_GENES = 3


def total_count_factors(counts: np.ndarray) -> np.ndarray:
    """One scale factor per position: its own total, relative to the mean total."""
    totals = counts.sum(axis=1)
    mean_total = float(totals[totals > 0].mean()) if np.any(totals > 0) else 1.0
    factors = totals / mean_total
    return np.where(factors > 0, factors, 1.0)


def median_ratio_factors(counts: np.ndarray) -> np.ndarray:
    """One scale factor per position: the median ratio against a reference profile.

    The reference is the geometric mean of each gene across positions, computed
    only over genes that are non-zero everywhere — a gene absent from one
    position has a geometric mean of zero and no usable ratio.
    """
    usable = np.all(counts > 0, axis=0)
    if int(usable.sum()) < MIN_REFERENCE_GENES:
        # Too few genes to build a reference from; widen to genes present in at
        # least one position and accept the noisier estimate.
        usable = counts.sum(axis=0) > 0
    if not np.any(usable):
        return np.ones(counts.shape[0])
    kept = counts[:, usable]
    with np.errstate(divide="ignore", invalid="ignore"):
        reference = np.exp(np.nanmean(np.where(kept > 0, np.log(kept), np.nan), axis=0))
        ratios = np.where((kept > 0) & (reference > 0), kept / reference, np.nan)
    # A position with nothing measured at all has no ratio to take a median of.
    # Give it a factor of 1 rather than asking NumPy for the median of nothing.
    factors = np.ones(counts.shape[0])
    measured = np.any(np.isfinite(ratios), axis=1)
    if np.any(measured):
        factors[measured] = np.nanmedian(ratios[measured], axis=1)
    return np.where(np.isfinite(factors) & (factors > 0), factors, 1.0)


class NormalizeExpressionBlock(ProcessBlock):
    """Scale each position's counts so positions can be compared.

    Input and output are the same table: the coordinate columns pass through
    untouched, and every gene column is replaced by its normalised value.
    """

    name: ClassVar[str] = "Normalize Expression"
    type_name: ClassVar[str] = "normalize_expression"
    description: ClassVar[str] = "Scale per-position counts (total-count or median-of-ratios), then log1p."
    algorithm: ClassVar[str] = "count_normalisation"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="counts", accepted_types=[DataFrame], description="Raw per-position counts"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="normalized", accepted_types=[DataFrame], description="Same table, gene columns rescaled"),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["total_count", "median_ratio"],
                "default": "total_count",
                "title": "Method",
                "description": (
                    "total_count: scale by each position's own total. "
                    "median_ratio: scale by the median ratio against a reference profile."
                ),
            },
        },
        "required": [],
    }

    def process_item(self, item: DataFrame, config: BlockConfig, state: Any = None) -> DataFrame:
        """Normalise one section's count table.

        Args:
            item: One section's counts, with ``position_id``/``y``/``x`` and one
                column per gene.
            config: Supplies ``method`` (default ``total_count``).
            state: Unused; part of the ProcessBlock signature.

        Returns:
            The same table with every gene column normalised and ``log1p``-ed.
        """
        frame = item.to_memory().to_pandas()
        genes = [column for column in frame.columns if column not in COORDINATE_COLUMNS]
        counts = frame[genes].to_numpy(dtype=float)

        method = str(config.get("method", "total_count"))
        factors = median_ratio_factors(counts) if method == "median_ratio" else total_count_factors(counts)

        scaled = counts / factors[:, None]
        if method == "total_count":
            # Counts-per-10,000 puts total-count output on a familiar scale.
            # The median-ratio factors are already relative, so it does not
            # apply there.
            scaled = scaled * (TARGET_SCALE / max(float(counts.sum(axis=1).mean()), 1.0))
        frame[genes] = np.log1p(scaled)
        return DataFrame(data=pa.Table.from_pandas(frame, preserve_index=False), user=dict(item.user or {}))
