"""Starter template for a custom SciStudio ProcessBlock.

A ProcessBlock transforms a batch one item at a time: you write only
``process_item()`` and the base class loops over the first input port's
Collection, calls your method once per item, and packs the results onto the
first output port. Use it when every item is transformed on its own and the
number of items does not change (no filtering, merging, or splitting). For
anything else -- several outputs, cross-item logic, a different item count --
start from the basic ``Block`` template and write ``run()`` yourself.

Three steps to make it yours:

    1. Rename the class and edit ``name`` / ``description``.
    2. Name and describe the ports and parameters -- the GUI shows users only
       this text, so make each one distinct and plain.
    3. Fill in ``process_item()``.

Reading and building items:

    Type        item.to_memory() returns    construct one with
    ---------   -------------------------   ----------------------------------
    Array       numpy ndarray               Array(axes=["y", "x"], data=arr)
    DataFrame   pyarrow.Table               DataFrame(data=table)
    Series      pyarrow.Table               Series(data=table)
    Text        str                         Text(content="hello")
    Artifact    bytes                       Artifact(file_path=Path(...))

Expensive one-time work (loading a model, opening a connection) belongs in
``setup(self, config)``; whatever it returns arrives as ``state`` on every
``process_item`` call, and ``teardown(self, state)`` releases it afterwards.

The project's ``user-guide/writing-blocks.md`` has a longer walkthrough.
"""

from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock

# All built-in data types are imported here so you can switch a port to any of
# them without adding an import line. The "noqa" notes silence the linter for
# the types you have not used yet.
from scistudio.core.types import (
    Array,
    Artifact,  # noqa: F401
    DataFrame,  # noqa: F401
    Series,  # noqa: F401
    Text,  # noqa: F401
)


class MyProcessBlock(ProcessBlock):
    """Replace this docstring with a one-line description of what your block does."""

    # Shown in the block palette and on the node header.
    name: ClassVar[str] = "My Process Block"
    description: ClassVar[str] = "Describe what this block does."

    # The base class reads the FIRST input port and fills the FIRST output port.
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[Array], description="Describe what flows into this port."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[Array], description="Describe what this port produces."),
    ]

    # Parameters for the GUI panel (JSON Schema). ``title`` is the field label and
    # ``description`` explains it. Read them with config.get().
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "gain": {
                "type": "number",
                "title": "Gain",
                "description": "Multiplier applied to every value.",
                "default": 1.0,
            },
        },
    }

    def process_item(self, item: Array, config: BlockConfig, state: Any = None) -> Array:
        # >>> EDIT THIS <<<
        # Called once per item of the input Collection. Return one new item; the
        # base class collects the results into the output Collection.
        gain = config.get("gain", 1.0)
        arr = item.to_memory()  # numpy ndarray
        return Array(axes=list(item.axes), data=arr * gain)
