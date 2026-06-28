"""PairEditor -- interactively reorder items to fix index-based pairing.

When a multi-input block (for example one that extracts spectra) receives
several Collections from parallel branches, it pairs them by position: the
first item of each, then the second, and so on. If the Collections arrive in
different orders, the wrong items get paired. PairEditor lets the user reorder
items within each Collection so that same-position items line up correctly.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import (
    InteractiveMixin,
    InteractivePrompt,
    PanelManifest,
    interactive_item_label,
)
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock

logger = logging.getLogger(__name__)


# Interaction model (pause/resume, worker subprocesses, panel manifest) is
# specified in ADR-051; the variadic port system in ADR-029.
class PairEditor(InteractiveMixin, ProcessBlock):
    """Reorder items within Collections so they pair up correctly.

    Wire two to eight Collections into the input ports. When the workflow
    reaches this block it pauses and shows the Collections as side-by-side
    sortable lists, with items on the same row highlighted as a pair. Drag
    items within each list until the rows that should be paired line up, then
    confirm. The output ports mirror the inputs (same count and types), each
    carrying its reordered Collection.

    All input Collections must have the same length; otherwise the block stops
    with an error before pausing.

    Ports: a variadic input side (2-8 ports) and a matching set of output
    ports auto-mirrored from the inputs. Config: reads
    ``interactive_response.reorder``, a mapping of input port name to the new
    item order the user chose; the framework fills this in from the panel.

    This block is used by wiring it into a workflow and interacting with its
    panel; it is not meant to be subclassed.
    """

    name: ClassVar[str] = "Pair Editor"
    """Display name shown in the block palette and on the canvas node."""

    description: ClassVar[str] = "Interactive reordering of items within Collections for correct index-based pairing"
    """One-line summary shown in the palette and node tooltip."""

    algorithm: ClassVar[str] = "pair_editor"
    """Stable identifier for this block's transform; recorded in metadata."""

    subcategory: ClassVar[str] = "routing"
    """Palette subgroup this block is filed under (here, ``"routing"``)."""

    # #1839 / #1847: macaron apricot + a left-right swap glyph for the
    # pairing/reorder block. (Recoloured off the earlier rose, which read too
    # close to the subworkflow category pink.)
    ui_color: ClassVar[str] = "#f6cba0"
    ui_icon: ClassVar[str] = "arrow-left-right"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    """Marks the block as interactive: it pauses for user input mid-run."""

    # ADR-051: the block-owned window, resolved from the built-in panel registry.
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(
        panel_id="core.interactive.pair_editor",
        version="1",
    )
    """Identifies the built-in UI panel the frontend opens when this block pauses."""

    variadic_inputs: ClassVar[bool] = True
    """When ``True``, the user adds and removes input ports instead of using a fixed list."""

    variadic_outputs: ClassVar[bool] = True
    """When ``True``, the output ports follow the input ports instead of using a fixed list."""

    allowed_input_types: ClassVar[list[type]] = []
    """Data types selectable for the variadic input ports; empty means any type."""

    allowed_output_types: ClassVar[list[type]] = []
    """Data types selectable for the variadic output ports; empty means any type."""

    min_input_ports: ClassVar[int | None] = 2
    """Fewest input ports the user may configure."""

    max_input_ports: ClassVar[int | None] = 8
    """Most input ports the user may configure."""

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        """Build the data the sortable panels need, while the block is paused.

        Called before the pause to describe the items the user will reorder.
        Runs in an isolated worker subprocess and checks that every input
        Collection has the same length.

        Args:
            inputs: Mapping of input port name to its Collection (or a single
                value), one entry per connected input port.
            config: The block configuration for this run.

        Returns:
            An :class:`~scistudio.blocks.base.interactive.InteractivePrompt`
            whose ``panel_payload`` carries ``ports`` (the port names),
            ``items_per_port`` (each port mapped to a list of item
            descriptors), and ``collection_length`` (the shared length of all
            Collections).

        Raises:
            ValueError: If the input Collections do not all have equal length.
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
                        "name": interactive_item_label(item, i),
                        "type": type(item).__name__,
                    }
                    items.append(item_desc)
            else:
                lengths[port_name] = 1
                items.append(
                    {
                        "index": 0,
                        "name": interactive_item_label(value, 0),
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

        return InteractivePrompt(
            panel_payload={
                "ports": ports,
                "items_per_port": items_per_port,
                "collection_length": collection_length,
            }
        )

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Reorder each Collection using the order the user chose in the panel.

        Emits each reordered Collection on the matching output port (output
        ports are named independently of the input ports, so results are placed
        by position). A port with no reorder entry, or a non-Collection input,
        is passed through unchanged.

        Args:
            inputs: Mapping of input port name to its Collection (or a single
                value).
            config: The block configuration. Its ``interactive_response``
                holds ``reorder``: a mapping of input port name to the list of
                item indices giving the new order (for example
                ``{"input_1": [2, 0, 1]}``).

        Returns:
            Mapping of output port name to the reordered Collection.

        Raises:
            ValueError: If the interactive response contains no reorder data,
                or if a reorder index list does not match its Collection's
                length.
        """
        from scistudio.core.types.collection import Collection

        response = config.get("interactive_response", {})
        reorder = response.get("reorder", {})

        if not reorder:
            raise ValueError("PairEditor received no reorder data from interactive response")

        # Outputs auto-mirror inputs positionally, but the output ports have
        # their own names (e.g. inputs ``input_1``/``input_2`` -> outputs
        # ``port_1``/``port_2``). The reorder decision is keyed by the *input*
        # port names, while the engine validates the block's declared *output*
        # port names — so emit each result under the i-th output port name, not
        # the input name (which would leave the required output ports unproduced).
        output_port_names = [p.name for p in self.get_effective_output_ports()]

        outputs: dict[str, Any] = {}
        for idx, (port_name, value) in enumerate(inputs.items()):
            out_name = output_port_names[idx] if idx < len(output_port_names) else port_name
            indices = reorder.get(port_name)
            if indices is None:
                # If no reorder specified for this port, pass through unchanged.
                outputs[out_name] = value
                continue

            if isinstance(value, Collection):
                items = list(value)
                if len(indices) != len(items):
                    raise ValueError(
                        f"PairEditor: reorder indices length ({len(indices)}) does not match "
                        f"Collection length ({len(items)}) for port '{port_name}'"
                    )
                reordered = [items[i] for i in indices]
                outputs[out_name] = Collection(reordered, item_type=value.item_type)
            else:
                # Single item — pass through.
                outputs[out_name] = value

        return outputs
