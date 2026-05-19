"""Structured documentation/fact drift checks for ADR-042."""

from __future__ import annotations

from pathlib import Path

from scieasy.qa.audit.governed import display_path, governed_file_matches, load_governed_documents
from scieasy.qa.schemas.facts import FactsRegistry
from scieasy.qa.schemas.frontmatter import ADRFrontmatter, GovernedSurfaces, SpecFrontmatter
from scieasy.qa.schemas.report import AuditReport, AuditStatus, DriftClass, Finding, Severity


def _symbol_subjects(facts: FactsRegistry) -> set[str]:
    return {fact.subject for fact in facts.find(kind="symbol")}


def _module_exists(module: str, symbols: set[str]) -> bool:
    return module in symbols or any(subject.startswith(f"{module}.") for subject in symbols)


def _contract_exists(contract: str, symbols: set[str]) -> bool:
    return contract in symbols


def _governs(document: ADRFrontmatter | SpecFrontmatter) -> GovernedSurfaces:
    return document.governs


def classify_repo(
    repo_root: Path,
    facts: FactsRegistry,
    *,
    docs: list[Path] | None = None,
) -> AuditReport:
    """Check structured ADR/spec governed claims against repository facts."""

    del docs
    root = repo_root.resolve()
    governed_docs, frontmatter_findings = load_governed_documents(root)
    symbols = _symbol_subjects(facts)
    findings: list[Finding] = []
    for finding in frontmatter_findings:
        finding_path = Path(finding.file)
        findings.append(
            finding.model_copy(
                update={
                    "rule_id": "doc-drift.invalid-frontmatter",
                    "file": display_path(finding_path, root),
                    "drift_class": DriftClass.PHANTOM_REFERENCE,
                }
            )
        )

    checked_modules = 0
    checked_contracts = 0
    checked_files = 0
    for document in governed_docs:
        governs = _governs(document.frontmatter)
        doc_path = display_path(document.path, root)
        for module in governs.modules:
            checked_modules += 1
            if not _module_exists(module, symbols):
                findings.append(
                    Finding(
                        rule_id="doc-drift.phantom-module",
                        severity=Severity.ERROR,
                        file=doc_path,
                        message=f"governed module does not resolve to generated symbol facts: {module}",
                        symbol=module,
                        drift_class=DriftClass.PHANTOM_REFERENCE,
                    )
                )
        for contract in governs.contracts:
            checked_contracts += 1
            if not _contract_exists(contract, symbols):
                findings.append(
                    Finding(
                        rule_id="doc-drift.phantom-contract",
                        severity=Severity.ERROR,
                        file=doc_path,
                        message=f"governed contract does not resolve to generated symbol facts: {contract}",
                        symbol=contract,
                        drift_class=DriftClass.PHANTOM_REFERENCE,
                    )
                )
        for pattern in governs.files:
            checked_files += 1
            if not governed_file_matches(root, pattern):
                findings.append(
                    Finding(
                        rule_id="doc-drift.phantom-file",
                        severity=Severity.ERROR,
                        file=doc_path,
                        message=f"governed file path or glob does not resolve: {pattern}",
                        drift_class=DriftClass.PHANTOM_REFERENCE,
                    )
                )

    return AuditReport(
        tool="doc_drift",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=facts.source_sha,
        findings=findings,
        summary={
            "governed_docs_checked": len(governed_docs),
            "modules_checked": checked_modules,
            "contracts_checked": checked_contracts,
            "files_checked": checked_files,
        },
    )
