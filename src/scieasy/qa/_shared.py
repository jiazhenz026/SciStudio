"""Shared shims for ADR-042 quality tooling.

The quality tools must emit the target `AuditReport` shape from
`scieasy.qa.schemas.report`. When that branch/module is not available locally,
we keep a minimal compatibility shim and record the dependency on the
consistency branch in generated report metadata.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from scieasy.qa.schemas.report import AuditFinding, AuditReport

CONSISTENCY_SCHEMAS_AVAILABLE = True


GradeAlias = Literal["A", "B", "C", "D", "F"]


def _grade_order() -> dict[GradeAlias, int]:
    return {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}


def better_grade(left: GradeAlias, right: GradeAlias) -> GradeAlias:
    """Return the worse (numerically larger) of two grades."""

    return left if _grade_order()[left] >= _grade_order()[right] else right


def as_finding(
    *,
    tool: str,
    severity: Literal["info", "warning", "error"],
    finding_class: str,
    message: str,
    path: str | None = None,
    line: int | None = None,
    subject: str | None = None,
) -> AuditFinding:
    return AuditFinding(
        id=f"{tool}:{finding_class}:{path or 'repo'}:{line or 0}",
        tool=tool,
        severity=severity,
        finding_class=finding_class,
        message=message,
        path=path,
        line=line,
        subject=subject,
    )


def git_sha(repo_root: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    sha = proc.stdout.strip()
    if proc.returncode == 0 and sha:
        return sha
    return "unknown"


def now_utc() -> datetime:
    return datetime.now(UTC)


def report_status(report: AuditReport) -> Literal["passed", "failed", "skipped", "error"]:
    if report.status in {"passed", "failed", "skipped", "error"}:
        return report.status
    return "error"


def schema_dependency_note() -> str:
    return "shared report schema is available"
