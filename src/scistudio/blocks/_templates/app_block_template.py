"""Starter template for a custom SciStudio AppBlock.

An AppBlock hands a workflow step to an external program -- a desktop GUI
(Fiji, napari, an analysis app) or a command-line tool. You write almost no
code: declare the command and the ports, and the base ``run()`` does the rest.
It writes the block's inputs into an exchange folder, launches the program with
that folder's path as the last argument, waits until result files appear in the
output folder and stop changing, and hands them back on the output ports.

Three steps to make it yours:

    1. Rename the class and edit ``name`` / ``description``.
    2. Set ``app_command`` to the program to launch (users can also set it per
       workflow in the parameter panel) and ``output_patterns`` to the result
       files to wait for.
    3. Name and describe the ports -- the GUI shows users only this text.

You do NOT override ``run()``. If the program needs a generated config file or
a custom command line instead of the exchange-folder argument, override
``prepare_launch(self, exchange_dir, output_dir, config)``: write the file, then
return the argument list to launch with. Returning ``None`` keeps the default.

Files are exchanged as-is, so ``Artifact`` (an opaque file) is the usual port
type; use a concrete type such as ``DataFrame`` when the program reads or writes
a format SciStudio can convert.
"""

from __future__ import annotations

from typing import ClassVar

from scistudio.blocks.app import AppBlock
from scistudio.blocks.base import InputPort, OutputPort

# All built-in data types are imported here so you can switch a port to any of
# them without adding an import line. The "noqa" notes silence the linter for
# the types you have not used yet.
from scistudio.core.types import (
    Array,  # noqa: F401
    Artifact,
    DataFrame,  # noqa: F401
    Series,  # noqa: F401
    Text,  # noqa: F401
)


class MyAppBlock(AppBlock):
    """Replace this docstring with a one-line description of what the program does."""

    # Shown in the block palette and on the node header.
    name: ClassVar[str] = "My App Block"
    description: ClassVar[str] = "Describe what the external program does."

    # >>> EDIT THIS <<<
    # The program to launch: an executable path, optionally followed by its
    # arguments, for example "/Applications/Fiji.app/Contents/MacOS/ImageJ-macosx --headless".
    # Left empty, the user sets it in the parameter panel.
    app_command: ClassVar[str] = ""

    # Which files in the output folder count as results.
    output_patterns: ClassVar[list[str]] = ["*"]

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[Artifact], description="Describe what flows into this port."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="result", accepted_types=[Artifact], description="Describe what this port produces."),
    ]
