"""Deprecated alias for :mod:`scistudio.panels.helpers` (ADR-054 spec 1, FR-038).

``scistudio.previewers.helpers`` was the canonical author root for
``sanitize_svg``. The subsystem is now :mod:`scistudio.panels`; this module
keeps the retired path resolving for unmigrated packages and on-disk drop-ins
(FR-045, FR-020, FR-042).

It contains no logic of its own — only imports and aliases. Removed under the
condition stated in the ADR-048 addendum (FR-044).
"""

from __future__ import annotations

from scistudio.panels.helpers import (
    sanitize_svg as sanitize_svg,
)

__all__ = ["sanitize_svg"]
