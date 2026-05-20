"""Guard governance-critical files against unauthorized changes."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

from scieasy.qa.governance.human_bypass_guard import VALID_OVERRIDE_LABELS
from scieasy.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

APPROVAL_ENV = "SCIEASY_GOVERNANCE_CHANGE_APPROVED"
BYPASS_ENV = "SCIEASY_GATE_BYPASS_LABELS"

PROTECTED_PATTERNS: tuple[str, ...] = (
    "AGENTS.md",
    ".workflow/**",
    ".github/workflows/**",
    ".pre-commit-config.yaml",
    "docs/adr/ADR-042.md",
    "docs/specs/adr-042-*.md",
    "src/scieasy/qa/governance/**",
    "src/scieasy/qa/audit/**",
    "src/scieasy/qa/schemas/**",
    "tests/qa/**",
)


def _run_git(repo_root: Path, args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True, stderr=subprocess.DEVNULL)


def _source_sha(repo_root: Path) -> str:
    try:
        return _run_git(repo_root, ["rev-parse", "HEAD"]).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _changed_files(repo_root: Path, *, base_ref: str, head_ref: str, staged: bool) -> list[str]:
    if staged:
        args = ["diff", "--cached", "--name-only", "--diff-filter=ACMRTUXB"]
    else:
        args = ["diff", "--name-only", "--diff-filter=ACMRTUXB", f"{base_ref}...{head_ref}"]
    output = _run_git(repo_root, args)
    return [line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()]


def _is_protected(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in PROTECTED_PATTERNS)


def _approval_present(*, allow_governance_change: bool) -> bool:
    return allow_governance_change or os.environ.get(APPROVAL_ENV) == "1"


def _local_bypass_findings() -> tuple[bool, list[Finding]]:
    labels = {label.strip() for label in os.environ.get(BYPASS_ENV, "").replace(",", " ").split() if label.strip()}
    invalid = sorted(
        label
        for label in labels
        if label not in VALID_OVERRIDE_LABELS and (label.startswith("human") or label.startswith("admin-approved"))
    )
    findings = [
        Finding(
            rule_id="governance.mod_guard.invalid-override-label",
            severity=Severity.ERROR,
            message="override label is not part of the ADR-042 vocabulary",
            evidence={"label": label, "valid_labels": sorted(VALID_OVERRIDE_LABELS)},
        )
        for label in invalid
    ]
    return bool(labels & VALID_OVERRIDE_LABELS), findings


def check(
    repo_root: Path,
    *,
    base_ref: str = "origin/main",
    head_ref: str = "HEAD",
    staged: bool = False,
    allow_governance_change: bool = False,
) -> AuditReport:
    """Fail when governance-critical files changed without explicit approval."""

    bypassed, bypass_findings = _local_bypass_findings()
    if bypass_findings:
        return AuditReport(
            tool="governance_mod_guard",
            status=AuditStatus.FAIL,
            source_sha=_source_sha(repo_root),
            findings=bypass_findings,
            summary={"bypassed": False, "mode": "staged" if staged else "ref"},
        )
    if bypassed:
        return AuditReport(
            tool="governance_mod_guard",
            status=AuditStatus.PASS,
            source_sha=_source_sha(repo_root),
            findings=[],
            summary={
                "bypassed": True,
                "bypass_env": BYPASS_ENV,
                "mode": "staged" if staged else "ref",
            },
        )

    protected = [
        path
        for path in _changed_files(repo_root, base_ref=base_ref, head_ref=head_ref, staged=staged)
        if _is_protected(path)
    ]
    approved = _approval_present(allow_governance_change=allow_governance_change)
    findings = []
    if protected and not approved:
        findings = [
            Finding(
                rule_id="governance.mod_guard.unauthorized-change",
                severity=Severity.ERROR,
                file=path,
                message=(
                    "governance-critical file changed without explicit approval; "
                    f"set {APPROVAL_ENV}=1 only after maintainer authorization"
                ),
            )
            for path in protected
        ]
    return AuditReport(
        tool="governance_mod_guard",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=_source_sha(repo_root),
        findings=findings,
        summary={
            "changed_protected_files": protected,
            "approved": approved,
            "mode": "staged" if staged else "ref",
        },
    )


def _render_text(report: AuditReport) -> str:
    if not report.findings:
        return "governance_mod_guard: pass"
    lines = ["governance_mod_guard: fail"]
    lines.extend(f"- {finding.file}: {finding.message}" for finding in report.findings)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--allow-governance-change", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = check(
        args.repo_root,
        base_ref=args.base,
        head_ref=args.head,
        staged=args.staged,
        allow_governance_change=args.allow_governance_change,
    )
    if args.format == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print(_render_text(report))
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    sys.exit(main())
