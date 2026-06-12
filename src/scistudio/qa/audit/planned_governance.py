"""Shared planned-governed-surface checks for ADR/spec audits."""

from __future__ import annotations

from collections.abc import Callable

from scistudio.qa.schemas.frontmatter import ADRFrontmatter, GovernedSurfaces, SpecFrontmatter
from scistudio.qa.schemas.report import DriftClass, Finding, Severity

_SURFACES = ("modules", "contracts", "files")
_LABELS = {
    "modules": "module",
    "contracts": "contract",
    "files": "file path or glob",
}


def pre_implementation_state(document: ADRFrontmatter | SpecFrontmatter) -> bool:
    """Return true when unresolved planned surfaces are allowed as informational."""

    if isinstance(document, SpecFrontmatter):
        return document.status in {"Draft", "Clarifying", "Planned"}
    return document.status == "Proposed" or document.phase == "planning"


def planned_governs(document: ADRFrontmatter | SpecFrontmatter) -> GovernedSurfaces:
    """Return future governed surfaces declared by a document."""

    return document.planned_governs


def planned_surface_findings(
    document: ADRFrontmatter | SpecFrontmatter,
    *,
    doc_path: str,
    rule_prefix: str,
    module_exists: Callable[[str], bool],
    contract_exists: Callable[[str], bool],
    file_exists: Callable[[str], bool],
) -> list[Finding]:
    """Classify planned surfaces without treating them as current governance."""

    exists_by_surface = {
        "modules": module_exists,
        "contracts": contract_exists,
        "files": file_exists,
    }
    planned = planned_governs(document)
    pre_implementation = pre_implementation_state(document)
    findings: list[Finding] = []
    for surface in _SURFACES:
        label = _LABELS[surface]
        for claim in getattr(planned, surface):
            resolved = exists_by_surface[surface](claim)
            allowed_unresolved = pre_implementation and not resolved
            findings.append(
                Finding(
                    rule_id=_planned_rule_id(
                        rule_prefix,
                        surface=label.split()[0],
                        resolved=resolved,
                        pre_implementation=pre_implementation,
                    ),
                    severity=Severity.INFO if allowed_unresolved else Severity.ERROR,
                    file=doc_path,
                    message=_planned_message(
                        label,
                        claim=claim,
                        resolved=resolved,
                        pre_implementation=pre_implementation,
                    ),
                    symbol=claim if surface != "files" else None,
                    drift_class=DriftClass.BEHAVIOR_DRIFT if resolved else DriftClass.PHANTOM_REFERENCE,
                )
            )
    return findings


def _planned_rule_id(rule_prefix: str, *, surface: str, resolved: bool, pre_implementation: bool) -> str:
    if resolved:
        return f"{rule_prefix}.planned-{surface}-is-resolved"
    if not pre_implementation:
        return f"{rule_prefix}.planned-{surface}-left-in-active-doc"
    return f"{rule_prefix}.planned-{surface}"


def _planned_message(label: str, *, claim: str, resolved: bool, pre_implementation: bool) -> str:
    if resolved:
        return f"planned governed {label} already resolves and must move to governs: {claim}"
    if not pre_implementation:
        return f"non-planning document still declares planned governed {label}: {claim}"
    return f"planned governed {label} does not resolve yet: {claim}"
