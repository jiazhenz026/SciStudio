"""Pydantic schema package for the QA infrastructure (ADR-042 §5/§6/§7).

This package owns the structural shapes consumed by every Phase 1 audit
tool: ADR/spec frontmatter, MAINTAINERS ownership rows, and the shared
``AuditReport`` envelope. Later Phase 1 sub-waves add ``facts``,
``identity``, ``tracker``, ``governance``, ``test_quality``,
``classification``, and the workflow gate schemas.

The ``ADRFrontmatter.model_rebuild()`` call below resolves the forward
reference to ``AgentRuntime`` that the model_validator code paths
introduce — ``frontmatter`` is imported first and the
``agent_editable_allowlist: list[AgentRuntime]`` annotation needs
``maintainers`` to be importable for the type to fully resolve.
Manager-default per Phase 1 investigation SUMMARY TC-1A.1.
"""

from . import _common, frontmatter, maintainers, report
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
    "Finding",
    "FunctionOrClassPath",
    "GitHandle",
    "Governs",
    "IssueRef",
    "LocaleCode",
    "Maintainers",
    "MaintainersEntry",
    "PathGlob",
    "Phase",
    "RepoRelativePath",
    "Severity",
    "SpecFrontmatter",
    "Status",
    "ToolRun",
    "Translation",
    "_common",
    "frontmatter",
    "maintainers",
    "report",
]
