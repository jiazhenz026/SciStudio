"""Small helper utilities used by ADR-042 documentation QA tools."""

from __future__ import annotations

import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scieasy.qa.schemas.report import AuditFinding, AuditReport


def _load_report_models() -> tuple[type["AuditFinding"], type["AuditReport"]]:
    from importlib import import_module

    try:
        module = import_module("scieasy.qa.schemas.report")
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via fixture in tests
        raise RuntimeError(
            "Missing dependency: scieasy.qa.schemas.report. "
            "Documentation tools target this interface and require consistency schema branch to be merged."
        ) from exc
    return module.AuditFinding, module.AuditReport


def source_sha_from_repo(repo_root: Path) -> str:
    """Best-effort source hash from git, or ``"unknown"``."""

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "unknown"

    return result.stdout.strip()


def build_report(
    *,
    tool: str,
    repo_root: Path,
    findings: list[AuditFinding] | None = None,
    summary: dict[str, object] | None = None,
) -> AuditReport:
    """Build an :class:`AuditReport` with status inferred from findings."""

    findings = findings or []
    status = "passed"
    if findings:
        has_error = any(finding.severity == "error" for finding in findings)
        status = "failed" if has_error else "passed"
    _, AuditReport = _load_report_models()
    return AuditReport(
        tool=tool,
        status=status,
        generated_at=datetime.utcnow(),
        source_sha=source_sha_from_repo(repo_root),
        findings=findings,
        summary=summary or {"error_count": Counter(f.severity for f in findings)},
    )


def build_finding(
    *,
    finding_id: str,
    tool: str,
    finding_class: str,
    severity: str,
    message: str,
    path: Path | str | None = None,
    line: int | None = None,
    subject: str | None = None,
    expected: object | None = None,
    actual: object | None = None,
    remediation: str | None = None,
    evidence: dict[str, object] | None = None,
) -> AuditFinding:
    AuditFinding, _ = _load_report_models()
    return AuditFinding(
        id=finding_id,
        tool=tool,
        severity=severity,  # type: ignore[arg-type]
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
