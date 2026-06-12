"""Shared schemas used by ADR-042 QA tooling."""

from __future__ import annotations

from .change_contracts import (
    BaselinePolicyMode,
    ChangeContract,
    ChangeContractBaseline,
    ChangeContractBaselineFinding,
    ChangeContractBaselinePolicy,
    ChangeContractFrontmatterDeclaration,
    ChangeContractLink,
    ChangeContractNotApplicable,
    ChangeContractSurfaces,
    ChangeKind,
    ChangeSurface,
    ChangeSurfaceKind,
    ChangeSurfaceScope,
    ChangeWaiver,
    ForbiddenProdReference,
    ForbiddenReferenceKind,
    IssueReference,
    RequiredCanary,
    RequiredCanaryKind,
    RequiredReachability,
)
from .facts import Fact, FactConfidence, FactKind, FactsRegistry, FactStability
from .frontmatter import ADRFrontmatter, GovernedSurfaces, SpecFrontmatter, SpecScope, Translation
from .maintainers import MaintainerRule, Maintainers
from .report import AuditFinding, DriftClass, Finding, Severity
from .signatures import ExpectedCliCommand, ExpectedModelField, ExpectedSignature, ParameterSpec

__all__ = [
    "ADRFrontmatter",
    "AuditFinding",
    "BaselinePolicyMode",
    "ChangeContract",
    "ChangeContractBaseline",
    "ChangeContractBaselineFinding",
    "ChangeContractBaselinePolicy",
    "ChangeContractFrontmatterDeclaration",
    "ChangeContractLink",
    "ChangeContractNotApplicable",
    "ChangeContractSurfaces",
    "ChangeKind",
    "ChangeSurface",
    "ChangeSurfaceKind",
    "ChangeSurfaceScope",
    "ChangeWaiver",
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
    "ForbiddenProdReference",
    "ForbiddenReferenceKind",
    "GovernedSurfaces",
    "IssueReference",
    "MaintainerRule",
    "Maintainers",
    "ParameterSpec",
    "RequiredCanary",
    "RequiredCanaryKind",
    "RequiredReachability",
    "Severity",
    "SpecFrontmatter",
    "SpecScope",
    "Translation",
]
