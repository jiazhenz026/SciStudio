"""Deprecated alias for :mod:`scistudio.panels.registry` (ADR-054 spec 1, FR-038).

Core-internal machinery that resolved under ``scistudio.previewers`` before the
rename. It carries no author stability promise, but it imported, and a path that
silently stops importing is the break the alias package exists to prevent
(FR-020).

``PREVIEWER_ENTRY_POINT_GROUP`` keeps both its name and its value here for the
same reason it keeps them in :mod:`scistudio.panels.registry`: an installed
package's metadata is frozen at install time, so the group name is a
compatibility surface in the way a file path is (FR-045).

It contains no logic of its own — only imports and aliases. Removed under the
condition stated in the ADR-048 addendum (FR-044).
"""

from __future__ import annotations

from scistudio.panels.registry import (
    COMPANION_ENTRY_POINT_GROUPS as COMPANION_ENTRY_POINT_GROUPS,
)
from scistudio.panels.registry import (
    PREVIEWER_ENTRY_POINT_GROUP as PREVIEWER_ENTRY_POINT_GROUP,
)
from scistudio.panels.registry import (
    PanelRegistry as PreviewerRegistry,
)

__all__ = ["COMPANION_ENTRY_POINT_GROUPS", "PREVIEWER_ENTRY_POINT_GROUP", "PreviewerRegistry"]
