"""Deferred approved AI committer path enforcement."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

from scieasy.qa._report_helpers import build_finding
from scieasy.qa._shared import AuditReport, git_sha, now_utc


def check_committer_enforce(
    *,
    repo_root: Path,
    rev_range: str,
    approved_committers: Sequence[str],
) -> AuditReport:
    if not approved_committers:
        return AuditReport(
            tool="committer_enforce",
            status="skipped",
            generated_at=now_utc(),
            source_sha=git_sha(repo_root),
            findings=[],
            summary={"deferred": True},
        )
    proc = subprocess.run(
        ["git", "log", "--format=%H%x00%ae", rev_range],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    findings = []
    for line in proc.stdout.splitlines():
        sha, _, email = line.partition("\0")
        if email and email not in approved_committers:
            findings.append(
                build_finding(
                    finding_id="committer-enforce-unapproved",
                    tool="committer_enforce",
                    finding_class="committer",
                    severity="error",
                    message=f"Commit {sha[:12]} has unapproved committer {email}",
                    subject=sha,
                )
            )
    return AuditReport(
        tool="committer_enforce",
        status="failed" if findings else "passed",
        generated_at=now_utc(),
        source_sha=git_sha(repo_root),
        findings=findings,
    )


def check(*, repo_root: Path, rev_range: str, approved_committers: Sequence[str]) -> AuditReport:
    return check_committer_enforce(
        repo_root=repo_root,
        rev_range=rev_range,
        approved_committers=approved_committers,
    )
