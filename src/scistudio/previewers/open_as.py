"""Deprecated alias for :mod:`scistudio.panels.open_as` (ADR-054 spec 1, FR-038).

Core-internal machinery that resolved under ``scistudio.previewers`` before the
rename. It carries no author stability promise, but it imported, and a path that
silently stops importing is the break the alias package exists to prevent
(FR-020). Every name and value in it survived the rename unchanged.

It contains no logic of its own — only imports and aliases. Removed under the
condition stated in the ADR-048 addendum (FR-044).
"""

from __future__ import annotations

from scistudio.panels.open_as import (
    OPEN_AS_FILENAME as OPEN_AS_FILENAME,
)
from scistudio.panels.open_as import (
    clear_open_as as clear_open_as,
)
from scistudio.panels.open_as import (
    normalize_extension as normalize_extension,
)
from scistudio.panels.open_as import (
    open_as_path as open_as_path,
)
from scistudio.panels.open_as import (
    read_open_as as read_open_as,
)
from scistudio.panels.open_as import (
    write_open_as as write_open_as,
)

__all__ = [
    "OPEN_AS_FILENAME",
    "clear_open_as",
    "normalize_extension",
    "open_as_path",
    "read_open_as",
    "write_open_as",
]
