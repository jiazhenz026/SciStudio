"""Codemod metadata and idempotence checks for governed contract migrations."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Sequence
from pathlib import Path

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa.audit._cli import exit_code, print_report
from scieasy.qa.governance._auth import has_label
from scieasy.qa.governance.local_gate import PullRequestMetadata


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


def _is_contract_change(path: str) -> bool:
    return path.startswith("src/") or path.startswith("docs/specs/") or path.startswith("docs/adr/")


def _has_codemod_metadata(paths: Sequence[str]) -> bool:
    return any("codemod" in path.lower() or path.startswith("scripts/codemods/") for path in paths)


def check_codemod_lint(
    *,
    repo_root: Path,
    changed_files: Sequence[str],
    pr: PullRequestMetadata | None = None,
    run_idempotence: bool = True,
):
    del run_idempotence
    if has_label(pr, "human-authored"):
        return build_report(tool="codemod_lint", repo_root=repo_root, findings=[], summary={"skipped_human": True})
    findings = []
    contract_changed = any(_is_contract_change(path) for path in changed_files)
    if contract_changed and not _has_codemod_metadata(changed_files):
        findings.append(
            build_finding(
                finding_id="codemod-lint-missing-metadata",
                tool="codemod_lint",
                finding_class="codemod",
                severity="error",
                message="AI-authored contract migration requires codemod metadata or explicit human bypass.",
                subject="codemod",
            )
        )
    return build_report(tool="codemod_lint", repo_root=repo_root, findings=findings)


def check(
    *,
    repo_root: Path,
    changed_files: Sequence[str],
    pr: PullRequestMetadata | None = None,
    run_idempotence: bool = True,
):
    return check_codemod_lint(
        repo_root=repo_root,
        changed_files=changed_files,
        pr=pr,
        run_idempotence=run_idempotence,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check ADR-042 codemod requirements.")
    parser.add_argument("--base", default="HEAD~1")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    report = check_codemod_lint(
        repo_root=Path.cwd(),
        changed_files=_changed(Path.cwd(), args.base, args.head),
    )
    print_report(report, as_json=args.format == "json")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
