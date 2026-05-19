"""Protected core component change guard."""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
from collections.abc import Sequence
from pathlib import Path

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa._shared import AuditReport
from scieasy.qa.audit._cli import exit_code, print_report
from scieasy.qa.governance._auth import has_authorized_signal, review_authorized
from scieasy.qa.governance.local_gate import GateSession, PullRequestMetadata


def _protected(path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(path.replace("\\", "/"), pattern) for pattern in patterns)


def check_core_change(
    *,
    pr: PullRequestMetadata | None,
    changed_files: Sequence[str],
    session: GateSession | None,
    protected_globs: Sequence[str] = (
        "src/scieasy/core/**",
        "src/scieasy/engine/**",
        "src/scieasy/blocks/**",
        "src/scieasy/workflow/**",
        "src/scieasy/utils/**",
    ),
) -> AuditReport:
    findings = []
    authorized = bool(session and "admin-approved:core-change" in session.admin_labels)
    authorized = (
        authorized
        or has_authorized_signal(
            pr,
            operation="core-change",
            name="admin-approved:core-change",
            signal_type="label",
            admin_only=True,
        )
        or (pr is not None and review_authorized(pr.reviews, admin_only=True))
    )
    for path in changed_files:
        if _protected(path, protected_globs) and not authorized:
            findings.append(
                build_finding(
                    finding_id="core-change-guard-missing-admin-authorization",
                    tool="core_change_guard",
                    finding_class="core-change",
                    severity="error",
                    message=f"Protected core change requires administrator authorization: {path}",
                    path=path,
                )
            )
    return build_report(tool="core_change_guard", repo_root=Path.cwd(), findings=findings)


def check(
    *,
    pr: PullRequestMetadata | None = None,
    changed_files: Sequence[str],
    session: GateSession | None = None,
) -> AuditReport:
    return check_core_change(pr=pr, changed_files=changed_files, session=session)


def _changed(repo_root: Path, base: str, head: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", base, head],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return (
        [line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip()]
        if proc.returncode == 0
        else []
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check protected core changes.")
    parser.add_argument("--base", default="HEAD~1")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    report = check_core_change(pr=None, changed_files=_changed(Path.cwd(), args.base, args.head), session=None)
    print_report(report, as_json=args.format == "json")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
