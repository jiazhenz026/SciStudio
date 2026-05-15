"""Starter template for a custom SciEasy block (per ADR-036 §3.12).

The "New custom block" action in the toolbar copies this file into
``<project>/blocks/<name>.py`` and opens it in the editor. Replace the
placeholder body below with real logic.

Quick reference
---------------

config_schema is a JSON Schema describing the block's parameters. Common
shapes:

  {"type": "object", "properties": {
      "threshold": {"type": "number", "default": 0.5},
      "method":    {"type": "string", "enum": ["otsu", "li"], "default": "otsu"},
  }}

Inside ``run()``:
  - ``inputs[port_name]`` is the value delivered on each input port.
  - ``self.config["threshold"]`` etc. read parameter values.
  - Return a ``BlockResult`` whose ``outputs`` dict keys match this
    block's declared output port names.

NOTE for ADR-036 skeleton agent (S36): the dispatch prompt asked for
``from scieasy.blocks.base import Block, BlockSpec, PortSpec``. In the
current codebase, ``BlockSpec`` lives in ``scieasy.blocks.registry`` and
the port classes are ``InputPort``/``OutputPort`` (no ``PortSpec``). The
imports below use the real symbols so the file compiles. Implementation
phase agent (I36c) should keep this template in lockstep with whatever
``base/__init__.py`` exports at the time they wire up the endpoint.
"""

from __future__ import annotations

from typing import Any, ClassVar

from scieasy.blocks.base import (
    Block,
    BlockConfig,
    InputPort,
    OutputPort,
)
from scieasy.core.types.collection import Collection


class MyBlock(Block):
    """Replace this docstring with what your block does."""

    # Static port declarations. Edit ``accepted_types`` to constrain
    # what flows in/out (use any subclass of ``DataObject``).
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[]),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[]),
    ]

    # JSON Schema for the parameters panel rendered in the GUI.
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            # Example: "threshold": {"type": "number", "default": 0.5},
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        # >>> EDIT THIS <<<
        # Read inputs from ``inputs["<port_name>"]``, do work, and return
        # a dict keyed by output port names. Each value is a Collection
        # holding one or more DataObject instances of the declared type.
        raise NotImplementedError("fill in MyBlock.run()")
