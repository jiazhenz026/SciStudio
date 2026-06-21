"""Starter template for a custom SciStudio block.

The "New custom block" toolbar action copies this file into
``<project>/blocks/<name>.py`` and opens it for editing. Rename ``MyBlock``,
declare your ports and parameters, then fill in ``run()``.

Quick reference
---------------

Ports — typed connection points on the block, declared as class attributes::

    input_ports  = [InputPort(name="input",  accepted_types=[DataFrame])]
    output_ports = [OutputPort(name="output", accepted_types=[DataFrame])]

  ``accepted_types`` restricts what may connect: any ``DataObject`` subclass
  (``DataFrame``, ``Array``, ``Series``, ``Text``, ``Artifact`` ...). An empty
  list ``[]`` accepts anything. Optional keywords: ``description=`` (shown in
  the UI), ``required=False`` (make an input optional), ``default=``.

Parameters — ``config_schema`` is a JSON Schema that renders the GUI
parameter panel. Read values inside ``run()`` with ``config.get(name, default)``::

    config_schema = {"type": "object", "properties": {
        "threshold": {"type": "number", "default": 0.5},
        "method":    {"type": "string", "enum": ["otsu", "li"], "default": "otsu"},
    }}
    # inside run():
    threshold = config.get("threshold", 0.5)

run() — signature ``run(self, inputs, config) -> dict[str, Collection]``::

    * ``inputs[port_name]`` is the ``Collection`` arriving on that input port.
    * Iterate a Collection to get its ``DataObject`` items; read the native
      value with ``item.to_memory()`` — an Arrow table for ``DataFrame`` (call
      ``.to_pandas()`` for a pandas frame), a numpy array for ``Array``, etc.
    * Return a dict keyed by your OUTPUT port names. Each value is a
      ``Collection`` of DataObjects of the declared type; build one with
      ``Collection([obj, ...], item_type=DataFrame)``.

Minimal example — keep only the numeric columns of each input table::

    from scistudio.core.types.dataframe import DataFrame

    def run(self, inputs, config):
        results = []
        for item in inputs["input"]:
            table = item.to_memory().to_pandas()   # Arrow table -> pandas DataFrame
            numeric = table.select_dtypes(include="number")
            results.append(DataFrame(data=numeric))
        return {"output": Collection(results, item_type=DataFrame)}
"""

from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base import (
    Block,
    BlockConfig,
    InputPort,
    OutputPort,
)
from scistudio.core.types.collection import Collection


class MyBlock(Block):
    """Replace this docstring with a one-line description of what your block does."""

    # Shown in the block palette and on the node header.
    name: ClassVar[str] = "My Block"
    description: ClassVar[str] = "Describe what this block does."

    # Typed ports. Edit ``accepted_types`` to constrain connections to any
    # ``DataObject`` subclass; an empty list ``[]`` accepts anything.
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[], description="Input data"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[], description="Output data"),
    ]

    # JSON Schema for the parameters panel rendered in the GUI.
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            # "threshold": {"type": "number", "default": 0.5},
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        # >>> EDIT THIS <<<
        # Read parameters with ``config.get("name", default)`` and input
        # Collections from ``inputs["<input_port_name>"]``. Do your work, then
        # return a dict keyed by your output port names, each value a Collection.
        #
        # The default below passes the input straight through unchanged.
        # Replace it with your own logic (see "Minimal example" above).
        return {"output": inputs["input"]}
