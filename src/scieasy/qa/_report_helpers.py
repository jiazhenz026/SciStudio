"""Small helper utilities used by ADR-042 documentation QA tools."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from scieasy.qa._shared import AuditFinding, AuditReport, git_sha, now_utc


def source_sha_from_repo(repo_root: Path) -> str:
    """Best-effort source hash from git, or ``"unknown"``."""

    try:
        return git_sha(repo_root)
    except Exception:
        return "unknown"


def build_report(
    *,
    tool: str,
    repo_root: Path,
    findings: list[AuditFinding] | None = None,
    summary: dict[str, object] | None = None,
) -> AuditReport:
    """Build an :class:`AuditReport` with status inferred from findings."""

    findings = findings or []
    status: Literal["passed", "failed", "skipped", "error"] = "passed"
    if findings:
        has_error = any(finding.severity == "error" for finding in findings)
        status = "failed" if has_error else "passed"
    return AuditReport(
        tool=tool,
        status=status,
        generated_at=now_utc(),
        source_sha=source_sha_from_repo(repo_root),
        findings=findings,
        summary=summary or {"error_count": Counter(f.severity for f in findings)},
    )


def build_finding(
    *,
    finding_id: str,
    tool: str,
    finding_class: str,
    severity: Literal["info", "warning", "error"],
    message: str,
    path: Path | str | None = None,
    line: int | None = None,
    subject: str | None = None,
    expected: object | None = None,
    actual: object | None = None,
    remediation: str | None = None,
    evidence: dict[str, object] | None = None,
) -> AuditFinding:
    return AuditFinding(
        id=finding_id,
        tool=tool,
        severity=severity,
        finding_class=finding_class,
        message=message,
        path=str(path) if path is not None else None,
        line=line,
        subject=subject,
        expected=expected,
        actual=actual,
        remediation=remediation,
        evidence=evidence or {},
    )


def count_lines_and_words(lines: Iterable[str]) -> tuple[int, int]:
    """Count non-empty lines and prose words from Markdown-safe lines."""

    non_empty = 0
    words = 0
    in_code_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if stripped == "":
            continue
        if stripped.startswith("---"):
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            # tables are structural, not prose; avoid double-counting.
            continue
        if stripped.startswith("#"):
            continue
        non_empty += 1
        words += len(stripped.split())
    return non_empty, words
