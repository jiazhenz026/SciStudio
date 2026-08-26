"""The tutorial-only AI Block — a real AIBlock subclass with a frozen answer.

Core tutorial 3 ships this into the tutorial project so the reader can run an
AI Block without configuring a provider or spending tokens. It is honest about
what it is: a subclass of the real :class:`~scistudio.blocks.ai.ai_block.AIBlock`
whose ``run`` returns a prepared table instead of spawning an agent CLI, and
the level says so out loud before the reader ever presses anything.

**Why a subclass rather than a lookalike.** SciStudio infers a block's category
— and with it the palette colour and the node's appearance — by walking the
class hierarchy with ``isinstance``, never from a declared field
(``registry/_spec.py``, ``_infer_category``). The only way for this block to
look like an AI block is to *be* one, which is the guarantee the tutorial is
demonstrating: the palette does not take a block's word for what it is.

**What it answers, and why that is the whole point of the level.** The plate
export names its groups A…J and says nothing about what they were dosed with;
the concentrations are in the file's name. A curve cannot be fitted from the
table alone, and no ordinary block can read a filename into data. This one
turns

    drug_A-J_1mM_500uM_200uM_100uM_50uM_20uM_10uM_5uM_2uM_1uM_plus_VEH_BLANK.csv

into a typed table — one row per group, with the concentration it stands
for — which is exactly the shape ``fit_ic50`` needs on its ``metadata``
input. Chat could have told the reader the same facts in prose;
what a block adds is that the answer is typed, validated, recorded in lineage,
and connected to the thing that needs it.

The two controls are the part a careless answer would get wrong. ``VEH`` and
``BLANK`` are group labels that are *not* doses, and an empty concentration is
how that is said — which is what makes the fit's inner join drop them without
the fit needing to know their names. A row that guessed a number for them
would put two invented points on the curve.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pyarrow as pa

from scistudio.blocks.ai.ai_block import AIBlock
from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.core.types import Collection, DataFrame

#: What a live agent reads out of the export's filename, frozen at authoring
#: time. ``None`` means "this group is not a dose", which is the fact the fit
#: relies on to leave the controls out of the curve.
_GROUPS: tuple[tuple[str, float | None], ...] = (
    ("A", 1000.0),
    ("B", 500.0),
    ("C", 200.0),
    ("D", 100.0),
    ("E", 50.0),
    ("F", 20.0),
    ("G", 10.0),
    ("H", 5.0),
    ("I", 2.0),
    ("J", 1.0),
    ("VEH", None),
    ("BLANK", None),
)


class TutorialAiAgentBlock(AIBlock):
    """AI Block (tutorial only): read the dose map out of the export's filename.

    Identical to the real AI Agent block in every declared respect — same
    config schema merged down the class hierarchy, same inferred category, same
    typed output contract — except that running it returns a frozen answer
    instead of spawning an agent. The config's ``provider`` field is accepted
    and ignored; nothing here contacts a provider or costs anything.
    """

    name: ClassVar[str] = "AI Agent (Tutorial Only)"
    type_name: ClassVar[str] = "tutorial_ai_agent"
    description: ClassVar[str] = "Read each group's concentration out of the export's filename."

    # Neither ui_color nor ui_icon, deliberately. The real AI Agent block
    # declares neither either, so leaving both alone is what makes this one
    # look exactly like it on the canvas — which is the claim the level is
    # making. The name is where the difference is stated, because that is
    # where a reader will actually read it.

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="table",
            accepted_types=[DataFrame],
            description="The plate, so the answer covers exactly the groups it contains",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="metadata",
            accepted_types=[DataFrame],
            description="One row per group: group, concentration_um",
        ),
    ]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Return the dose map, restricted to the groups the plate actually has.

        Args:
            inputs: ``table`` — the plate. Only its ``group`` column is read,
                and only to decide which rows of the answer are relevant.
            config: Accepted and ignored. A live AI Block would put its
                ``user_prompt`` to a model here; this one has the answer.

        Returns:
            ``{"metadata": Collection([...])}`` with ``group`` and
            ``concentration_um``, the latter null for a control.

        Raises:
            ValueError: The plate carries a group this answer has never seen.
                Silently returning a short table would be worse: the fit's join
                would drop those wells and the curve would come out quietly
                wrong instead of loudly absent.
        """
        present: set[str] = set()
        table = inputs.get("table")
        if table is not None:
            items = list(table) if isinstance(table, Collection) else [table]
            for item in items:
                present.update(str(value) for value in item.to_memory().to_pandas()["group"])

        known = {group for group, _dose in _GROUPS}
        unknown = sorted(present - known)
        if unknown:
            raise ValueError(
                f"the plate contains group(s) {unknown} this block has no answer for; "
                "a live AI Block would read them off the filename, and this one only "
                "knows the export the tutorial ships."
            )

        rows = [row for row in _GROUPS if not present or row[0] in present]
        out = pa.table(
            {
                "group": [group for group, _dose in rows],
                "concentration_um": pa.array([dose for _group, dose in rows], type=pa.float64()),
            }
        )
        return {"metadata": Collection([DataFrame(data=out)])}
