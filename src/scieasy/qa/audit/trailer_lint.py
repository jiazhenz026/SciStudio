"""Validate AI provenance trailers across commit ranges."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa.audit._cli import exit_code, print_report
from scieasy.qa.governance.local_gate import check_commit_msg


def _commits(repo_root: Path, rev_range: str) -> list[tuple[str, str]]:
    proc = subprocess.run(
        ["git", "log", "--format=%H%x00%B%x00END%x00", rev_range],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    parts = proc.stdout.split("\0END\0")
    commits: list[tuple[str, str]] = []
    for part in parts:
        if not part.strip():
            continue
        sha, _, body = part.partition("\0")
        commits.append((sha.strip(), body.strip()))
    return commits


def run_trailer_lint(
    *,
    repo_root: Path,
    rev_range: str,
    require_ai_trailers: bool,
):
    findings = []
    for sha, message in _commits(repo_root, rev_range):
        report = check_commit_msg(message, require_ai_trailers=require_ai_trailers)
        for finding in report.findings:
            findings.append(
                build_finding(
                    finding_id=f"trailer-lint-{sha[:12]}-{finding.id}",
                    tool="trailer_lint",
                    finding_class=finding.finding_class,
                    severity=finding.severity,
                    message=f"Commit {sha[:12]}: {finding.message}",
                    subject=sha,
                )
            )
    return build_report(tool="trailer_lint", repo_root=repo_root, findings=findings)


def run(*, repo_root: Path, rev_range: str, require_ai_trailers: bool = True):
    return run_trailer_lint(repo_root=repo_root, rev_range=rev_range, require_ai_trailers=require_ai_trailers)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check AI provenance commit trailers.")
    parser.add_argument("--range", dest="rev_range", required=True)
    parser.add_argument("--no-ai-trailers", action="store_true")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    report = run_trailer_lint(
        repo_root=Path.cwd(),
        rev_range=args.rev_range,
        require_ai_trailers=not args.no_ai_trailers,
    )
    print_report(report, as_json=args.format == "json")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
