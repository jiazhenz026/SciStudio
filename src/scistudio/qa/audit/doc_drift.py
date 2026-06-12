"""Structured documentation/fact drift checks for ADR-042."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from scistudio.qa.audit.governed import GovernedDocument, display_path, governed_file_matches, load_governed_documents
from scistudio.qa.audit.planned_governance import planned_surface_findings
from scistudio.qa.schemas.facts import FactsRegistry
from scistudio.qa.schemas.frontmatter import ADRFrontmatter, GovernedSurfaces, SpecFrontmatter
from scistudio.qa.schemas.report import AuditReport, AuditStatus, DriftClass, Finding, Severity

SPEC_ALIGNED_ADR_PHASES = frozenset({"implementation", "complete", "maintenance"})


def _symbol_subjects(facts: FactsRegistry) -> set[str]:
    return {fact.subject for fact in facts.find(kind="symbol")}


def _module_exists(module: str, symbols: set[str]) -> bool:
    return module in symbols or any(subject.startswith(f"{module}.") for subject in symbols)


def _contract_exists(contract: str, symbols: set[str]) -> bool:
    return contract in symbols


def _governs(document: ADRFrontmatter | SpecFrontmatter) -> GovernedSurfaces:
    return document.governs


def _active_governance(document: ADRFrontmatter | SpecFrontmatter) -> bool:
    if isinstance(document, SpecFrontmatter):
        return document.status in {"Planned", "Implemented"}
    return True


def _adr_requires_spec_alignment(adr: ADRFrontmatter) -> bool:
    return adr.phase in SPEC_ALIGNED_ADR_PHASES


def _module_or_contract_covers(owner_claim: str, covered_claim: str) -> bool:
    return covered_claim == owner_claim or covered_claim.startswith(f"{owner_claim}.")


def _file_claim_covers(owner_claim: str, covered_claim: str) -> bool:
    owner = owner_claim.replace("\\", "/")
    covered = covered_claim.replace("\\", "/")
    if owner == covered:
        return True
    if owner.endswith("/**"):
        return covered.startswith(owner[:-3].rstrip("/") + "/")
    return False


def _covered_by_any(claim: str, candidates: set[str], *, file_claim: bool = False) -> bool:
    covers = _file_claim_covers if file_claim else _module_or_contract_covers
    return any(covers(candidate, claim) or covers(claim, candidate) for candidate in candidates)


def _surface_values(governs: GovernedSurfaces, surface: str) -> list[str]:
    return list(getattr(governs, surface))


def _alignment_finding(
    *,
    rule_id: str,
    file: str,
    message: str,
    symbol: str | None = None,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=Severity.ERROR,
        file=file,
        message=message,
        symbol=symbol,
        drift_class=DriftClass.BEHAVIOR_DRIFT,
    )


def _check_adr_spec_alignment(
    governed_docs: Sequence[GovernedDocument],
    repo_root: Path,
) -> tuple[list[Finding], dict[str, int]]:
    adrs = {
        document.frontmatter.adr: document
        for document in governed_docs
        if isinstance(document.frontmatter, ADRFrontmatter)
    }
    active_specs = [
        document
        for document in governed_docs
        if isinstance(document.frontmatter, SpecFrontmatter) and _active_governance(document.frontmatter)
    ]
    specs_by_adr: dict[int, list[GovernedDocument]] = {}
    findings: list[Finding] = []

    for spec_doc in active_specs:
        spec = spec_doc.frontmatter
        if not isinstance(spec, SpecFrontmatter):
            continue
        spec_path = display_path(spec_doc.path, repo_root)
        for adr_number in spec.related_adrs:
            adr_doc = adrs.get(adr_number)
            if adr_doc is None:
                findings.append(
                    _alignment_finding(
                        rule_id="doc-drift.unlinked-spec",
                        file=spec_path,
                        message=f"active spec references missing ADR-{adr_number:03d}",
                    )
                )
                continue
            specs_by_adr.setdefault(adr_number, []).append(spec_doc)
            adr = adr_doc.frontmatter
            if not isinstance(adr, ADRFrontmatter):
                continue
            adr_path = display_path(adr_doc.path, repo_root)
            for surface in ("modules", "contracts", "entry_points", "files"):
                adr_values = set(_surface_values(adr.governs, surface))
                for claim in _surface_values(spec.governs, surface):
                    if not _covered_by_any(claim, adr_values, file_claim=surface == "files"):
                        findings.append(
                            _alignment_finding(
                                rule_id="doc-drift.missing-adr-governance",
                                file=spec_path,
                                message=(
                                    f"active spec governs {surface[:-1]} {claim}, "
                                    f"but related {Path(adr_path).name} does not cover it"
                                ),
                                symbol=claim if surface != "files" else None,
                            )
                        )

    for adr_number, adr_doc in adrs.items():
        adr = adr_doc.frontmatter
        if not isinstance(adr, ADRFrontmatter) or not _adr_requires_spec_alignment(adr):
            continue
        adr_path = display_path(adr_doc.path, repo_root)
        related_specs = specs_by_adr.get(adr_number, [])
        if not related_specs:
            findings.append(
                _alignment_finding(
                    rule_id="doc-drift.adr-without-implementation-spec",
                    file=adr_path,
                    message=f"ADR-{adr_number:03d} is in phase={adr.phase} but has no active related spec",
                )
            )
            continue
        spec_surfaces = {
            surface: {
                claim for spec_doc in related_specs for claim in _surface_values(spec_doc.frontmatter.governs, surface)
            }
            for surface in ("modules", "contracts", "entry_points", "files")
        }
        for surface in ("modules", "contracts", "entry_points", "files"):
            for claim in _surface_values(adr.governs, surface):
                if not _covered_by_any(claim, spec_surfaces[surface], file_claim=surface == "files"):
                    findings.append(
                        _alignment_finding(
                            rule_id="doc-drift.missing-spec-governance",
                            file=adr_path,
                            message=(
                                f"ADR-{adr_number:03d} governs {surface[:-1]} {claim}, "
                                "but no active related spec covers it"
                            ),
                            symbol=claim if surface != "files" else None,
                        )
                    )

    return findings, {
        "active_specs_checked": len(active_specs),
        "adr_spec_links_checked": sum(len(v) for v in specs_by_adr.values()),
    }


def classify_repo(
    repo_root: Path,
    facts: FactsRegistry,
    *,
    docs: Sequence[Path] | None = None,
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
        doc_path = display_path(document.path, root)
        if _active_governance(document.frontmatter):
            governs = _governs(document.frontmatter)
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

        findings.extend(
            planned_surface_findings(
                document.frontmatter,
                doc_path=doc_path,
                rule_prefix="doc-drift",
                module_exists=lambda claim: _module_exists(claim, symbols),
                contract_exists=lambda claim: _contract_exists(claim, symbols),
                file_exists=lambda claim: bool(governed_file_matches(root, claim)),
            )
        )

    alignment_findings, alignment_summary = _check_adr_spec_alignment(governed_docs, root)
    findings.extend(alignment_findings)

    return AuditReport(
        tool="doc_drift",
        status=AuditStatus.FAIL if any(f.severity == Severity.ERROR for f in findings) else AuditStatus.PASS,
        source_sha=facts.source_sha,
        findings=findings,
        summary={
            "governed_docs_checked": len(governed_docs),
            "modules_checked": checked_modules,
            "contracts_checked": checked_contracts,
            "files_checked": checked_files,
            "adr_spec_alignment_findings": len(alignment_findings),
            **alignment_summary,
        },
    )
