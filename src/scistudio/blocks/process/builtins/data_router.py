"""DataRouter -- interactive N-input to M-output item routing.

#591: Replaces separate Merge Selection / Slice Collection / Split Collection
blocks with a single interactive block that lets users drag items from
any input port to any output port.

First consumer of ADR-029 variadic port system.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import InteractiveMixin, InteractivePrompt, PanelManifest
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject

logger = logging.getLogger(__name__)


class DataRouter(InteractiveMixin, ProcessBlock):
    """Interactive N-to-M data routing block.

    Users configure variadic input/output ports (ADR-029). At runtime the
    block pauses with a drag-and-drop UI for manually routing items from
    inputs to outputs.

    ADR-051: a processing block that carries the interaction capability
    (``InteractiveMixin`` + ``execution_mode = INTERACTIVE``). It runs as two
    worker subprocesses around an engine-held pause and opens its window through
    the :attr:`interactive_panel` manifest rather than a hardcoded frontend
    branch. Its item-routing behaviour is unchanged.

    Runtime flow:
        1. User configures N input ports + M output ports via variadic editor
        2. Workflow reaches DataRouter; prompt phase builds the panel view
           (subprocess) -> PAUSED
        3. Frontend resolves the panel from the manifest (drag items inputs->outputs)
        4. Confirm -> assignments sent to backend -> compute phase routes items -> DONE
    """

    name: ClassVar[str] = "Data Router"
    description: ClassVar[str] = "Interactive drag-and-drop routing of items from N inputs to M outputs"
    algorithm: ClassVar[str] = "data_router"
    subcategory: ClassVar[str] = "routing"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE

    # ADR-051: the block-owned window. Resolved by the frontend panel host from
    # the built-in panel registry (core panel; no wheel-served module_url).
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(
        panel_id="core.interactive.data_router",
        version="1",
    )

    variadic_inputs: ClassVar[bool] = True
    variadic_outputs: ClassVar[bool] = True
    allowed_input_types: ClassVar[list[type]] = []
    allowed_output_types: ClassVar[list[type]] = []
    min_input_ports: ClassVar[int | None] = 1
    min_output_ports: ClassVar[int | None] = 1

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        """Build the panel view for the interactive prompt (ADR-051 prompt phase).

        Runs in an isolated worker subprocess. Returns an
        :class:`~scistudio.blocks.base.interactive.InteractivePrompt` whose
        ``panel_payload`` carries:
            input_ports: list of port name strings
            items_per_port: dict mapping port name to list of item descriptors
            output_ports: list of output port name strings
        DataRouter needs no intermediate reuse, so it returns no references.
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
                        "name": getattr(item, "name", None) or f"item_{i}",
                        "type": type(item).__name__,
                    }
                    items.append(item_desc)
            else:
                items.append(
                    {
                        "index": 0,
                        "port": port_name,
                        "ref": f"{port_name}:0",
                        "name": getattr(value, "name", None) or "item_0",
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
        """Route items from inputs to outputs based on user assignments.

        The ``interactive_response`` in config contains:
            assignments: dict mapping output port name to list of item refs
                (each ref is "input_port:index")
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
