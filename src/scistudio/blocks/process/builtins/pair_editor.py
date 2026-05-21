"""PairEditor -- interactive reordering to fix index-based pairing.

#594: When a multi-input block (e.g. ExtractSpectrum) receives N Collections
from N parallel branches, it zips by index. If the Collections arrive in
different orders, the pairing is wrong. PairEditor lets users visually
reorder items within each Collection so same-index items are paired.

First consumer of ADR-029 variadic port system alongside DataRouter (#591).
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock

logger = logging.getLogger(__name__)


class PairEditor(ProcessBlock):
    """Interactive item reordering block for fixing index-based pairing.

    Users configure N variadic input ports (2-8). Output ports are
    auto-mirrored from inputs (same count, same types). At runtime the
    block pauses with side-by-side sortable panels. Same-row items across
    panels are "paired" (highlighted with same color). Users drag to
    reorder within each panel.

    Runtime flow:
        1. User configures N input ports (2-8), output ports auto-mirror
        2. Workflow reaches PairEditor -> PAUSED
        3. Frontend opens PairEditor modal (N side-by-side sortable panels)
        4. Confirm -> reordered indices sent to backend -> reordered Collections -> DONE

    Validation: All input Collections must have equal length.
    """

    name: ClassVar[str] = "Pair Editor"
    description: ClassVar[str] = "Interactive reordering of items within Collections for correct index-based pairing"
    algorithm: ClassVar[str] = "pair_editor"
    subcategory: ClassVar[str] = "routing"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE

    variadic_inputs: ClassVar[bool] = True
    variadic_outputs: ClassVar[bool] = True
    allowed_input_types: ClassVar[list[type]] = []
    allowed_output_types: ClassVar[list[type]] = []
    min_input_ports: ClassVar[int | None] = 2
    max_input_ports: ClassVar[int | None] = 8

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Prepare data for the frontend interactive prompt.

        Validates equal-length Collections and returns item descriptors
        for each port.

        Returns a dict with:
            ports: list of port name strings
            items_per_port: dict mapping port name to list of item descriptors
            collection_length: int (common length of all Collections)
        """
        from scistudio.core.types.collection import Collection

        ports = list(inputs.keys())
        items_per_port: dict[str, list[dict[str, Any]]] = {}
        lengths: dict[str, int] = {}

        for port_name, value in inputs.items():
            items: list[dict[str, Any]] = []
            if isinstance(value, Collection):
                lengths[port_name] = len(value)
                for i, item in enumerate(value):
                    item_desc: dict[str, Any] = {
                        "index": i,
                        "name": getattr(item, "name", None) or f"item_{i}",
                        "type": type(item).__name__,
                    }
                    items.append(item_desc)
            else:
                lengths[port_name] = 1
                items.append(
                    {
                        "index": 0,
                        "name": getattr(value, "name", None) or "item_0",
                        "type": type(value).__name__,
                    }
                )
            items_per_port[port_name] = items

        # Validate equal length.
        unique_lengths = set(lengths.values())
        if len(unique_lengths) > 1:
            detail = ", ".join(f"{k}={v}" for k, v in lengths.items())
            raise ValueError(f"PairEditor requires all input Collections to have equal length. Got: {detail}")

        collection_length = unique_lengths.pop() if unique_lengths else 0

        return {
            "ports": ports,
            "items_per_port": items_per_port,
            "collection_length": collection_length,
        }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Reorder items in each Collection based on user-specified indices.

        The ``interactive_response`` in config contains:
            reorder: dict mapping port name to list of indices (new order)
                e.g. {"A": [2, 0, 4, 1, 3], "B": [2, 0, 4, 1, 3]}
        """
        from scistudio.core.types.collection import Collection

        response = config.get("interactive_response", {})
        reorder = response.get("reorder", {})

        if not reorder:
            raise ValueError("PairEditor received no reorder data from interactive response")

        outputs: dict[str, Any] = {}
        for port_name, value in inputs.items():
            indices = reorder.get(port_name)
            if indices is None:
                # If no reorder specified for this port, pass through unchanged.
                outputs[port_name] = value
                continue

            if isinstance(value, Collection):
                items = list(value)
                if len(indices) != len(items):
                    raise ValueError(
                        f"PairEditor: reorder indices length ({len(indices)}) does not match "
                        f"Collection length ({len(items)}) for port '{port_name}'"
                    )
                reordered = [items[i] for i in indices]
                outputs[port_name] = Collection(reordered, item_type=value.item_type)
            else:
                # Single item — pass through.
                outputs[port_name] = value

        return outputs
