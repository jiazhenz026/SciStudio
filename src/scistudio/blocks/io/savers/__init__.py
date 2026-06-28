"""SciStudio's built-in core savers.

This sub-package holds the framework's general-purpose saver block,
:class:`SaveData`. One block writes any of the six core data types to a file: its
``core_type`` setting picks the type, which also retypes the input port. These
are internal building blocks — most authors write their own saver on
:class:`~scistudio.blocks.io.SimpleSaver` instead.
"""

from __future__ import annotations

from scistudio.blocks.io.savers.save_data import SaveData

__all__ = ["SaveData"]
