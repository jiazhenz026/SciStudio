"""Governed-change artifact completion checks."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Sequence
from pathlib import Path

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa.audit._cli import exit_code, print_report
from scieasy.qa.governance._auth import has_label
from scieasy.qa.governance.local_gate import GateSession, PullRequestMetadata


def _changed(repo_root: Path, base: str, head: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", base, head],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return (
        [line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip()]
        if proc.returncode == 0
        else []
    )


def _has_prefix(paths: Sequence[str], *prefixes: str) -> bool:
    return any(path.startswith(prefix) for path in paths for prefix in prefixes)


def check_complete_artifacts(
    *,
    repo_root: Path,
    session: GateSession | None,
    pr: PullRequestMetadata | None = None,
    changed_files: Sequence[str] | None = None,
):
    repo_root = repo_root.resolve()
    changed = list(changed_files or [])
    findings = []
    human_bypass = has_label(pr, "human-authored")
    code_changed = _has_prefix(changed, "src/", "packages/")
    docs_changed = _has_prefix(changed, "docs/")
    tests_changed = _has_prefix(changed, "tests/")
    changelog_changed = "CHANGELOG.md" in changed
    checklist_changed = any("checklist" in Path(path).name.lower() for path in changed)
    if human_bypass:
        return build_report(
            tool="complete_artifacts",
            repo_root=repo_root,
            findings=[],
            summary={"skipped_human": True},
        )
    if code_changed and not tests_changed:
        findings.append(
            build_finding(
                finding_id="complete-artifacts-missing-tests",
                tool="complete_artifacts",
                finding_class="missing-artifact",
                severity="error",
                message="Code changes require tests or an explicit owner-approved rationale.",
                subject="tests",
            )
        )
    if (
        code_changed
        and not docs_changed
        and not (session and session.docs_landing and session.docs_landing.not_applicable_rationale)
    ):
        findings.append(
            build_finding(
                finding_id="complete-artifacts-missing-docs",
                tool="complete_artifacts",
                finding_class="missing-artifact",
                severity="error",
                message="Governed code changes require documentation landing or N/A rationale.",
                subject="docs",
            )
        )
    if (
        code_changed
        and not changelog_changed
        and not (session and session.docs_landing and session.docs_landing.not_applicable_rationale)
    ):
        findings.append(
            build_finding(
                finding_id="complete-artifacts-missing-changelog",
                tool="complete_artifacts",
                finding_class="missing-artifact",
                severity="error",
                message="Governed code changes require changelog landing or N/A rationale.",
                subject="CHANGELOG.md",
            )
        )
    if (docs_changed or code_changed) and not checklist_changed and session and session.task_kind == "manager":
        findings.append(
            build_finding(
                finding_id="complete-artifacts-missing-checklist",
                tool="complete_artifacts",
                finding_class="missing-artifact",
                severity="error",
                message="Manager task requires checklist update or explicit N/A rationale.",
                subject="checklist",
            )
        )
    return build_report(tool="complete_artifacts", repo_root=repo_root, findings=findings)


def check(
    *,
    repo_root: Path,
    session: GateSession | None,
    pr: PullRequestMetadata | None = None,
    changed_files: Sequence[str] | None = None,
):
    return check_complete_artifacts(repo_root=repo_root, session=session, pr=pr, changed_files=changed_files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check governed-change required artifacts.")
    parser.add_argument("--base", default="HEAD~1")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    report = check_complete_artifacts(
        repo_root=Path.cwd(),
        session=None,
        changed_files=_changed(Path.cwd(), args.base, args.head),
    )
    print_report(report, as_json=args.format == "json")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
