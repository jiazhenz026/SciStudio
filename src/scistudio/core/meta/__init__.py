"""Stratified metadata public surface for ``DataObject``.

A ``DataObject`` keeps its metadata in three separate slots so that
framework-managed facts, plugin-declared descriptors, and free-form user notes
never overwrite each other. This module holds the core pieces of that model:

- :class:`FrameworkMeta` — the frozen ``framework`` slot the framework fills in
  at object creation time (timestamps, identity, provenance hints).
- :class:`ChannelInfo` — a small frozen descriptor for one acquisition channel,
  used by plugin ``Meta`` classes (e.g. ``FluorImage.Meta.channels``). It lives
  in core so several plugin packages can share it without importing one another.
- :func:`with_meta_changes` — a pure helper that returns a metadata model with
  some fields changed, backing ``DataObject.with_meta()``.

``DataObject`` itself is intentionally not exported here; it lives in
``scistudio.core.types``.
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
