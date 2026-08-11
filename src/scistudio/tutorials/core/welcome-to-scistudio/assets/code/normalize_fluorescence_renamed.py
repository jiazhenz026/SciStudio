"""The same block after a well-meaning rename broke every reference to it.

The Learning Center writes this file over ``blocks/normalize_fluorescence.py``
so the reader meets a recovery they did not cause. The processing code below is
untouched and still correct; the only edit is the identifier on the
``type_name`` line, changed from ``normalize_fluorescence`` to
``normalise_fluorescence``.

That single line is the one the workflow stores. A saved workflow refers to a
block by ``type_name``, not by file name and not by class name, so renaming it
leaves the node in the canvas pointing at a block type that no longer exists.
The file still imports, the block still appears in the palette under its new
identifier, and the workflow still cannot run.

Recovering it by hand means knowing all of that. Restore does not require
knowing any of it.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pyarrow as pa

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import DataFrame


class NormaliseFluorescenceBlock(ProcessBlock):
    """Normalise fluorescence using negative and positive control means."""

    name: ClassVar[str] = "Normalise Fluorescence"
    type_name: ClassVar[str] = "normalise_fluorescence"
    description: ClassVar[str] = "Normalise fluorescence with negative and positive controls."
    algorithm: ClassVar[str] = "fluorescence_control_normalization"

    # Carried over unchanged, so the block still looks like itself in the
    # palette. The rename above is the only thing that moved.
    ui_color: ClassVar[str] = "#22c55e"
    ui_icon: ClassVar[str] = "Sparkles"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="table", accepted_types=[DataFrame], description="Raw fluorescence table"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="normalized", accepted_types=[DataFrame], description="Normalized activity table"),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "negative_control": {
                "type": "string",
                "default": "neg_control",
                "description": "Condition label used as the zero-activity control.",
            },
            "positive_control": {
                "type": "string",
                "default": "pos_control",
                "description": "Condition label used as the full-activity control.",
            },
        },
        "required": ["negative_control", "positive_control"],
    }

    def process_item(self, item: DataFrame, config: BlockConfig, state: Any = None) -> DataFrame:
        """Rescale the ``fluorescence`` column onto the control axis.

        Args:
            item: The raw table. Must carry ``condition``, ``replicate`` and
                ``fluorescence`` columns.
            config: Block config supplying the two control labels.
            state: Unused; part of the ProcessBlock signature.

        Returns:
            The same table with a ``normalized_activity`` column added.

        Raises:
            ValueError: When a required column is absent, when either control
                label is missing from ``condition``, or when the two control
                means coincide so the scale would divide by zero.
        """
        # to_memory() is the canonical read: it returns this table's
        # pyarrow.Table from storage. pandas is only borrowed for the
        # grouping below, and the result is handed back as Arrow.
        df = item.to_memory().to_pandas()
        negative_control = str(config.get("negative_control", "neg_control"))
        positive_control = str(config.get("positive_control", "pos_control"))

        required = {"condition", "replicate", "fluorescence"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Input table is missing columns: {sorted(missing)}")

        neg = df.loc[df["condition"] == negative_control, "fluorescence"]
        pos = df.loc[df["condition"] == positive_control, "fluorescence"]
        if neg.empty or pos.empty:
            raise ValueError("Both negative_control and positive_control labels must exist in condition.")

        neg_mean = float(neg.mean())
        pos_mean = float(pos.mean())
        denominator = pos_mean - neg_mean
        if denominator == 0:
            raise ValueError("Positive and negative control means must be different.")

        df["normalized_activity"] = (df["fluorescence"] - neg_mean) / denominator
        return DataFrame(data=pa.Table.from_pandas(df, preserve_index=False))
