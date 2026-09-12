# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/tutorials/core/']`, which the
# CI-side run honors but the pre-commit hook (explicit file list) does not
# (#2115): this file ships as project *data* the reader opens and reads.
"""Put every spot's counts on a comparable scale.

Core tutorial 4 lands this file in the project's ``blocks/`` directory when it
creates the project.

Raw counts are not comparable between spots, because spots do not capture the
same amount of material: a spot that caught twice the RNA reports roughly twice
every count. Dividing each spot by its own total removes that, and rescaling to
counts per 10,000 keeps the numbers readable. ``log1p`` then compresses the
range, so a gene going from 1 to 2 weighs as much as one going from 100 to 200.

It is the standard first step for spatial and single-cell counts, and it is a
few lines of NumPy below. Read them: this is not a library call wearing a
costume.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import pandas as pd
import pyarrow as pa

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import DataFrame

#: Columns that say which spot this is rather than what it expressed. Everything
#: else in the table is a gene.
DESCRIPTIVE_COLUMNS = ("barcode", "tumor", "region", "x", "y")

#: Counts per 10,000, the usual scale for spatial and single-cell data.
TARGET_SCALE = 10_000.0


def normalize_counts(counts: np.ndarray) -> np.ndarray:
    """Scale each row to counts per 10,000, then ``log1p``.

    A spot that captured nothing at all stays at zero rather than dividing by
    zero.
    """
    totals = counts.sum(axis=1, keepdims=True)
    return np.log1p(counts / np.where(totals > 0, totals, 1.0) * TARGET_SCALE)


class NormalizeExpressionBlock(ProcessBlock):
    """Scale each spot's counts so spots can be compared.

    Input and output are the same table: the descriptive columns pass through
    untouched, and every gene column is replaced by its normalized value.
    """

    name: ClassVar[str] = "Normalize Expression"
    type_name: ClassVar[str] = "normalize_expression"
    description: ClassVar[str] = "Scale each spot to counts per 10,000, then log1p."
    algorithm: ClassVar[str] = "total_count_log1p"
    # Any lucide icon name; it draws this block's node on the canvas and its entry in the palette.
    ui_icon: ClassVar[str] = "scale"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="counts", accepted_types=[DataFrame], description="Raw spot-by-gene counts"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="normalized", accepted_types=[DataFrame], description="Same table, genes rescaled"),
    ]

    def process_item(self, item: DataFrame, config: BlockConfig, state: Any = None) -> DataFrame:
        """Normalize one tumor's table.

        Args:
            item: One tumor's counts, one row per spot and one column per gene.
            config: Unused.
            state: Unused; part of the ProcessBlock signature.

        Returns:
            The same table with every gene column normalized.
        """
        frame = item.to_memory().to_pandas()
        kept = [column for column in frame.columns if column in DESCRIPTIVE_COLUMNS]
        genes = [column for column in frame.columns if column not in DESCRIPTIVE_COLUMNS]
        scaled = pd.DataFrame(normalize_counts(frame[genes].to_numpy(dtype=float)), columns=genes, index=frame.index)
        result = pd.concat([frame[kept], scaled], axis=1)
        return DataFrame(data=pa.Table.from_pandas(result, preserve_index=False), user=dict(item.user or {}))
