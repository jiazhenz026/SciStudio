"""Shared schemas used by ADR-042 QA tooling."""

from __future__ import annotations

from .facts import Fact, FactConfidence, FactKind, FactsRegistry, FactStability
from .frontmatter import ADRFrontmatter, GovernedSurfaces, SpecFrontmatter, SpecScope, Translation
from .maintainers import MaintainerRule, Maintainers
from .report import AuditFinding, DriftClass, Finding, Severity
from .signatures import ExpectedCliCommand, ExpectedModelField, ExpectedSignature, ParameterSpec

__all__ = [
    "ADRFrontmatter",
    "AuditFinding",
    "DriftClass",
    "ExpectedCliCommand",
    "ExpectedModelField",
    "ExpectedSignature",
    "Fact",
    "FactConfidence",
    "FactKind",
    "FactStability",
    "FactsRegistry",
    "Finding",
    "GovernedSurfaces",
    "MaintainerRule",
    "Maintainers",
    "ParameterSpec",
    "Severity",
    "SpecFrontmatter",
    "SpecScope",
    "Translation",
]
