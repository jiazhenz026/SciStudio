"""Block authoring surface.

The canonical place to import block-authoring symbols from:
``from scistudio.blocks.base import …``. The supported public surface is exactly
this module's ``__all__``. Everything else here (``Port`` and the port helpers,
``BlockState``, ``BlockResult``, and the internal interactive plumbing) stays
importable via its deep path but carries no stability promise, so prefer the
names below.
"""

from __future__ import annotations

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import (
    INTERACTIVE_RESPONSE_KEY,
    PANEL_API_VERSION,
    InteractiveMixin,
    InteractivePrompt,
    PanelManifest,
    load_intermediate,
)
from scistudio.blocks.base.package_info import PackageInfo, PackageOtaSource
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.base.state import ExecutionMode

__all__ = [
    "INTERACTIVE_RESPONSE_KEY",
    "PANEL_API_VERSION",
    "Block",
    "BlockConfig",
    "ExecutionMode",
    "InputPort",
    "InteractiveMixin",
    "InteractivePrompt",
    "OutputPort",
    "PackageInfo",
    "PackageOtaSource",
    "PanelManifest",
    "load_intermediate",
]
