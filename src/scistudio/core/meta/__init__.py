"""scistudio.core.meta — stratified metadata public surface.

Implements ADR-027 D5: framework / meta / user three-slot model on
``DataObject``.

Public API:

- :class:`FrameworkMeta` — frozen Pydantic ``BaseModel`` for the
  ``framework`` slot, populated by the framework at object creation
  time.
- :class:`ChannelInfo` — frozen Pydantic ``BaseModel`` used by plugin
  ``Meta`` classes that describe acquisition channels (e.g.
  ``FluorImage.Meta.channels``). Lives in core so that multiple plugin
  packages can compose it without forcing a plugin → plugin import
  (ADR-027 D5 §"Question 3").
- :func:`with_meta_changes` — free-function helper backing
  ``DataObject.with_meta()`` (T-005). Pure operation on a Pydantic
  ``BaseModel``; does not depend on ``DataObject``.

This module deliberately does NOT export ``DataObject``; that lives in
``scistudio.core.types.base`` and is updated by T-005.
"""

from __future__ import annotations

from scistudio.core.meta._with_meta import with_meta_changes
from scistudio.core.meta.channel import ChannelInfo
from scistudio.core.meta.framework import FrameworkMeta

__all__ = [
    "ChannelInfo",
    "FrameworkMeta",
    "with_meta_changes",
]
