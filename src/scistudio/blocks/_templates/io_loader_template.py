"""Starter template for a custom SciStudio file loader.

A loader reads a file from disk into a SciStudio data object. Before writing
one, check the built-in Load block: with its data type set it already reads the
common formats, and every installed package plugs its own formats into it.
Write a custom loader only for a format nothing else reads.

``SimpleLoader`` (from ``scistudio.blocks.io``) handles the plumbing: set the
data type it produces, a short format name, and the file extensions it claims,
then write ``load_file()`` for ONE file. When the user selects several files the
runtime calls it once per file and collects the results into a Collection.

Three steps to make it yours:

    1. Rename the class and edit ``name`` / ``description``.
    2. Set ``output_type``, ``format_id`` and ``extensions``, and describe the
       output port -- the GUI shows users only this text.
    3. Fill in ``load_file()``.

Building the object you return:

    Type        construct one with
    ---------   -------------------------------------------
    Array       Array(axes=["y", "x"], data=numpy_array)
    DataFrame   DataFrame(data=pyarrow_table)
    Series      Series(data=pyarrow_table)
    Text        Text(content="hello")
    Artifact    Artifact(file_path=path)

The ``path`` parameter (a file picker) is provided by the base class; add your
own parameters to ``config_schema`` and read them from the ``config`` dict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from scistudio.blocks.base import OutputPort
from scistudio.blocks.io import SimpleLoader

# All built-in data types are imported here so you can switch the output type
# without adding an import line. The "noqa" notes silence the linter for the
# types you have not used yet.
from scistudio.core.types import (
    Array,  # noqa: F401
    Artifact,  # noqa: F401
    DataFrame,  # noqa: F401
    DataObject,
    Series,  # noqa: F401
    Text,
)


class MyLoader(SimpleLoader):
    """Replace this docstring with a one-line description of what your loader reads."""

    # Shown in the block palette and on the node header.
    name: ClassVar[str] = "My Loader"
    description: ClassVar[str] = "Describe which files this block reads."

    # What load_file() returns, and which files this loader claims. Use your real
    # extension(s); two loaders may not both claim the same extension for the
    # same data type.
    output_type: ClassVar[type[DataObject]] = Text
    extensions: ClassVar[tuple[str, ...]] = (".mytext",)
    format_id: ClassVar[str] = "my_text"

    # A loader has no input ports: it reads from its ``path`` parameter.
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[Text], description="Describe what this port produces."),
    ]

    # Extra parameters for the GUI panel (JSON Schema). ``title`` is the field
    # label and ``description`` explains it. The base class adds ``path``.
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "encoding": {
                "type": "string",
                "title": "Encoding",
                "description": "Character encoding of the file.",
                "default": "utf-8",
            },
        },
    }

    def load_file(self, path: Path, config: dict[str, Any]) -> Text:
        # >>> EDIT THIS <<<
        # Read the ONE file at ``path`` and return one ``output_type`` object.
        encoding = config.get("encoding", "utf-8")
        return Text(content=path.read_text(encoding=encoding), format="plain")
