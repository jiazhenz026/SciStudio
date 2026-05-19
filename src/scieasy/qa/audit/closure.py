"""Bidirectional governed-surface closure checks for ADR-042."""

from __future__ import annotations

from pathlib import Path

from scieasy.qa.audit.governed import display_path, governed_file_matches, load_governed_documents
from scieasy.qa.schemas.facts import FactsRegistry
from scieasy.qa.schemas.frontmatter import ADRFrontmatter, GovernedSurfaces, SpecFrontmatter
from scieasy.qa.schemas.report import AuditReport, AuditStatus, DriftClass, Finding, Severity


def _governs(document: ADRFrontmatter | SpecFrontmatter) -> GovernedSurfaces:
    return document.governs


def _symbol_facts(facts: FactsRegistry) -> dict[str, str]:
    return {fact.subject: fact.source for fact in facts.find(kind="symbol")}


def _covered_by_governance(subject: str, modules: set[str], contracts: set[str]) -> bool:
    return subject in contracts or any(subject == module or subject.startswith(f"{module}.") for module in modules)


def _module_resolves(module: str, symbol_subjects: set[str]) -> bool:
    return module in symbol_subjects or any(subject.startswith(f"{module}.") for subject in symbol_subjects)


def check_bidirectional(
    repo_root: Path,
    facts: FactsRegistry,
    *,
    maintainers: object | None = None,
) -> AuditReport:
    """Verify governed claims resolve and public symbols have governance coverage."""

    del maintainers
    root = repo_root.resolve()
    governed_docs, frontmatter_findings = load_governed_documents(root)
    symbols = _symbol_facts(facts)
    symbol_subjects = set(symbols)
    modules: set[str] = set()
    contracts: set[str] = set()
    findings: list[Finding] = []

    for finding in frontmatter_findings:
        finding_path = Path(finding.file)
        findings.append(
            finding.model_copy(
                update={
                    "rule_id": "closure.invalid-frontmatter",
                    "file": display_path(finding_path, root),
                    "drift_class": DriftClass.PHANTOM_REFERENCE,
                }
            )
        )

    for document in governed_docs:
        governs = _governs(document.frontmatter)
        doc_path = display_path(document.path, root)
        modules.update(governs.modules)
        contracts.update(governs.contracts)
        for module in governs.modules:
            if not _module_resolves(module, symbol_subjects):
                findings.append(
                    Finding(
                        rule_id="closure.unresolved-module-claim",
                        severity=Severity.ERROR,
                        file=doc_path,
                        message=f"governed module claim does not resolve: {module}",
                        symbol=module,
                        drift_class=DriftClass.PHANTOM_REFERENCE,
                    )
                )
        for contract in governs.contracts:
            if contract not in symbol_subjects:
                findings.append(
                    Finding(
                        rule_id="closure.unresolved-contract-claim",
                        severity=Severity.ERROR,
                        file=doc_path,
                        message=f"governed contract claim does not resolve: {contract}",
                        symbol=contract,
                        drift_class=DriftClass.PHANTOM_REFERENCE,
                    )
                )
        for pattern in governs.files:
            if not governed_file_matches(root, pattern):
                findings.append(
                    Finding(
                        rule_id="closure.unresolved-file-claim",
                        severity=Severity.ERROR,
                        file=doc_path,
                        message=f"governed file claim does not resolve: {pattern}",
                        drift_class=DriftClass.PHANTOM_REFERENCE,
                    )
                )

    for subject in sorted(symbol_subjects):
        if _covered_by_governance(subject, modules, contracts):
            continue
        findings.append(
            Finding(
                rule_id="closure.missing-symbol-governance",
                severity=Severity.ERROR,
                file=symbols[subject],
                message=f"public symbol has no governing ADR/spec module or contract claim: {subject}",
                symbol=subject,
                drift_class=DriftClass.MISSING_DOCUMENTATION,
            )
        )

    return AuditReport(
        tool="closure",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=facts.source_sha,
        findings=findings,
        summary={
            "governed_docs_checked": len(governed_docs),
            "governed_modules": len(modules),
            "governed_contracts": len(contracts),
            "symbols_checked": len(symbol_subjects),
        },
    )
