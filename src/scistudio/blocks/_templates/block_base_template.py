"""Starter template for a custom SciStudio block.

The "New custom block" action copies this file into
``<project>/blocks/<name>.py`` and opens it for editing. Three steps to make
it yours:

    1. Rename ``MyBlock`` and edit ``name`` / ``description``.
    2. Declare your input/output ports and parameters.
    3. Fill in ``run()`` with your logic.

Everything you need is in the sections below. Read the part you care about and
skip the rest.

====================================================================
1. WHAT IS A BLOCK -- and which base class to inherit
====================================================================

A block is one step in a workflow: it takes typed inputs, does some work, and
returns typed outputs. Users wire blocks together on the canvas.

Most custom blocks subclass ``Block`` (this template). Other base classes
exist for special jobs:

    Block         General work. You write run() yourself, and you see the
                  data in batches (Collections). <- this template.
    ProcessBlock  One item in, one item out. You write only
                  process_item(self, item, config) and the base class loops
                  over the batch for you. Use it when every item is
                  transformed independently and the number of items does not
                  change (no filtering, no merging, no splitting).
    IOBlock       Load or save files. You write load() or save().
    AppBlock      Hand work to an external GUI application.
    CodeBlock     Run a project-local Python / R / Julia script.

When unsure, stay on ``Block``: it can do anything the others can.

====================================================================
2. DATA TYPES -- what flows between blocks
====================================================================

Every value is a "DataObject". Call ``item.to_memory()`` to read the real
value. What you get back depends on the type:

    Type        item.to_memory() returns    construct one with
    ---------   -------------------------   ----------------------------------
    Array       numpy ndarray               Array(axes=["y", "x"], data=arr)
    DataFrame   pyarrow.Table  (*)          DataFrame(data=table)
    Series      pyarrow.Table               Series(data=table)
    Text        str                         Text(content="hello")
    Artifact    bytes                       Artifact(file_path=Path(...))

    (*) DataFrame/Series give you an Arrow table. For a pandas frame:
        df = item.to_memory().to_pandas()
        ...and build one back with:
        DataFrame(data=pyarrow.Table.from_pandas(df))

Domain packages add more types (e.g. Image, Spectrum) -- see section 7.

====================================================================
3. COLLECTIONS -- data arrives in batches
====================================================================

Batch processing is the norm for scientific data, so every port carries a
``Collection``: an ordered group of same-type items. A single value is a
Collection of length 1; "no data" is an empty Collection. You decide how to
loop over it.

Read items directly::

    for item in inputs["input"]:     # each item is one DataObject
        data = item.to_memory()      # the real value (see the table above)

Helper methods on ``self`` so you do not manage storage by hand::

    self.map_items(fn, coll)       apply fn to each item -> Collection
                                   (low memory: one item at a time)
    self.parallel_map(fn, coll)    same, but in parallel (uses more memory)
    self.pack(items, item_type=T)  build a Collection from a list of items
    self.unpack(coll)              -> a plain list of items
    self.unpack_single(coll)       -> the single item (errors if not exactly 1)

====================================================================
4. PORTS & PARAMETERS
====================================================================

Ports are typed connection points, declared as class attributes::

    input_ports  = [InputPort(name="input",  accepted_types=[Array])]
    output_ports = [OutputPort(name="output", accepted_types=[Array])]

``accepted_types`` controls what may connect. Always name a concrete type
(Array, DataFrame, Series, Text, Artifact, or a package type like Image) so
the canvas can type-check connections and choose a preview. ``[]`` means
"accept anything" -- avoid it unless you truly mean it. Optional keywords:
``description=`` (shown in the UI), ``required=False`` (optional input),
``default=``.

Parameters are a JSON Schema in ``config_schema``; it renders the GUI
parameter panel. Read values inside run() with ``config.get(name, default)``::

    config_schema = {"type": "object", "properties": {
        "gain":   {"type": "number", "default": 1.0},
        "method": {"type": "string", "enum": ["a", "b"], "default": "a"},
    }}
    # inside run():
    gain = config.get("gain", 1.0)

====================================================================
5. WRITING run()
====================================================================

Signature::

    def run(self, inputs: dict[str, Collection],
            config: BlockConfig) -> dict[str, Collection]:

    * ``inputs[port_name]`` is the ``Collection`` arriving on that input port.
    * Return a dict keyed by your OUTPUT port names; each value is a
      ``Collection`` of the declared type.

====================================================================
6. Minimal examples (batch processing)
====================================================================

Array -- scale every image in the batch by a ``gain`` parameter::

    from scistudio.core.types.array import Array

    def run(self, inputs, config):
        gain = config.get("gain", 1.0)

        def scale(item):
            arr = item.to_memory()                  # numpy ndarray
            return Array(axes=list(item.axes), data=arr * gain)

        return {"output": self.map_items(scale, inputs["input"])}

DataFrame -- keep only the numeric columns of every table in the batch::

    import pyarrow as pa
    from scistudio.core.types.dataframe import DataFrame

    def run(self, inputs, config):
        def numeric_only(item):
            df = item.to_memory().to_pandas()       # pyarrow.Table -> pandas
            numeric = df.select_dtypes(include="number")
            return DataFrame(data=pa.Table.from_pandas(numeric))

        return {"output": self.map_items(numeric_only, inputs["input"])}

====================================================================
7. PACKAGE-SPECIFIC TYPES & HELPERS
====================================================================

Installed domain packages (imaging, lcms, spectroscopy, ...) add their own
types (e.g. Image) and helper functions on top of the core types above. To
find what a package gives you, read THAT package's own documentation.

Do not import a package's private, underscore-prefixed modules (for example
``_support``): they are internal and may change without notice. A public,
browsable list of installed packages and the types/helpers they export is
being built; until it ships, the package's own docs are the source of truth.
"""

from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base import (
    Block,
    BlockConfig,
    InputPort,
    OutputPort,
)
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection


class MyBlock(Block):
    """Replace this docstring with a one-line description of what your block does."""

    # Shown in the block palette and on the node header.
    name: ClassVar[str] = "My Block"
    description: ClassVar[str] = "Describe what this block does."

    # Typed ports. Change ``accepted_types`` to the concrete type you handle
    # (Array, DataFrame, Series, Text, Artifact, or a package type like Image).
    # Prefer a concrete type over ``[]`` so connections are type-checked.
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[Array], description="Input data"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[Array], description="Output data"),
    ]

    # Parameters for the GUI panel (JSON Schema). Read them with config.get().
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "gain": {"type": "number", "default": 1.0},
        },
    }

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        # >>> EDIT THIS <<<
        # Batch example: scale every input Array by the ``gain`` parameter.
        # ``map_items`` runs your function on each item in the Collection and
        # packs the results back into a Collection, one item in memory at a
        # time. See section 6 of the header for a DataFrame version, and
        # section 3 for the other Collection helpers.
        gain = config.get("gain", 1.0)

        def scale(item: Array) -> Array:
            arr = item.to_memory()  # numpy ndarray (see the type table above)
            return Array(axes=list(item.axes), data=arr * gain)

        return {"output": self.map_items(scale, inputs["input"])}
