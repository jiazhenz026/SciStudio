# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/_user_guide/']`, which
# package-wide runs honor but explicit-file runs do not (the gate's narrowed
# check and the pre-commit hook pass files by name, #2115): this file ships as
# project *data* a reader copies into their project and edits, not a module the
# package imports.
#
"""Open an image in Fiji — an AppBlock example.

``OpenInFiji`` hands an image file to **Fiji (ImageJ)** and waits while you
review or edit it. There is no macro and nothing to script: the block inherits
``run()`` from ``AppBlock``, and the base class does the whole exchange — it
stages the input into an exchange folder, launches the app, watches for the
files you save, and packs them back onto the output port. (The imaging
package's built-in Fiji block follows the same shape; it adds batch staging
and a macro option on top of this contract.)

Copy ``open_in_fiji.py`` into ``blocks/`` in your project and edit it.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from scistudio.blocks.app import AppBlock
from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.core.types import Artifact


class OpenInFiji(AppBlock):
    """Open an image in Fiji; the step finishes when a result file is saved."""

    name: ClassVar[str] = "Open in Fiji"
    description: ClassVar[str] = "Open an image in Fiji for interactive review or editing."

    # The executable. Usually left empty and set per workflow in the parameter
    # panel (its config field is a file browser); hard-code it here if your
    # install path is fixed, e.g.
    # "/Applications/Fiji.app/Contents/MacOS/ImageJ-macosx" (macOS) or
    # "C:\\Program Files\\Fiji\\fiji-windows-x64.exe" (Windows).
    app_command: ClassVar[str] = ""

    # The result files the watcher waits for in the exchange's outputs/ folder:
    # a TIFF you re-saved, or a ROI set (.zip/.roi) you exported.
    output_patterns: ClassVar[list[str]] = ["*.tif", "*.tiff", "*.zip", "*.roi"]

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Artifact], description="The image file to open in Fiji."),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="result", accepted_types=[Artifact], description="The files saved from Fiji."),
    ]

    def prepare_launch(self, exchange_dir: Path, output_dir: Path, config: BlockConfig) -> list[str] | None:
        """Hand Fiji the staged image paths so it opens them on launch.

        The only customization in this block. By default ``AppBlock`` launches
        the app with the exchange folder as its trailing argument; a GUI Fiji
        opens *files*, not folders, so this override passes the staged input
        files directly (the imaging package's Fiji block does the same, #420).
        ``output_dir`` is where the watcher expects saved results. Returning
        ``None`` would keep the default exchange-folder behavior — the right
        choice for apps that read the folder themselves.
        """
        return [str(p) for p in sorted((exchange_dir / "inputs").rglob("*")) if p.is_file()]
