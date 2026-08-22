"""The tutorial-only AI Block — a real AIBlock subclass with a canned run.

Core tutorial 4 ships this into the tutorial project so the reader can run an
AI Block without configuring a provider or spending tokens. It is honest about
what it is: a subclass of the real :class:`~scistudio.blocks.ai.ai_block.AIBlock`
whose ``run`` returns prepared results instead of spawning an agent CLI.

Why a *subclass* rather than a lookalike: SciStudio infers a block's category
— and with it the palette colour and icon — by walking the class hierarchy
with ``isinstance`` checks, never from a declared field
(``registry/_spec.py``, ``_infer_category``). The only way for this block to
look like an AI block is to *be* one, which is exactly the guarantee the
tutorial wants to demonstrate: the palette does not take a block's word for
what it is.

What the canned run does: for every table handed to it, it reports each
column's real observed facts (dtype, range, missing count) and pairs them with
the metadata a live agent inferred for these files when the tutorial was
authored. Real inference happens per dataset, with a provider configured; the
lookup table below is that inference, frozen. The shape of the answer is the
lesson — chat produces a conversation, an AI Block produces a typed, validated
table that flows into lineage like any other block output.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pyarrow as pa

from scistudio.blocks.ai.ai_block import AIBlock
from scistudio.blocks.base import BlockConfig
from scistudio.core.types import Collection, DataFrame

# What a live agent inferred for these instrument exports, frozen at authoring
# time. Keys are column names; values are (meaning, unit, evidence).
_CANNED_INFERENCES: dict[str, tuple[str, str, str]] = {
    "t": ("time since first read", "s", "monotone, constant step of 30"),
    "ch1": ("reporter fluorescence, channel 1", "AU", "rises smoothly toward a plateau"),
    "ch2": ("reference dye fluorescence, channel 2", "AU", "flat around 1500 across all reads"),
    "tempC": ("read-chamber temperature", "degC", "narrow band at 37, the incubation setpoint"),
    "idx": ("sample index", "-", "consecutive integers from 1"),
    "od600": ("optical density at 600 nm", "OD", "classic logistic growth-curve shape"),
    "ph": ("culture pH", "pH", "drifts down as the culture acidifies"),
    "w": ("plate well position", "-", "letter-number pairs in plate order"),
    "sig": ("raw assay signal", "AU", "same scale as the plate's fluorescence values"),
    "bg": ("background from an empty well", "AU", "small, stable, an order below sig"),
    "flag": ("instrument QC flag (0 ok, 1 flagged)", "-", "binary, sparse ones"),
}


class TutorialAiAgentBlock(AIBlock):
    """AI Block (tutorial only): infer column metadata from prepared answers.

    Identical to the real AI Agent block in every declared respect — same
    ports, same config schema (merged down the class hierarchy), same
    inferred category — except that running it consults a frozen answer table
    instead of spawning an agent. The config's ``provider`` field is accepted
    and ignored; nothing here contacts a provider.
    """

    name: ClassVar[str] = "AI Block (tutorial only)"
    type_name: ClassVar[str] = "tutorial_ai_agent"
    description: ClassVar[str] = (
        "The real AI Agent block with a canned run: infers column metadata from "
        "prepared answers instead of spawning an agent CLI."
    )
    version: ClassVar[str] = "0.1.0"

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Describe every column of every input table, without an agent.

        Args:
            inputs: The ``data`` port's collection — the undocumented tables.
            config: Accepted for interface compatibility; the prompt and
                provider fields a real run would use are ignored.

        Returns:
            One ``result`` collection holding a single metadata table: one row
            per (table, column), with observed facts computed from the real
            data and meanings looked up from the frozen inference table.

        Raises:
            ValueError: When no input tables were provided.
        """
        import pandas as pd

        tables = list(inputs.get("data", []) or [])
        if not tables:
            raise ValueError("AI Block (tutorial only) needs at least one input table on 'data'.")

        rows: list[dict[str, Any]] = []
        for index, item in enumerate(tables, start=1):
            df = item.to_memory().to_pandas()
            for column in df.columns:
                series = df[column]
                numeric = series.dtype.kind in "ifu"
                meaning, unit, evidence = _CANNED_INFERENCES.get(
                    str(column),
                    ("unknown - ask whoever produced the file", "?", "no stored inference for this name"),
                )
                rows.append(
                    {
                        "table": index,
                        "column": str(column),
                        "dtype": str(series.dtype),
                        "n_values": int(series.notna().sum()),
                        "n_missing": int(series.isna().sum()),
                        "observed_min": round(float(series.min()), 3) if numeric else None,
                        "observed_max": round(float(series.max()), 3) if numeric else None,
                        "inferred_meaning": meaning,
                        "inferred_unit": unit,
                        "evidence": evidence,
                    }
                )

        table = pa.Table.from_pandas(pd.DataFrame(rows), preserve_index=False)
        return {"result": Collection([DataFrame(data=table)])}
