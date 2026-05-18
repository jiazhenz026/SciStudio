"""Minimal ADR frontmatter primitives needed by ADR-043 section 2."""

from __future__ import annotations

from enum import StrEnum

from ._common import ADRRef, FunctionOrClassPath, RepoRelativePath


class Phase(StrEnum):
    """Canonical machine-readable cascade phase values from ADR-042 section 5."""

    PLANNING = "planning"
    PHASE_0 = "phase-0"
    PHASE_1 = "phase-1"
    PHASE_1_5 = "phase-1-5"
    PHASE_2 = "phase-2"
    PHASE_3 = "phase-3"
    PHASE_4 = "phase-4"
    PHASE_5 = "phase-5"
    COMPLETE = "complete"


__all__ = ["ADRRef", "FunctionOrClassPath", "Phase", "RepoRelativePath"]
