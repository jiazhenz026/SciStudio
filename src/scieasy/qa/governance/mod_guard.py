"""Governance modification guard."""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
from collections.abc import Sequence
from pathlib import Path

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa.audit._cli import exit_code, print_report
from scieasy.qa.governance.local_gate import GateSession

GOVERNANCE_PATTERNS = (
    "AGENTS.md",
    "docs/adr/ADR-042.md",
    "docs/specs/adr-042-*.md",
    ".github/workflows/**",
    ".pre-commit-config.yaml",
    ".claude/**",
    ".codex/**",
    ".agents/**",
    ".gemini/**",
)


def _changed(repo_root: Path, base_ref: str, head_ref: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", base_ref, head_ref],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip()]


def _is_governance(path: str, patterns: Sequence[str] = GOVERNANCE_PATTERNS) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def check_governance_modification(
    *,
    base_ref: str,
    head_ref: str,
    repo_root: Path,
    session: GateSession | None = None,
):
    findings = []
    authorized = bool(session and "admin-approved:governance" in session.admin_labels)
    for path in _changed(repo_root, base_ref, head_ref):
        if _is_governance(path) and not authorized:
            findings.append(
                build_finding(
                    finding_id="governance-mod-guard-unauthorized",
                    tool="governance_mod_guard",
                    finding_class="governance-modification",
                    severity="error",
                    message=f"Governance file changed without admin-approved:governance: {path}",
                    path=path,
                )
            )
    return build_report(tool="governance_mod_guard", repo_root=repo_root, findings=findings)


def check(
    *,
    base_ref: str,
    head_ref: str,
    repo_root: Path,
    session: GateSession | None = None,
):
    return check_governance_modification(base_ref=base_ref, head_ref=head_ref, repo_root=repo_root, session=session)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check governance file modifications.")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    report = check_governance_modification(base_ref=args.base, head_ref=args.head, repo_root=Path.cwd())
    print_report(report, as_json=args.format == "json")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
