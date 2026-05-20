"""Detect high-signal CI and pre-commit weakening diffs."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from scieasy.qa.governance.human_bypass_guard import VALID_OVERRIDE_LABELS
from scieasy.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

BYPASS_ENV = "SCIEASY_GATE_BYPASS_LABELS"
GOVERNED_PATTERNS: tuple[str, ...] = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".pre-commit-config.yaml",
    "pyproject.toml",
)

REQUIRED_REMOVAL_TOKENS: tuple[tuple[str, str], ...] = (
    ("ruff-check", "ruff check"),
    ("ruff-format", "ruff format --check"),
    ("mypy", "mypy"),
    ("architecture-tests", "pytest tests/architecture"),
    ("pytest", "pytest"),
    ("pytest-timeout", "--timeout=60"),
    ("shell-timeout", "timeout 600"),
    ("import-linter", "lint-imports"),
    ("frontend-tests", "npm test"),
    ("frontend-build", "npm run build"),
    ("detect-private-key", "detect-private-key"),
    ("check-merge-conflict", "check-merge-conflict"),
    ("check-yaml", "check-yaml"),
    ("check-json", "check-json"),
)

ADDED_WEAKENING_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "continue-on-error",
        re.compile(r"\bcontinue-on-error\s*:\s*true\b", re.IGNORECASE),
        "added continue-on-error: true to governed CI/pre-commit configuration",
    ),
    (
        "disabled-if",
        re.compile(r"\bif\s*:\s*(?:false|\${{\s*false\s*}})\b", re.IGNORECASE),
        "added an always-false conditional to governed CI/pre-commit configuration",
    ),
    (
        "no-verify",
        re.compile(r"\b(?:--no-verify|SKIP=)\b"),
        "added a local hook bypass mechanism to governed configuration",
    ),
    (
        "ignore-failures",
        re.compile(r"\b(?:\|\|\s*true|exit\s+0)\b"),
        "added a failure-suppression command to governed configuration",
    ),
)


@dataclass(frozen=True)
class DiffLine:
    path: str
    sign: str
    text: str


def _run_git(repo_root: Path, args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True, stderr=subprocess.DEVNULL)


def _source_sha(repo_root: Path) -> str:
    try:
        return _run_git(repo_root, ["rev-parse", "HEAD"]).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _is_governed(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in GOVERNED_PATTERNS)


def _diff(repo_root: Path, *, base_ref: str, head_ref: str, staged: bool) -> str:
    pathspecs = list(GOVERNED_PATTERNS)
    if staged:
        args = ["diff", "--cached", "--unified=0", "--", *pathspecs]
    else:
        args = ["diff", "--unified=0", f"{base_ref}...{head_ref}", "--", *pathspecs]
    return _run_git(repo_root, args)


def _parse_diff_lines(diff_text: str) -> list[DiffLine]:
    lines: list[DiffLine] = []
    current_path: str | None = None
    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            parts = raw_line.split()
            current_path = parts[3][2:] if len(parts) >= 4 and parts[3].startswith("b/") else None
            continue
        if current_path is None or not _is_governed(current_path):
            continue
        if raw_line.startswith(("+++", "---")):
            continue
        if raw_line.startswith("+"):
            lines.append(DiffLine(path=current_path, sign="+", text=raw_line[1:].strip()))
        elif raw_line.startswith("-"):
            lines.append(DiffLine(path=current_path, sign="-", text=raw_line[1:].strip()))
    return lines


def _removed_check_findings(lines: list[DiffLine]) -> list[Finding]:
    findings: list[Finding] = []
    for diff_line in lines:
        if diff_line.sign != "-":
            continue
        lowered = diff_line.text.lower()
        for rule_suffix, token in REQUIRED_REMOVAL_TOKENS:
            if token.lower() in lowered:
                findings.append(
                    Finding(
                        rule_id=f"weakened-ci.removed-{rule_suffix}",
                        severity=Severity.ERROR,
                        file=diff_line.path,
                        message=f"removed required CI/pre-commit check token: {token}",
                        git_evidence=f"-{diff_line.text}",
                    )
                )
    return findings


def _added_weakening_findings(lines: list[DiffLine]) -> list[Finding]:
    findings: list[Finding] = []
    for diff_line in lines:
        if diff_line.sign != "+":
            continue
        for rule_suffix, pattern, message in ADDED_WEAKENING_PATTERNS:
            if pattern.search(diff_line.text):
                findings.append(
                    Finding(
                        rule_id=f"weakened-ci.added-{rule_suffix}",
                        severity=Severity.ERROR,
                        file=diff_line.path,
                        message=message,
                        git_evidence=f"+{diff_line.text}",
                    )
                )
    return findings


def _local_bypass_findings() -> tuple[bool, list[Finding]]:
    labels = {label.strip() for label in os.environ.get(BYPASS_ENV, "").replace(",", " ").split() if label.strip()}
    invalid = sorted(
        label
        for label in labels
        if label not in VALID_OVERRIDE_LABELS and (label.startswith("human") or label.startswith("admin-approved"))
    )
    findings = [
        Finding(
            rule_id="weakened-ci.invalid-override-label",
            severity=Severity.ERROR,
            message="override label is not part of the ADR-042 vocabulary",
            evidence={"label": label, "valid_labels": sorted(VALID_OVERRIDE_LABELS)},
        )
        for label in invalid
    ]
    return bool(labels & VALID_OVERRIDE_LABELS), findings


def verify_no_weakening(
    repo_root: Path,
    *,
    base_ref: str = "origin/main",
    head_ref: str = "HEAD",
    staged: bool = False,
) -> AuditReport:
    """Fail when governed diffs remove or weaken repository checks."""

    bypassed, bypass_findings = _local_bypass_findings()
    if bypass_findings:
        return AuditReport(
            tool="weakened_ci_check",
            status=AuditStatus.FAIL,
            source_sha=_source_sha(repo_root),
            findings=bypass_findings,
            summary={"bypassed": False, "mode": "staged" if staged else "ref"},
        )
    if bypassed:
        return AuditReport(
            tool="weakened_ci_check",
            status=AuditStatus.PASS,
            source_sha=_source_sha(repo_root),
            findings=[],
            summary={
                "bypassed": True,
                "bypass_env": BYPASS_ENV,
                "mode": "staged" if staged else "ref",
            },
        )

    diff_lines = _parse_diff_lines(_diff(repo_root, base_ref=base_ref, head_ref=head_ref, staged=staged))
    findings = [*_removed_check_findings(diff_lines), *_added_weakening_findings(diff_lines)]
    return AuditReport(
        tool="weakened_ci_check",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=_source_sha(repo_root),
        findings=findings,
        summary={
            "diff_lines_checked": len(diff_lines),
            "mode": "staged" if staged else "ref",
            "governed_patterns": list(GOVERNED_PATTERNS),
        },
    )


def _render_text(report: AuditReport) -> str:
    if not report.findings:
        return "weakened_ci_check: pass"
    lines = ["weakened_ci_check: fail"]
    lines.extend(f"- {finding.file}: {finding.message}" for finding in report.findings)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = verify_no_weakening(args.repo_root, base_ref=args.base, head_ref=args.head, staged=args.staged)
    if args.format == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print(_render_text(report))
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    sys.exit(main())
