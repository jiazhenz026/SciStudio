"""SciStudio's built-in core loaders.

This sub-package holds the framework's general-purpose loader block,
:class:`LoadData`. One block reads any of the six core data types from a file:
its ``core_type`` setting picks the type, which also colours the output port to
match. These are internal building blocks — most authors write their own loader
on :class:`~scistudio.blocks.io.SimpleLoader` instead.
"""

from __future__ import annotations

from scistudio.blocks.io.loaders.load_data import LoadData

__all__ = ["LoadData"]
