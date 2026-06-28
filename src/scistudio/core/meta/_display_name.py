"""resolve_display_name — the single canonical user-facing-name resolver (#1812).

User-facing item names used to be computed by two divergent fallback chains: a
backend one for interactive panels (``interactive_item_label``) and a frontend
one for preview pills (``deriveDisplayName``). Each new origin (xlsx sheets, OME
``source_file``, …) needed a new special case in both places, and they could
disagree.

This module is the **single precedence authority** for that name. Both
consumers delegate here:

- ``scistudio.blocks.base.interactive.interactive_item_label`` calls it on the
  live ``DataObject`` to label an interactive panel row.
- ``scistudio.api.runtime`` calls it on the serialized wire ``metadata`` dict to
  stamp a resolved ``display_name`` onto each item descriptor; the frontend then
  reads that one field instead of re-deriving.

Living in ``scistudio.core.meta`` keeps the import direction clean: both
``blocks`` and ``api`` depend on ``core``, never the reverse. This is an
**internal** helper — it is deliberately not exported from
``scistudio.core.meta.__all__`` (it is framework presentation plumbing, not a
package-author-facing symbol per ADR-052 §3.10).

The resolver is **input-shape agnostic**: it reads its fields through a
duck-typed accessor, so the same function handles both a live ``DataObject``
(Pydantic ``meta``/``framework`` attributes) and the serialized wire ``metadata``
dict (nested ``meta``/``framework``/``user`` mappings). See
``scistudio.core.types.serialization`` for the wire shape.

Precedence (highest first):

1. ``user["display_name"]`` — an explicit presentation override declared once by
   the producing block (e.g. the xlsx loader composes ``"<file> — <sheet>"`` so
   same-file/different-sheet items do not collide). This is the canonical
   override channel a producer reaches for when the structural default is wrong.
2. ``name`` — an explicit object name, if the object carries one (defensive; no
   core ``DataObject`` declares ``name`` today, but a plugin type might).
3. ``meta.source_file`` — the originating filename from typed domain metadata,
   reduced to its basename (loaders for spectra, images, etc. populate this).
4. ``file_path`` — an :class:`~scistudio.core.types.artifact.Artifact`-style file
   path, reduced to its basename.
5. ``framework.source`` — the framework provenance origin, used only when it
   looks like a path (contains a separator); package-name provenance such as
   ``"scistudio-blocks-spectroscopy"`` is not a filename and is skipped.
6. the caller-supplied ``fallback`` (``"item_<index>"`` for an interactive row,
   ``""`` for a wire descriptor so the field is simply omitted when nothing
   resolves and the frontend keeps its own truncated-ref fallback).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _get(source: Any, key: str) -> Any:
    """Read ``key`` from either a Mapping (wire dict) or an attribute holder.

    The resolver runs over two input shapes: the serialized wire ``metadata``
    dict (``source["meta"]``) and a live ``DataObject`` (``source.meta``). A
    single duck-typed accessor lets one precedence definition serve both.
    """
    if source is None:
        return None
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)


def _basename(value: str) -> str:
    """Basename of a path string, tolerant of either separator.

    The value is a user-supplied path captured at load time, so it may use
    either ``/`` or ``\\`` regardless of the host OS.
    """
    return value.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def resolve_display_name(source: Any, *, fallback: str) -> str:
    """Resolve the canonical user-facing display name for one data item.

    ``source`` is either a live :class:`~scistudio.core.types.base.DataObject`
    or its serialized wire ``metadata`` mapping. See the module docstring for
    the precedence chain.

    Args:
        source: A ``DataObject`` instance, a wire ``metadata`` mapping, or
            ``None``.
        fallback: The value returned when no signal resolves. Interactive rows
            pass ``"item_<index>"``; wire descriptors pass ``""`` and omit the
            field when the result is empty.

    Returns:
        The resolved display name, or ``fallback`` if nothing matched.
    """
    # 1. Explicit presentation override (the canonical producer channel).
    display_name = _get(_get(source, "user"), "display_name")
    if isinstance(display_name, str) and display_name:
        return display_name

    # 2. Explicit object name (defensive; no core type declares one today).
    name = _get(source, "name")
    if isinstance(name, str) and name:
        return name

    # 3. Typed domain source filename → basename.
    meta = _get(source, "meta")
    source_file = _get(meta, "source_file")
    if not (isinstance(source_file, str) and source_file):
        # Wire dicts may also carry source_file at the metadata root.
        source_file = _get(source, "source_file")
    if isinstance(source_file, str) and source_file:
        base = _basename(source_file)
        if base:
            return base

    # 4. Artifact-style file path → basename. Live objects expose a ``Path``
    # (use its ``.name``); wire dicts expose a string (basename it).
    file_path = _get(meta, "file_path")
    if file_path is None:
        file_path = _get(source, "file_path")
    if file_path is not None:
        path_name = getattr(file_path, "name", None)
        if isinstance(path_name, str) and path_name:
            return path_name
        if isinstance(file_path, str) and file_path:
            base = _basename(file_path)
            if base:
                return base

    # 5. Framework provenance, only when it looks like a path (not a package
    # name such as "scistudio-blocks-spectroscopy").
    framework_source = _get(_get(source, "framework"), "source")
    if isinstance(framework_source, str) and ("/" in framework_source or "\\" in framework_source):
        base = _basename(framework_source)
        if base:
            return base

    # 6. Caller-supplied fallback.
    return fallback
