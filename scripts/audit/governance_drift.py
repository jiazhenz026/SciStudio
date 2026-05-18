"""Detect concrete ADR-claimed governance values that drift from config."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from scieasy.qa.schemas.report import Finding, Severity  # noqa: E402
from scieasy.qa.tracker.adr_implementation_check import make_finding, resolve_repo_root  # noqa: E402


def check(repo_root: Path | None = None) -> list[Finding]:
    """Compare a small fact catalog against checked-in config."""
    root = resolve_repo_root(repo_root)
    findings: list[Finding] = []
    findings.extend(_check_coverage_threshold(root))
    # TODO(#1113): Expand governance fact catalog beyond coverage threshold. Out of scope per ADR-043 §2. Followup: #1113.
    return findings


def _check_coverage_threshold(root: Path) -> list[Finding]:
    adr_path = root / "docs/adr/ADR-042.md"
    pyproject_path = root / "pyproject.toml"
    if not adr_path.is_file() or not pyproject_path.is_file():
        return []

    adr_text = adr_path.read_text(encoding="utf-8")
    claims = [int(value) for value in re.findall(r"--cov-fail-under=(\d+)", adr_text)]
    if not claims:
        return []
    claimed = max(claims)

    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    addopts = pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("addopts", "")
    actual_match = re.search(r"--cov-fail-under=(\d+)", str(addopts))
    coverage_actual = pyproject.get("tool", {}).get("coverage", {}).get("report", {}).get("fail_under")
    actual_values = []
    if actual_match:
        actual_values.append(int(actual_match.group(1)))
    if coverage_actual is not None:
        actual_values.append(int(coverage_actual))

    if not actual_values:
        return [
            make_finding(
                "governance-drift.coverage-threshold-missing",
                "ADR-042 claims a coverage threshold, but pyproject.toml does not configure one.",
                file="pyproject.toml",
            )
        ]
    if any(value != claimed for value in actual_values):
        return [
            make_finding(
                "governance-drift.coverage-threshold-mismatch",
                f"ADR-042 claims --cov-fail-under={claimed}, but pyproject.toml has {actual_values}.",
                file="pyproject.toml",
            )
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)

    findings = check(args.repo_root)
    if findings:
        print("Governance drift check found issues:")
        for finding in findings:
            print(f"  [{finding.severity}] {finding.rule_id}: {finding.message}")
    else:
        print("Governance drift check passed.")
    return 1 if any(finding.severity == Severity.ERROR for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
