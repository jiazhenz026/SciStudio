"""Trivial fixture ProcessBlock.

A package-owned, non-IO block so the fixture surfaces an entry in the block
palette with a ``package_name`` (core hides package IO blocks by aggregating
their capabilities onto Load/Save, so an IO-only package would never appear in
the palette). Identity pass-through; zero real behaviour.
"""

from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject


class FixtureNoop(ProcessBlock):
    """Identity pass-through process block owned by the fixture package."""

    type_name: ClassVar[str] = "fixture.noop"
    name: ClassVar[str] = "Fixture Noop"
    description: ClassVar[str] = "Fixture-only identity pass-through process block."
    algorithm: ClassVar[str] = "fixture_noop"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[DataObject], description="Primary input"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[DataObject], description="Primary output"),
    ]
    config_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
        del config, state
        return item
