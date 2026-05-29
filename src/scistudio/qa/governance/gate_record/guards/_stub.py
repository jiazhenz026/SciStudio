"""Shared helper for the B2-pending guard-calculator stubs.

Each guard module under this package is currently a STUB that returns an empty
passing report so the evaluator runs end-to-end. B2 (#1509) replaces the stub
body with the real calculator while keeping the ``check(inputs)`` signature.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scistudio.qa.schemas.report import AuditReport, AuditStatus


def source_sha(repo_root: Path) -> str:
    """Best-effort HEAD sha for report provenance."""

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def empty_report(tool: str, repo_root: Path) -> AuditReport:
    """Return a passing, finding-free report for a not-yet-implemented guard."""

    return AuditReport(
        tool=tool,
        status=AuditStatus.PASS,
        source_sha=source_sha(repo_root),
        findings=[],
        summary={"stub": True, "followup": "#1509"},
    )
