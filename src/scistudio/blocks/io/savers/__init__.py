"""Core IO savers for SciStudio (ADR-028 Addendum 1).

This sub-package hosts the dynamic-port core saver blocks introduced
by ADR-028 Addendum 1 §C9. The canonical entry point is
:class:`SaveData`, a single block that uses the ``core_type`` enum to
drive a per-instance ``InputPort`` accepted-types override and
dispatches its actual file-writing work to module-level private
``_save_*`` functions inside :mod:`scistudio.blocks.io.savers.save_data`.
"""

from __future__ import annotations

from scistudio.blocks.io.savers.save_data import SaveData

__all__ = ["SaveData"]
