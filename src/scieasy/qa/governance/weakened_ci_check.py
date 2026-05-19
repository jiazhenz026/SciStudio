"""Detect weakened ADR-042 CI, hook, and threshold protections."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa.audit._cli import exit_code, print_report

REQUIRED_CI_TOKENS = (
    "ruff check",
    "ruff format",
    "mypy",
    "pyright",
    "pytest",
    "lint-imports",
    "sphinx-build",
    "frontmatter-lint",
    "doc-length-lint",
    "auto-generated-lint",
    "skill-pointer-sync",
    "code-score",
    "pip-audit",
    "bandit",
    "actionlint",
    "zizmor",
)

REQUIRED_PRECOMMIT_TOKENS = (
    "ruff",
    "mypy",
    "codespell",
    "yamllint",
    "pyproject-fmt",
    "actionlint",
    "markdownlint-cli2",
    "adr042-code-score",
)


def _show(repo_root: Path, ref: str, path: str) -> str:
    proc = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout if proc.returncode == 0 else ""


def _read_head(repo_root: Path, head_ref: str, path: str) -> str:
    if head_ref == "WORKTREE":
        target = repo_root / path
        return target.read_text(encoding="utf-8") if target.exists() else ""
    return _show(repo_root, head_ref, path)


def _thresholds(text: str) -> list[int]:
    values = []
    for pattern in [r"cov-fail-under[= ](\d+)", r"fail_under\s*=\s*(\d+)", r"fail-under\s*=\s*(\d+)"]:
        values.extend(int(match.group(1)) for match in re.finditer(pattern, text))
    return values


def _token_removed(base: str, head: str, token: str) -> bool:
    return token in base and token not in head


def verify_no_weakening(
    *,
    repo_root: Path,
    base_ref: str,
    head_ref: str,
):
    repo_root = repo_root.resolve()
    findings = []
    files = {
        ".github/workflows/ci.yml": REQUIRED_CI_TOKENS,
        ".pre-commit-config.yaml": REQUIRED_PRECOMMIT_TOKENS,
        "pyproject.toml": ("cov-fail-under", "fail_under", "disallow_untyped_defs"),
    }
    for path, tokens in files.items():
        base = _show(repo_root, base_ref, path)
        head = _read_head(repo_root, head_ref, path)
        if base and not head:
            findings.append(
                build_finding(
                    finding_id="weakened-ci-file-removed",
                    tool="weakened_ci_check",
                    finding_class="governance-weakening",
                    severity="error",
                    message=f"Governance file removed: {path}",
                    path=path,
                )
            )
            continue
        for token in tokens:
            if _token_removed(base, head, token):
                findings.append(
                    build_finding(
                        finding_id="weakened-ci-token-removed",
                        tool="weakened_ci_check",
                        finding_class="governance-weakening",
                        severity="error",
                        message=f"Required check or setting removed: {token}",
                        path=path,
                        subject=token,
                    )
                )
        base_thresholds = _thresholds(base)
        head_thresholds = _thresholds(head)
        for index, base_value in enumerate(base_thresholds):
            if index < len(head_thresholds) and head_thresholds[index] < base_value:
                findings.append(
                    build_finding(
                        finding_id="weakened-ci-threshold-lowered",
                        tool="weakened_ci_check",
                        finding_class="governance-weakening",
                        severity="error",
                        message=f"Quality threshold lowered in {path}",
                        path=path,
                        expected=base_value,
                        actual=head_thresholds[index],
                    )
                )
    return build_report(tool="weakened_ci_check", repo_root=repo_root, findings=findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect ADR-042 CI and quality-rule weakening.")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    try:
        report = verify_no_weakening(repo_root=Path.cwd(), base_ref=args.base, head_ref=args.head)
    except Exception as exc:
        print(f"weakened_ci_check: {exc}", file=sys.stderr)
        return 2
    print_report(report, as_json=args.format == "json")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
