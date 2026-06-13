"""Baseline-aware audit checks for ADR/spec change contracts."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from scistudio.qa.audit._util import git_tracked_relative_paths, normalise_path, source_sha
from scistudio.qa.audit.change_contract_reachability import ReachabilityRequirement, evaluate_reachability
from scistudio.qa.audit.governed import GovernedDocument, load_governed_documents
from scistudio.qa.schemas.change_contracts import (
    ChangeContract,
    ChangeContractBaseline,
    ChangeContractBaselineFinding,
    ChangeContractLink,
    ChangeContractNotApplicable,
    ChangeSurface,
    ChangeSurfaceKind,
    ChangeSurfaceScope,
)
from scistudio.qa.schemas.frontmatter import ADRFrontmatter, GovernedSurfaces, SpecFrontmatter
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

DEFAULT_BASELINE_PATH = Path("docs/audit/baselines/change-contract-baseline.json")
CONTRACT_TOOL = "change_contracts"
CHANGE_CONTRACT_RULE_PREFIX = "change-contract"
PRODUCTION_EXTENSIONS = frozenset({".py", ".ts", ".tsx", ".js", ".jsx", ".toml", ".json"})
IGNORED_SCAN_PARTS = frozenset(
    {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", ".workflow", "node_modules"}
)


def _git_changed_paths(repo_root: Path, *, base_ref: str | None, head_ref: str | None) -> set[str]:
    if not base_ref or not head_ref:
        return set()
    ranges = (f"{base_ref}...{head_ref}", f"{base_ref}..{head_ref}")
    for diff_range in ranges:
        try:
            completed = subprocess.run(
                ["git", "diff", "--name-only", diff_range],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except (OSError, subprocess.CalledProcessError):
            continue
        return {normalise_path(line.strip()) for line in completed.stdout.splitlines() if line.strip()}
    return set()


def _document_relative_path(repo_root: Path, document: GovernedDocument) -> str:
    return normalise_path(document.path.relative_to(repo_root))


def _has_surface_entries(surfaces: GovernedSurfaces) -> bool:
    return bool(surfaces.modules or surfaces.contracts or surfaces.entry_points or surfaces.files)


def _is_implementation_affecting(
    frontmatter: ADRFrontmatter | SpecFrontmatter,
) -> bool:
    if isinstance(frontmatter, ADRFrontmatter) and frontmatter.is_code_implementation:
        return True
    if _has_surface_entries(frontmatter.governs) or _has_surface_entries(frontmatter.planned_governs):
        return True
    return bool(getattr(frontmatter, "tests", []))


def _json_fingerprint(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stable_id(rule_id: str, parts: Sequence[str]) -> str:
    digest = _json_fingerprint({"rule_id": rule_id, "parts": list(parts)})[:16]
    return f"{rule_id}:{digest}"


def _finding(
    rule_id: str,
    *,
    file: str,
    message: str,
    subject: str | None = None,
    expected: Any | None = None,
    actual: Any | None = None,
    evidence: Mapping[str, Any] | None = None,
    severity: Severity = Severity.ERROR,
) -> Finding:
    evidence_payload = dict(evidence or {})
    finding_id = _stable_id(rule_id, [file, subject or "", str(expected or ""), str(actual or "")])
    fingerprint = _json_fingerprint(
        {
            "rule_id": rule_id,
            "file": file,
            "message": message,
            "subject": subject,
            "expected": expected,
            "actual": actual,
            "evidence": evidence_payload,
        }
    )
    evidence_payload["fingerprint"] = fingerprint
    return Finding(
        id=finding_id,
        tool=CONTRACT_TOOL,
        rule_id=rule_id,
        severity=severity,
        file=file,
        subject=subject,
        expected=expected,
        actual=actual,
        message=message,
        evidence=evidence_payload,
    )


def _finding_fingerprint(finding: Finding) -> str:
    value = finding.evidence.get("fingerprint")
    if isinstance(value, str):
        return value
    return _json_fingerprint(finding.model_dump(mode="json", exclude={"generated_at"}))


def _load_contract(
    repo_root: Path,
    document: GovernedDocument,
    declaration: ChangeContractLink,
) -> tuple[ChangeContract | None, str, list[Finding]]:
    document_path = _document_relative_path(repo_root, document)
    contract_path = repo_root / declaration.path
    if not contract_path.exists():
        return (
            None,
            declaration.path,
            [
                _finding(
                    "change-contract.contract-missing",
                    file=document_path,
                    message=f"declared change contract does not exist: {declaration.path}",
                    subject=declaration.path,
                )
            ],
        )
    try:
        loaded = yaml.safe_load(contract_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return (
            None,
            declaration.path,
            [
                _finding(
                    "change-contract.contract-unreadable",
                    file=declaration.path,
                    message=f"cannot read change contract: {exc}",
                    subject=declaration.path,
                )
            ],
        )
    try:
        contract = ChangeContract.model_validate(loaded)
    except ValidationError as exc:
        return (
            None,
            declaration.path,
            [
                _finding(
                    "change-contract.contract-invalid",
                    file=declaration.path,
                    message=f"change contract schema validation failed: {exc}",
                    subject=declaration.path,
                )
            ],
        )
    return contract, declaration.path, []


def _load_baseline(repo_root: Path, baseline_path: Path | None) -> tuple[ChangeContractBaseline | None, list[Finding]]:
    if baseline_path is None:
        return None, []
    path = baseline_path if baseline_path.is_absolute() else repo_root / baseline_path
    display_path = (
        normalise_path(path.relative_to(repo_root)) if path.is_relative_to(repo_root) else normalise_path(path)
    )
    if not path.exists():
        return (
            None,
            [
                _finding(
                    "change-contract.baseline-missing",
                    file=display_path,
                    message=f"change-contract baseline is missing: {display_path}",
                    subject=display_path,
                )
            ],
        )
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (
            None,
            [
                _finding(
                    "change-contract.baseline-unreadable",
                    file=display_path,
                    message=f"cannot read change-contract baseline: {exc}",
                    subject=display_path,
                )
            ],
        )
    try:
        baseline = ChangeContractBaseline.model_validate(loaded)
    except ValidationError as exc:
        return (
            None,
            [
                _finding(
                    "change-contract.baseline-invalid",
                    file=display_path,
                    message=f"change-contract baseline schema validation failed: {exc}",
                    subject=display_path,
                )
            ],
        )
    if baseline.expires is not None and baseline.expires < date.today():
        return (
            baseline,
            [
                _finding(
                    "change-contract.baseline-expired",
                    file=display_path,
                    message=f"change-contract baseline expired on {baseline.expires.isoformat()}",
                    subject=display_path,
                )
            ],
        )
    return baseline, []


def _all_governed_surfaces(frontmatter: ADRFrontmatter | SpecFrontmatter) -> GovernedSurfaces:
    return GovernedSurfaces(
        modules=[*frontmatter.governs.modules, *frontmatter.planned_governs.modules],
        contracts=[*frontmatter.governs.contracts, *frontmatter.planned_governs.contracts],
        entry_points=[*frontmatter.governs.entry_points, *frontmatter.planned_governs.entry_points],
        files=[*frontmatter.governs.files, *frontmatter.planned_governs.files],
        excludes=[*frontmatter.governs.excludes, *frontmatter.planned_governs.excludes],
    )


def _matches_path_or_glob(pattern: str, target: str) -> bool:
    normalized_pattern = normalise_path(pattern)
    normalized_target = normalise_path(target)
    if normalized_pattern == normalized_target:
        return True
    if normalized_pattern.endswith("/**") and normalized_target.startswith(normalized_pattern[:-3]):
        return True
    return fnmatch.fnmatch(normalized_target, normalized_pattern)


def _target_is_excluded(target: str, surfaces: GovernedSurfaces) -> bool:
    return any(_matches_path_or_glob(pattern, target) for pattern in surfaces.excludes)


def _dotted_prefix_matches(prefix: str, target: str) -> bool:
    return target == prefix or target.startswith(f"{prefix}.") or target.startswith(f"{prefix}:")


def _surface_is_covered(surface: ChangeSurface, governed: GovernedSurfaces) -> bool:
    target = normalise_path(surface.target)
    if _target_is_excluded(target, governed):
        return False
    if surface.kind == ChangeSurfaceKind.MODULE:
        return any(_dotted_prefix_matches(module, surface.target) for module in governed.modules)
    if surface.kind == ChangeSurfaceKind.SYMBOL:
        return any(_dotted_prefix_matches(contract, surface.target) for contract in governed.contracts) or any(
            _dotted_prefix_matches(module, surface.target) for module in governed.modules
        )
    if surface.kind == ChangeSurfaceKind.ENTRY_POINT:
        return target in governed.entry_points or any(
            _matches_path_or_glob(pattern, target) for pattern in governed.files
        )
    return any(_matches_path_or_glob(pattern, target) for pattern in governed.files) or any(
        _dotted_prefix_matches(contract, surface.target) for contract in governed.contracts
    )


def _contract_surfaces(contract: ChangeContract) -> Iterable[ChangeSurface]:
    yield from contract.surfaces.added
    yield from contract.surfaces.changed
    yield from contract.surfaces.removed
    yield from contract.surfaces.retained


def _check_contract_parent(
    repo_root: Path,
    document: GovernedDocument,
    contract: ChangeContract,
    contract_path: str,
) -> list[Finding]:
    document_path = _document_relative_path(repo_root, document)
    if normalise_path(contract.parent) == document_path:
        return []
    return [
        _finding(
            "change-contract.parent-mismatch",
            file=contract_path,
            message="change contract parent must match the ADR/spec that links it",
            subject=contract.id,
            expected=document_path,
            actual=contract.parent,
        )
    ]


def _check_surface_coverage(document: GovernedDocument, contract: ChangeContract, contract_path: str) -> list[Finding]:
    governed = _all_governed_surfaces(document.frontmatter)
    findings: list[Finding] = []
    for surface in _contract_surfaces(contract):
        if _surface_is_covered(surface, governed):
            continue
        findings.append(
            _finding(
                "change-contract.surface-outside-governance",
                file=contract_path,
                message=f"declared {surface.kind} surface is outside parent governs/planned_governs",
                subject=surface.target,
                evidence={"surface_kind": surface.kind, "surface_scope": surface.scope},
            )
        )
    return findings


def _scope_for_path(path: str) -> ChangeSurfaceScope:
    normalized = normalise_path(path)
    parts = set(Path(normalized).parts)
    basename = Path(normalized).name
    if normalized.startswith(".workflow/"):
        return ChangeSurfaceScope.GENERATED
    if normalized.startswith("docs/"):
        return ChangeSurfaceScope.DOCS
    if (
        normalized.startswith("tests/")
        or "tests" in parts
        or basename.startswith("test_")
        or basename.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    ):
        return ChangeSurfaceScope.TEST
    if "generated" in parts or normalized.startswith(("frontend/dist/", "build/", "dist/")):
        return ChangeSurfaceScope.GENERATED
    return ChangeSurfaceScope.PRODUCTION


def _iter_reference_scan_files(repo_root: Path) -> Iterable[Path]:
    tracked = git_tracked_relative_paths(repo_root)
    paths = (
        sorted(tracked)
        if tracked is not None
        else [normalise_path(path.relative_to(repo_root)) for path in repo_root.rglob("*")]
    )
    for relative in paths:
        path = repo_root / relative
        if not path.is_file():
            continue
        if any(part in IGNORED_SCAN_PARTS for part in Path(relative).parts):
            continue
        if path.suffix not in PRODUCTION_EXTENSIONS:
            continue
        yield path


def _reference_found(text: str, *, target: str, kind: str, suffix: str) -> bool:
    if kind == "import" and suffix == ".py":
        escaped = re.escape(target)
        pattern = re.compile(
            rf"^\s*(?:from\s+{escaped}(?:\s+import|\.|$)|import\s+{escaped}(?:\s|,|\.|$))",
            re.MULTILINE,
        )
        return pattern.search(text) is not None
    if kind == "import":
        import_line = re.compile(r"^\s*(?:import|export)\s+[^'\"]*['\"](?P<specifier>[^'\"]+)['\"]", re.MULTILINE)
        return any(target in match.group("specifier") for match in import_line.finditer(text))
    if kind == "pattern":
        try:
            return re.search(target, text, re.MULTILINE) is not None
        except re.error:
            return target in text
    return target in text


def _check_forbidden_prod_references(
    repo_root: Path,
    contract: ChangeContract,
    contract_path: str,
) -> list[Finding]:
    findings: list[Finding] = []
    references = contract.forbidden_prod_references
    if not references:
        return findings
    for path in _iter_reference_scan_files(repo_root):
        relative = normalise_path(path.relative_to(repo_root))
        scope = _scope_for_path(relative)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for reference in references:
            if ChangeSurfaceScope.ANY in reference.allowed_scopes or scope in reference.allowed_scopes:
                continue
            if not _reference_found(text, target=reference.target, kind=str(reference.kind), suffix=path.suffix):
                continue
            findings.append(
                _finding(
                    "change-contract.forbidden-prod-reference",
                    file=relative,
                    message=f"forbidden production reference remains: {reference.target}",
                    subject=reference.target,
                    evidence={
                        "contract": contract_path,
                        "reference_kind": reference.kind,
                        "scope": scope,
                    },
                )
            )
    return findings


def _reachable_target(surface: ChangeSurface) -> str:
    if surface.kind == ChangeSurfaceKind.SYMBOL:
        target = surface.target.split(":", 1)[0]
        return target.rsplit(".", 1)[0] if "." in target else target
    return surface.target


def _reachability_kind(surface: ChangeSurface) -> str | None:
    if surface.kind in {ChangeSurfaceKind.MODULE, ChangeSurfaceKind.SYMBOL}:
        return "python_module"
    if surface.kind == ChangeSurfaceKind.FRONTEND_COMPONENT:
        return "frontend_component"
    if surface.kind in {ChangeSurfaceKind.ENTRY_POINT, ChangeSurfaceKind.CLI, ChangeSurfaceKind.TOOL}:
        return "entry_point"
    if surface.kind in {ChangeSurfaceKind.FILE, ChangeSurfaceKind.GLOB, ChangeSurfaceKind.ROUTE}:
        target = normalise_path(surface.target)
        if target.startswith("frontend/"):
            return "frontend_component"
    return None


def _entry_point_parts(values: Sequence[str]) -> tuple[str | None, str | None]:
    if not values:
        return None, None
    first = values[0]
    for separator in (":", "/"):
        if separator in first:
            group, name = first.split(separator, 1)
            return group, name
    return None, first


def _reachability_requirements(contract: ChangeContract) -> list[ReachabilityRequirement]:
    requirements: list[ReachabilityRequirement] = []
    for declared in contract.required_reachability:
        kind = _reachability_kind(declared.surface)
        if kind is None:
            continue
        entry_point_group, entry_point_name = _entry_point_parts(declared.entry_points)
        requirements.append(
            ReachabilityRequirement(
                kind=kind,  # type: ignore[arg-type]
                target=_reachable_target(declared.surface),
                roots=tuple(declared.production_roots),
                entry_point_group=entry_point_group,
                entry_point_name=entry_point_name,
                entry_point_value=declared.registrations[0] if declared.registrations else None,
                canaries=tuple(declared.canaries),
            )
        )
    return requirements


def _check_reachability(repo_root: Path, contract: ChangeContract, contract_path: str) -> tuple[list[Finding], int]:
    requirements = _reachability_requirements(contract)
    if not requirements:
        return [], 0
    result = evaluate_reachability(repo_root, requirements)
    findings = [
        _finding(
            reachability_finding.rule_id,
            file=contract_path,
            message=reachability_finding.message,
            subject=reachability_finding.target,
            evidence=reachability_finding.evidence,
        )
        for reachability_finding in result.findings
    ]
    return findings, len(result.evidence)


def _canary_test_file(canary: str) -> str:
    return normalise_path(canary.split("::", 1)[0])


def _missing_canary_finding(
    *,
    repo_root: Path,
    contract_path: str,
    canary: str,
    evidence: Mapping[str, Any] | None = None,
) -> Finding | None:
    test_file = _canary_test_file(canary)
    if (repo_root / test_file).exists():
        return None
    return _finding(
        "change-contract.canary-missing",
        file=contract_path,
        message=f"required canary test path does not exist: {test_file}",
        subject=test_file,
        evidence=evidence,
    )


def _check_canaries(repo_root: Path, contract: ChangeContract, contract_path: str) -> list[Finding]:
    findings: list[Finding] = []
    for canary in contract.required_canaries:
        if canary.test_path is None:
            continue
        if finding := _missing_canary_finding(
            repo_root=repo_root,
            contract_path=contract_path,
            canary=canary.test_path,
            evidence={"source": "required_canaries", "surface": canary.surface.target},
        ):
            findings.append(finding)
    for declared in contract.required_reachability:
        findings.extend(
            finding
            for canary in declared.canaries
            if (
                finding := _missing_canary_finding(
                    repo_root=repo_root,
                    contract_path=contract_path,
                    canary=canary,
                    evidence={"source": "required_reachability", "surface": declared.surface.target},
                )
            )
        )
    return findings


def _check_expirations(contract: ChangeContract, contract_path: str) -> list[Finding]:
    findings: list[Finding] = []
    today = date.today()
    for surface in contract.surfaces.retained:
        if surface.expires is not None and surface.expires < today:
            findings.append(
                _finding(
                    "change-contract.retained-surface-expired",
                    file=contract_path,
                    message=f"retained surface expired on {surface.expires.isoformat()}",
                    subject=surface.target,
                )
            )
    for waiver in contract.waivers:
        if waiver.expires is not None and waiver.expires < today:
            findings.append(
                _finding(
                    "change-contract.waiver-expired",
                    file=contract_path,
                    message=f"waiver expired on {waiver.expires.isoformat()}",
                    subject=waiver.rule_id,
                )
            )
    return findings


def _contract_findings(
    repo_root: Path,
    document: GovernedDocument,
    contract: ChangeContract,
    contract_path: str,
) -> tuple[list[Finding], int]:
    reachability_findings, evidence_count = _check_reachability(repo_root, contract, contract_path)
    findings = [
        *_check_contract_parent(repo_root, document, contract, contract_path),
        *_check_surface_coverage(document, contract, contract_path),
        *_check_forbidden_prod_references(repo_root, contract, contract_path),
        *reachability_findings,
        *_check_canaries(repo_root, contract, contract_path),
        *_check_expirations(contract, contract_path),
    ]
    return findings, evidence_count


def _baseline_entry_by_id(
    baseline: ChangeContractBaseline | None,
) -> dict[str, ChangeContractBaselineFinding]:
    if baseline is None:
        return {}
    return {finding.id: finding for finding in baseline.findings}


def _is_touched_baseline_finding(
    finding: Finding,
    entry: ChangeContractBaselineFinding,
    changed_paths: set[str],
) -> bool:
    if not changed_paths:
        return False
    candidates = {finding.file}
    if entry.source is not None:
        candidates.add(normalise_path(entry.source))
    if entry.surface is not None:
        candidates.add(normalise_path(entry.surface.target))
    for candidate in candidates:
        if candidate in changed_paths:
            return True
        if any(
            _matches_path_or_glob(candidate, path) or _matches_path_or_glob(path, candidate) for path in changed_paths
        ):
            return True
    return False


def _apply_baseline(
    findings: list[Finding],
    *,
    baseline: ChangeContractBaseline | None,
    changed_paths: set[str],
) -> tuple[list[Finding], int]:
    baseline_by_id = _baseline_entry_by_id(baseline)
    reconciled: list[Finding] = []
    grandfathered = 0
    today = date.today()
    for finding in findings:
        if finding.severity != Severity.ERROR:
            reconciled.append(finding)
            continue
        entry = baseline_by_id.get(finding.id or "")
        fingerprint = _finding_fingerprint(finding)
        if entry is None or entry.fingerprint != fingerprint:
            reconciled.append(finding)
            continue
        if entry.expires is not None and entry.expires < today:
            reconciled.append(
                _finding(
                    "change-contract.baseline-finding-expired",
                    file=finding.file,
                    message=f"baseline finding expired on {entry.expires.isoformat()}: {finding.message}",
                    subject=finding.subject or finding.id,
                )
            )
            continue
        if _is_touched_baseline_finding(finding, entry, changed_paths) and not (
            entry.owner and entry.issue and entry.reason
        ):
            reconciled.append(
                _finding(
                    "change-contract.baseline-renewal-required",
                    file=finding.file,
                    message="touched baseline finding requires renewed owner, issue, and reason justification",
                    subject=finding.id,
                    evidence={"baseline_id": entry.id, "original_rule_id": entry.rule_id},
                )
            )
            continue
        grandfathered += 1
        evidence = dict(finding.evidence)
        evidence["baseline_id"] = entry.id
        reconciled.append(
            finding.model_copy(
                update={
                    "severity": Severity.INFO,
                    "message": f"{finding.message} (grandfathered by change-contract baseline)",
                    "evidence": evidence,
                }
            )
        )
    return reconciled, grandfathered


def _evaluate_documents(
    repo_root: Path,
    *,
    changed_paths: set[str],
) -> tuple[list[Finding], dict[str, int]]:
    findings: list[Finding] = []
    contracts_checked = 0
    contract_links = 0
    not_applicable = 0
    reachability_evidence = 0
    docs_checked = 0
    missing_contract_candidates = 0
    documents, load_findings = load_governed_documents(repo_root)
    findings.extend(load_findings)
    for document in documents:
        document_path = _document_relative_path(repo_root, document)
        docs_checked += 1
        declaration = document.frontmatter.change_contract
        implementation_affecting = _is_implementation_affecting(document.frontmatter)
        if declaration is None:
            if document_path in changed_paths and implementation_affecting:
                missing_contract_candidates += 1
                findings.append(
                    _finding(
                        "change-contract.missing-contract",
                        file=document_path,
                        message="implementation-affecting ADR/spec changes must declare a change_contract link or explicit docs-only N/A",
                        subject=document_path,
                    )
                )
            continue
        if isinstance(declaration, ChangeContractNotApplicable):
            not_applicable += 1
            if implementation_affecting:
                findings.append(
                    _finding(
                        "change-contract.invalid-not-applicable",
                        file=document_path,
                        message="implementation-affecting ADR/spec cannot use change_contract not_applicable",
                        subject=document_path,
                        evidence={"rationale": declaration.rationale},
                    )
                )
            continue
        contract_links += 1
        contract, contract_path, load_contract_findings = _load_contract(repo_root, document, declaration)
        findings.extend(load_contract_findings)
        if contract is None:
            continue
        contracts_checked += 1
        contract_findings, contract_reachability_evidence = _contract_findings(
            repo_root,
            document,
            contract,
            contract_path,
        )
        reachability_evidence += contract_reachability_evidence
        findings.extend(contract_findings)
    summary = {
        "documents_checked": docs_checked,
        "contract_links": contract_links,
        "contracts_checked": contracts_checked,
        "not_applicable_declarations": not_applicable,
        "missing_contract_candidates": missing_contract_candidates,
        "reachability_evidence": reachability_evidence,
    }
    return findings, summary


def _observed_change_paths(
    root: Path,
    *,
    base_ref: str | None,
    head_ref: str | None,
    changed_paths: Sequence[str] | None,
) -> set[str]:
    if changed_paths is not None:
        return {normalise_path(path) for path in changed_paths}
    return _git_changed_paths(root, base_ref=base_ref, head_ref=head_ref)


def _reconciled_contract_findings(
    root: Path,
    *,
    observed_changes: set[str],
    baseline_path: Path | None,
) -> tuple[list[Finding], dict[str, int], ChangeContractBaseline | None, int]:
    contract_findings, summary = _evaluate_documents(root, changed_paths=observed_changes)
    baseline, baseline_findings = _load_baseline(root, baseline_path)
    findings, grandfathered = _apply_baseline(contract_findings, baseline=baseline, changed_paths=observed_changes)
    findings.extend(baseline_findings)
    return findings, summary, baseline, grandfathered


def _summary_with_baseline(
    summary: Mapping[str, int],
    *,
    observed_changes: set[str],
    baseline_path: Path | None,
    baseline: ChangeContractBaseline | None,
    grandfathered: int,
) -> dict[str, int | str | None]:
    return {
        **summary,
        "changed_paths": len(observed_changes),
        "baseline_path": normalise_path(baseline_path) if baseline_path is not None else None,
        "baseline_findings": len(baseline.findings) if baseline is not None else 0,
        "grandfathered_findings": grandfathered,
    }


def _run_contract_report(
    root: Path,
    *,
    baseline_path: Path | None,
    base_ref: str | None,
    head_ref: str | None,
    changed_paths: Sequence[str] | None,
) -> AuditReport:
    observed_changes = _observed_change_paths(
        root,
        base_ref=base_ref,
        head_ref=head_ref,
        changed_paths=changed_paths,
    )
    findings, summary, baseline, grandfathered = _reconciled_contract_findings(
        root,
        observed_changes=observed_changes,
        baseline_path=baseline_path,
    )
    status = AuditStatus.FAIL if any(finding.severity == Severity.ERROR for finding in findings) else AuditStatus.PASS
    return AuditReport(
        tool=CONTRACT_TOOL,
        status=status,
        source_sha=source_sha(root),
        findings=findings,
        summary=_summary_with_baseline(
            summary,
            observed_changes=observed_changes,
            baseline_path=baseline_path,
            baseline=baseline,
            grandfathered=grandfathered,
        ),
    )


def check_report(
    repo_root: Path,
    *,
    baseline_path: Path | None = DEFAULT_BASELINE_PATH,
    base_ref: str | None = "origin/main",
    head_ref: str | None = "HEAD",
    changed_paths: Sequence[str] | None = None,
) -> AuditReport:
    """Run the change-contract audit and return a shared audit report."""

    return _run_contract_report(
        repo_root.resolve(),
        baseline_path=baseline_path,
        base_ref=base_ref,
        head_ref=head_ref,
        changed_paths=changed_paths,
    )


def _baseline_from_findings(findings: Sequence[Finding], *, source_sha: str) -> ChangeContractBaseline:
    return ChangeContractBaseline(
        generated_from=source_sha or "unknown",
        findings=[
            ChangeContractBaselineFinding(
                id=finding.id or finding.rule_id,
                rule_id=finding.rule_id,
                fingerprint=_finding_fingerprint(finding),
                source=finding.file or None,
                reason="Initial change-contract baseline entry.",
            )
            for finding in findings
            if finding.severity == Severity.ERROR and finding.rule_id.startswith(CHANGE_CONTRACT_RULE_PREFIX)
        ],
    )


def write_baseline(
    repo_root: Path,
    *,
    baseline_path: Path = DEFAULT_BASELINE_PATH,
    base_ref: str | None = "origin/main",
    head_ref: str | None = "HEAD",
    changed_paths: Sequence[str] | None = None,
) -> ChangeContractBaseline:
    """Write a baseline from the current raw change-contract findings."""

    root = repo_root.resolve()
    observed_changes = (
        {normalise_path(path) for path in changed_paths}
        if changed_paths is not None
        else _git_changed_paths(root, base_ref=base_ref, head_ref=head_ref)
    )
    findings, _summary = _evaluate_documents(root, changed_paths=observed_changes)
    baseline = _baseline_from_findings(findings, source_sha=source_sha(root))
    path = baseline_path if baseline_path.is_absolute() else root / baseline_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return baseline


def render_text(report: AuditReport) -> str:
    """Render a compact text summary for CLI use."""

    lines = [
        f"change_contracts: {report.status}",
        f"contracts_checked={report.summary.get('contracts_checked', 0)}",
        f"findings={len(report.findings)}",
    ]
    for finding in report.findings:
        location = finding.file or "<repo>"
        lines.append(f"- {finding.severity} {finding.rule_id} {location}: {finding.message}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ADR/spec change-contract checks")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.write_baseline:
            baseline = write_baseline(
                args.repo_root, baseline_path=args.baseline, base_ref=args.base, head_ref=args.head
            )
            text = json.dumps(baseline.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
            if args.output is not None:
                output = args.output if args.output.is_absolute() else args.repo_root / args.output
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(text, encoding="utf-8")
            else:
                print(text, end="")
            return 0
        report = check_report(args.repo_root, baseline_path=args.baseline, base_ref=args.base, head_ref=args.head)
        text = report.model_dump_json(indent=2) + "\n" if args.format == "json" else render_text(report)
        if args.output is not None:
            output = args.output if args.output.is_absolute() else args.repo_root / args.output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
    except Exception as exc:
        print(f"change_contracts failed: {exc}", file=sys.stderr)
        return 2
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    raise SystemExit(main())
