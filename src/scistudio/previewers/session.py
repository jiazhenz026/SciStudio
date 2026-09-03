"""Deprecated alias for :mod:`scistudio.panels.session` (ADR-054 spec 1, FR-038).

Core-internal machinery that resolved under ``scistudio.previewers`` before the
rename. It carries no author stability promise, but it imported, and a path that
silently stops importing is the break the alias package exists to prevent
(FR-020).

It contains no logic of its own — only imports and aliases. Removed under the
condition stated in the ADR-048 addendum (FR-044).
"""

from __future__ import annotations

from scistudio.panels.session import (
    PreviewSessionManager as PreviewSessionManager,
)

__all__ = ["PreviewSessionManager"]
