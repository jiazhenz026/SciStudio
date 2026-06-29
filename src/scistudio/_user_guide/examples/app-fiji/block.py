"""Hand work to an external GUI app — an AppBlock example.

``FijiMacro`` sends an image file to Fiji (ImageJ), runs a macro on it, and
reads the processed image back. This is what ``AppBlock`` is for: any tool that
works on files — Fiji, ImageJ, CellProfiler, a command-line program — can be a
block, headless or interactive.

You write almost no code. An ``AppBlock`` subclass just *declares* the command
and the ports; the base ``run()`` does the rest: it writes your inputs into an
exchange folder, launches the app, waits for the output files to appear, and
hands them back as typed outputs. You do NOT override ``run()``.

Copy this file into ``blocks/`` in your project and edit the two paths marked
``# EDIT``.
"""

from __future__ import annotations

from typing import ClassVar

from scistudio.blocks.app import AppBlock
from scistudio.blocks.base import InputPort, OutputPort
from scistudio.core.types import Artifact


class FijiMacro(AppBlock):
    """Run a Fiji/ImageJ macro on an image file and return the result."""

    name: ClassVar[str] = "Fiji Macro"
    description: ClassVar[str] = "Process an image in Fiji using a saved macro."

    # The command to launch. The base run() appends the exchange-folder path as
    # the final argument, which the macro reads with getArgument().
    #   EDIT the Fiji path and the macro path for your machine.
    app_command: ClassVar[list[str]] = [
        "/Applications/Fiji.app/Contents/MacOS/ImageJ-macosx",  # EDIT: your Fiji
        "--headless",
        "-macro",
        "gaussian_blur.ijm",                                    # EDIT: macro path
    ]

    # Image files in and out. Artifact = an opaque file; Fiji reads/writes TIFF
    # natively, so passing the file straight through is the natural fit.
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Artifact], description="Image file for Fiji"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="result", accepted_types=[Artifact], description="Processed image"),
    ]

    # Which files in the output folder count as "done". The base run() watches
    # for files matching these patterns and waits until they stop changing.
    output_patterns: ClassVar[list[str]] = ["*.tif"]
