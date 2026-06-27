"""Single source of truth for the SciStudio base version and release channel.

#1742: the base ``a.b.c`` and the release ``CHANNEL`` live here and only here.
The *build number* is supplied at runtime by :mod:`scistudio.version` from a
local persistent counter (``.build-counter.json``) or the
``SCISTUDIO_BUILD_NUMBER`` environment override, so this file does not change on
every build. ``scripts/version.py`` rewrites the remaining manifests
(``pyproject.toml``, ``desktop/package.json``, ``frontend/package.json``) from
the derived version, eliminating the historical drift between them.

Keep this module import-cheap and dependency-free: it is imported very early
(``scistudio/__init__.py`` derives ``__version__`` from it).
"""

from __future__ import annotations

#: Base semantic version ``a.b.c`` (no channel/build suffix).
BASE_VERSION = "0.3.0"

#: Release channel. One of ``"alpha"``, ``"beta"``, ``"stable"``.
CHANNEL = "alpha"

__all__ = ["BASE_VERSION", "CHANNEL"]
