"""Core IO loaders for SciStudio (ADR-028 Addendum 1).

This sub-package hosts the dynamic-port core loader blocks introduced
by ADR-028 Addendum 1 §C9. The canonical entry point is
:class:`LoadData`, a single block that uses the ``core_type`` enum to
drive a per-instance ``OutputPort`` accepted-types override and
dispatches its actual file-reading work to module-level private
``_load_*`` functions inside :mod:`scistudio.blocks.io.loaders.load_data`.
"""

from __future__ import annotations

from scistudio.blocks.io.loaders.load_data import LoadData

__all__ = ["LoadData"]
