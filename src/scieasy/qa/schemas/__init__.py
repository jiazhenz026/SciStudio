"""Shared schemas used by ADR-042 QA tooling."""

from __future__ import annotations

from .facts import Fact, FactConfidence, FactKind, FactsRegistry, FactStability
from .frontmatter import ADRFrontmatter, GovernedSurfaces, SpecFrontmatter, SpecScope, Translation
from .report import DriftClass, Finding, Severity

__all__ = [
    "ADRFrontmatter",
    "DriftClass",
    "Fact",
    "FactConfidence",
    "FactKind",
    "FactStability",
    "FactsRegistry",
    "Finding",
    "GovernedSurfaces",
    "Severity",
    "SpecFrontmatter",
    "SpecScope",
    "Translation",
]
