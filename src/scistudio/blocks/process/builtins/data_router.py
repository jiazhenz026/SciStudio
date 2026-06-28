"""DataRouter -- interactively route items from many inputs to many outputs.

A single interactive block that replaces separate merge/slice/split blocks:
the user drags items from any input port onto any output port. The number of
input and output ports is configurable rather than fixed.
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
from scistudio.core.types.base import DataObject

logger = logging.getLogger(__name__)


# Interaction model (pause/resume, worker subprocesses, panel manifest) is
# specified in ADR-051; the variadic port system in ADR-029.
class DataRouter(InteractiveMixin, ProcessBlock):
    """Route items from several inputs to several outputs, by hand.

    Add as many input and output ports as you need, then wire data to them.
    When the workflow reaches this block it pauses and opens a drag-and-drop
    panel: drag each item from an input port onto the output port you want it
    to leave by. Use it to merge, split, or re-sort items across branches
    without writing code.

    Ports: variadic on both sides -- the user adds input and output ports as
    needed (at least one of each). Reads every connected input Collection and
    emits one Collection per output port holding the items routed to it.
    Config: reads ``interactive_response.assignments``, a mapping of output
    port name to the list of item references the user dragged onto it; the
    framework fills this in from the panel, so there is nothing to set by hand.

    This block is used by wiring it into a workflow and interacting with its
    panel; it is not meant to be subclassed.
    """

    name: ClassVar[str] = "Data Router"
    """Display name shown in the block palette and on the canvas node."""

    description: ClassVar[str] = "Interactive drag-and-drop routing of items from N inputs to M outputs"
    """One-line summary shown in the palette and node tooltip."""

    algorithm: ClassVar[str] = "data_router"
    """Stable identifier for this block's transform; recorded in metadata."""

    subcategory: ClassVar[str] = "routing"
    """Palette subgroup this block is filed under (here, ``"routing"``)."""

    # #1839 / #1847: macaron periwinkle + a split glyph for the N->M routing
    # block. The ":90" suffix rotates the glyph 90deg to read left->right, in
    # line with the canvas data-flow direction (rotation parsed by the frontend
    # ui_icon resolver in categoryVisuals.ts).
    ui_color: ClassVar[str] = "#aec5eb"
    ui_icon: ClassVar[str] = "split:90"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    """Marks the block as interactive: it pauses for user input mid-run."""

    # ADR-051: the block-owned window. Resolved by the frontend panel host from
    # the built-in panel registry (core panel; no wheel-served module_url).
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(
        panel_id="core.interactive.data_router",
        version="1",
    )
    """Identifies the built-in UI panel the frontend opens when this block pauses."""

    variadic_inputs: ClassVar[bool] = True
    """When ``True``, the user adds and removes input ports instead of using a fixed list."""

    variadic_outputs: ClassVar[bool] = True
    """When ``True``, the user adds and removes output ports instead of using a fixed list."""

    allowed_input_types: ClassVar[list[type]] = []
    """Data types selectable for the variadic input ports; empty means any type."""

    allowed_output_types: ClassVar[list[type]] = []
    """Data types selectable for the variadic output ports; empty means any type."""

    min_input_ports: ClassVar[int | None] = 1
    """Fewest input ports the user may configure."""

    min_output_ports: ClassVar[int | None] = 1
    """Fewest output ports the user may configure."""

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        """Build the data the drag-and-drop panel needs, while the block is paused.

        Called before the pause to describe the items the user will route. Runs
        in an isolated worker subprocess.

        Args:
            inputs: Mapping of input port name to its Collection (or a single
                value), one entry per connected input port.
            config: The block configuration for this run.

        Returns:
            An :class:`~scistudio.blocks.base.interactive.InteractivePrompt`
            whose ``panel_payload`` carries ``input_ports`` (the input port
            names), ``items_per_port`` (each port mapped to a list of item
            descriptors), and ``output_ports`` (the output port names). It
            holds no references because this block reuses nothing between the
            prompt and the routing step.
        """
        from scistudio.core.types.collection import Collection

        input_ports = list(inputs.keys())
        items_per_port: dict[str, list[dict[str, Any]]] = {}

        for port_name, value in inputs.items():
            items: list[dict[str, Any]] = []
            if isinstance(value, Collection):
                for i, item in enumerate(value):
                    item_desc: dict[str, Any] = {
                        "index": i,
                        "port": port_name,
                        "ref": f"{port_name}:{i}",
                        "name": interactive_item_label(item, i),
                        "type": type(item).__name__,
                    }
                    items.append(item_desc)
            else:
                items.append(
                    {
                        "index": 0,
                        "port": port_name,
                        "ref": f"{port_name}:0",
                        "name": interactive_item_label(value, 0),
                        "type": type(value).__name__,
                    }
                )
            items_per_port[port_name] = items

        # Read output port names from config.
        effective_output_ports = self.get_effective_output_ports()
        output_port_names = [p.name for p in effective_output_ports]

        return InteractivePrompt(
            panel_payload={
                "input_ports": input_ports,
                "items_per_port": items_per_port,
                "output_ports": output_port_names,
            }
        )

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Route items from inputs to outputs using the user's panel choices.

        Reads the assignments the user made in the panel and emits one
        Collection per output port. If two routed items disagree on type, the
        output Collection widens to the common ``DataObject`` type so mixed
        routing does not fail.

        Args:
            inputs: Mapping of input port name to its Collection (or a single
                value).
            config: The block configuration. Its ``interactive_response``
                holds ``assignments``: a mapping of output port name to the
                list of item references (each ``"input_port:index"``) the user
                dragged onto that port.

        Returns:
            Mapping of output port name to the Collection of items routed there.

        Raises:
            ValueError: If the interactive response contains no assignments.
        """
        from scistudio.core.types.collection import Collection

        response = config.get("interactive_response", {})
        assignments = response.get("assignments", {})

        if not assignments:
            raise ValueError("DataRouter received no assignments from interactive response")

        # Build a lookup of all input items by ref.
        item_lookup: dict[str, Any] = {}
        item_type: type | None = None
        for port_name, value in inputs.items():
            if isinstance(value, Collection):
                if item_type is None and value.item_type is not None:
                    item_type = value.item_type
                for i, item in enumerate(value):
                    item_lookup[f"{port_name}:{i}"] = item
            else:
                if item_type is None:
                    item_type = type(value)
                item_lookup[f"{port_name}:0"] = value

        # Route items to output ports per the user's assignments.
        # Derive item_type per output batch: if all items share the same
        # type use it; otherwise widen to DataObject so mixed-type routing
        # (items from different input ports) doesn't fail.
        outputs: dict[str, Any] = {}
        for output_port, item_refs in assignments.items():
            routed_items = []
            for ref in item_refs:
                if ref not in item_lookup:
                    logger.warning("DataRouter: unknown item ref '%s', skipping", ref)
                    continue
                routed_items.append(item_lookup[ref])
            if routed_items:
                types_seen = {type(item) for item in routed_items}
                batch_type = types_seen.pop() if len(types_seen) == 1 else DataObject
            else:
                batch_type = DataObject
            outputs[output_port] = Collection(routed_items, item_type=batch_type)

        return outputs
