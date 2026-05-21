"""Example block implementation for {package_name}.

This module demonstrates a minimal SciEasy block following the
block contract (ADR-017). Blocks extend ``ProcessBlock`` for
data transformations, or ``Block`` directly for custom logic.

Tier 1 (recommended): Override ``process_item()`` only.
  - The engine iterates the input Collection for you.
  - Peak memory = O(1 item).

Tier 2/3 (advanced): Override ``run()`` directly.
  - Use ``map_items()`` or ``parallel_map()`` for batch processing.
  - Use ``pack()`` / ``unpack()`` for manual Collection handling.
"""

from __future__ import annotations

from typing import Any, ClassVar

from scieasy.blocks.base.block import Block
from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.base.state import ExecutionMode
from scieasy.blocks.process.process_block import ProcessBlock


class ExampleBlock(ProcessBlock):
    """Example processing block that passes data through unchanged.

    Replace this with your own transformation logic.
    """

    name: ClassVar[str] = "{display_name} Example"
    description: ClassVar[str] = "Example block from {package_name}"
    version: ClassVar[str] = "0.1.0"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", produced_type=None),
    ]

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.AUTO
    algorithm: ClassVar[str] = "passthrough"

    def process_item(self, item: Any, config: BlockConfig) -> Any:
        """Process a single item from the input Collection.

        This is the Tier 1 entry point. The engine calls this method
        once per item in the input Collection, handling iteration and
        memory management automatically.

        Args:
            item: A single DataObject from the input Collection.
            config: Block configuration parameters.

        Returns:
            A DataObject to include in the output Collection.
        """
        # TODO: Replace with your transformation logic.
        return item
