"""Pydantic schema package for the QA infrastructure (ADR-042 §5/§6/§7/§7.5/§25.3).

This package owns the structural shapes consumed by every Phase 1 audit
tool: ADR/spec frontmatter, MAINTAINERS ownership rows, the shared
``AuditReport`` envelope, the ``FactsRegistry`` manifest (Phase 1A-b,
ADR-042 §7.5), and the human ``IdentityRegistry`` (Phase 1A-b,
ADR-042 §25.3). Later Phase 1 sub-waves add ``tracker``, ``governance``,
``test_quality``, ``classification``, and the doc-set frontmatter
schemas. Workflow-v2 gate shapes live under
``scieasy.qa.workflow.gate`` (Phase 1A-b sibling subpackage,
ADR-042 §19.5).

The ``ADRFrontmatter.model_rebuild()`` call below resolves the forward
reference to ``AgentRuntime`` that the model_validator code paths
introduce — ``frontmatter`` is imported first and the
``agent_editable_allowlist: list[AgentRuntime]`` annotation needs
``maintainers`` to be importable for the type to fully resolve.
Manager-default per Phase 1 investigation SUMMARY TC-1A.1.
"""

from . import _common, facts, frontmatter, identity, maintainers, report
from ._common import (
    ADRRef,
    AssistedByLine,
    DottedModulePath,
    FunctionOrClassPath,
    GitHandle,
    IssueRef,
    LocaleCode,
    PathGlob,
    RepoRelativePath,
)
from .facts import (
    ADRFacts,
    FactsRegistry,
    MaintainersFacts,
    SkillFacts,
    ToolFacts,
    WorkflowFacts,
)
from .frontmatter import (
    ADRFrontmatter,
    AgentEditable,
    Amendment,
    AmendmentKind,
    Governs,
    Phase,
    SpecFrontmatter,
    Status,
    Translation,
)
from .identity import (
    HumanIdentity,
    HumanTier,
    IdentityRegistry,
    SigningKey,
)
from .maintainers import AgentRuntime, Maintainers, MaintainersEntry
from .report import (
    AuditReport,
    DriftClass,
    Finding,
    Severity,
    ToolRun,
)

# Force pydantic to resolve `AgentRuntime` forward refs that `ADRFrontmatter`
# references via `agent_editable_allowlist: list[AgentRuntime]`. With
# `from __future__ import annotations` in frontmatter.py, the annotation is
# a string at class-definition time; this call evaluates it now that both
# modules are loaded. Manager-default per SUMMARY TC-1A.1.
ADRFrontmatter.model_rebuild()
SpecFrontmatter.model_rebuild()

__all__ = [
    "ADRFacts",
    "ADRFrontmatter",
    "ADRRef",
    "AgentEditable",
    "AgentRuntime",
    "Amendment",
    "AmendmentKind",
    "AssistedByLine",
    "AuditReport",
    "DottedModulePath",
    "DriftClass",
    "FactsRegistry",
    "Finding",
    "FunctionOrClassPath",
    "GitHandle",
    "Governs",
    "HumanIdentity",
    "HumanTier",
    "IdentityRegistry",
    "IssueRef",
    "LocaleCode",
    "Maintainers",
    "MaintainersEntry",
    "MaintainersFacts",
    "PathGlob",
    "Phase",
    "RepoRelativePath",
    "Severity",
    "SigningKey",
    "SkillFacts",
    "SpecFrontmatter",
    "Status",
    "ToolFacts",
    "ToolRun",
    "Translation",
    "WorkflowFacts",
    "_common",
    "facts",
    "frontmatter",
    "identity",
    "maintainers",
    "report",
]
