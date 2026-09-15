"""Starter template for a custom SciStudio file saver.

A saver writes a SciStudio data object to a file on disk. Before writing one,
check the built-in Save block: with its data type set it already writes the
common formats, and every installed package plugs its own formats into it.
Write a custom saver only for a format nothing else writes.

``SimpleSaver`` (from ``scistudio.blocks.io``) handles the plumbing: set the
data type it accepts, a short format name, and the file extensions it claims,
then write ``save_file()`` for ONE object. The base class checks the incoming
object's type and resolves the destination ``path`` for you.

Three steps to make it yours:

    1. Rename the class and edit ``name`` / ``description``.
    2. Set ``input_type``, ``format_id`` and ``extensions``, and describe the
       input port -- the GUI shows users only this text.
    3. Fill in ``save_file()``.

Reading the object you receive:

    Type        obj.to_memory() returns
    ---------   -------------------------
    Array       numpy ndarray
    DataFrame   pyarrow.Table
    Series      pyarrow.Table
    Text        str
    Artifact    bytes

The ``path`` parameter is provided by the base class; add your own parameters
to ``config_schema`` and read them from the ``config`` dict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from scistudio.blocks.base import InputPort, OutputPort
from scistudio.blocks.io import SimpleSaver

# All built-in data types are imported here so you can switch the input type
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


class MySaver(SimpleSaver):
    """Replace this docstring with a one-line description of what your saver writes."""

    # Shown in the block palette and on the node header.
    name: ClassVar[str] = "My Saver"
    description: ClassVar[str] = "Describe which files this block writes."

    # What save_file() accepts, and which files this saver writes. Use your real
    # extension(s); two savers may not both claim the same extension for the
    # same data type.
    input_type: ClassVar[type[DataObject]] = Text
    extensions: ClassVar[tuple[str, ...]] = (".mytext",)
    format_id: ClassVar[str] = "my_text"

    # A saver takes the object to write on its input port. It has no output
    # ports: the written path is reported back automatically.
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[Text], description="Describe what flows into this port."),
    ]
    output_ports: ClassVar[list[OutputPort]] = []

    # Extra parameters for the GUI panel (JSON Schema). ``title`` is the field
    # label and ``description`` explains it. The base class adds ``path``.
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "encoding": {
                "type": "string",
                "title": "Encoding",
                "description": "Character encoding of the written file.",
                "default": "utf-8",
            },
        },
    }

    def save_file(self, obj: DataObject, path: Path, config: dict[str, Any]) -> None:
        # >>> EDIT THIS <<<
        # Write the ONE object ``obj`` (a Text, checked by the base class) to ``path``.
        encoding = config.get("encoding", "utf-8")
        path.write_text(obj.to_memory(), encoding=encoding)
