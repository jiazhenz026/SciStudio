"""Deprecated alias for :mod:`scistudio.panels.project` (ADR-054 spec 1, FR-038).

Core-internal machinery that resolved under ``scistudio.previewers`` before the
rename. It carries no author stability promise, but it imported, and a path that
silently stops importing is the break the alias package exists to prevent
(FR-020).

``PROJECT_PREVIEWERS_DIR`` is still ``"previewers"`` — the drop-in directory was
deliberately not renamed, because it is a path in people's projects rather than
an identifier. ``PROJECT_PREVIEWERS_MANIFEST`` is the retired name for the
manifest constant, and it answers the manifest this build reads first
(``.scistudio/panels.json``); the pre-rename ``.scistudio/previewers.json`` is
still read as a fallback and is exported here under the name the panels module
gives it.

It contains no logic of its own — only imports and aliases. Removed under the
condition stated in the ADR-048 addendum (FR-044).
"""

from __future__ import annotations

from scistudio.panels.project import (
    LEGACY_PROJECT_PANELS_MANIFEST as LEGACY_PROJECT_PANELS_MANIFEST,
)
from scistudio.panels.project import (
    PROJECT_PANELS_DIR as PROJECT_PREVIEWERS_DIR,
)
from scistudio.panels.project import (
    PROJECT_PANELS_MANIFEST as PROJECT_PREVIEWERS_MANIFEST,
)
from scistudio.panels.project import (
    load_project_panels as load_project_previewers,
)
from scistudio.panels.project import (
    load_user_panels as load_user_previewers,
)

__all__ = [
    "PROJECT_PREVIEWERS_DIR",
    "PROJECT_PREVIEWERS_MANIFEST",
    "load_project_previewers",
    "load_user_previewers",
]
