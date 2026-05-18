"""Run ADR-043 section 2 QA tools as a report-only aggregate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_PATH = Path("docs/audit/report-only/adr043-section2-report-only.json")
TEXT_LIMIT = 20_000


@dataclass(frozen=True)
class CommandSpec:
    """A report-only command and how it should be interpreted."""

    name: str
    command: list[str]
    hard_fail_later: str
    manual_note: str | None = None


@dataclass(frozen=True)
class CommandResult:
    """Machine-readable command result for the aggregate report."""

    name: str
    command: list[str]
    exit_code: int
    classification: str
    report_only: bool
    hard_fail_later: str
    stdout: str
    stderr: str
    manual_note: str | None = None


SECTION2_COMMANDS = (
    CommandSpec(
        name="adr_implementation_check",
        command=[sys.executable, "scripts/audit/adr_implementation_check.py", "--json"],
        hard_fail_later=(
            "TODO(#1113): Convert tracker schema/import/artifact errors to hard-fail during the owner final "
            "CI pass per ADR-043 section 2 and the checklist Hard-fail conversion plan."
        ),
    ),
    CommandSpec(
        name="tool_self_test_runner",
        command=[sys.executable, "scripts/audit/tool_self_test_runner.py", "all"],
        hard_fail_later=(
            "TODO(#1113): Convert missing/stale tool self-test artifacts to hard-fail after required "
            "docs/audit/tool-self-test artifacts exist per ADR-043 section 2.4."
        ),
    ),
    CommandSpec(
        name="governance_drift",
        command=[sys.executable, "scripts/audit/governance_drift.py"],
        hard_fail_later=(
            "TODO(#1113): Convert governance drift findings to hard-fail after known ADR/config mismatches "
            "are resolved or baselined per ADR-043 section 2.7."
        ),
    ),
    CommandSpec(
        name="addendum_propagate_help_probe",
        command=[sys.executable, "scripts/audit/addendum_propagate.py", "--help"],
        hard_fail_later=(
            "TODO(#1113): Wire addendum propagation as report-only or hard-fail only after the tracker "
            "update workflow is owner-approved per ADR-043 section 2.6."
        ),
        manual_note=(
            "Help-only probe: normal addendum_propagate execution writes tracker rows and is intentionally "
            "not run without an addendum target."
        ),
    ),
)


def run_command(spec: CommandSpec, repo_root: Path) -> CommandResult:
    """Run one command and classify non-zero exits as report-only findings."""
    result = subprocess.run(
        spec.command,
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    classification = "pass" if result.returncode == 0 else "finding"
    return CommandResult(
        name=spec.name,
        command=spec.command,
        exit_code=result.returncode,
        classification=classification,
        report_only=True,
        hard_fail_later=spec.hard_fail_later,
        stdout=_truncate(result.stdout),
        stderr=_truncate(result.stderr),
        manual_note=spec.manual_note,
    )


def build_report(repo_root: Path) -> dict[str, object]:
    """Build the aggregate report without enforcing findings as failures."""
    started_at = datetime.now(UTC)
    results = [run_command(spec, repo_root) for spec in SECTION2_COMMANDS]
    completed_at = datetime.now(UTC)
    classifications = [result.classification for result in results]
    return {
        "run_id": f"adr043-section2-report-only-{uuid.uuid4()}",
        "generated_at": completed_at.isoformat(),
        "started_at": started_at.isoformat(),
        "repo_root": str(repo_root),
        "repo_branch": _git_value(repo_root, "branch", "--show-current"),
        "repo_sha": _git_value(repo_root, "rev-parse", "HEAD"),
        "report_only": True,
        "classification": "finding" if "finding" in classifications else "pass",
        "hard_fail_later": (
            "TODO(#1113): This aggregate remains report-only until the owner final CI pass selects "
            "which ADR-043 section 2 checks become required CI gates."
        ),
        "commands": [asdict(result) for result in results],
    }


def write_report(report: dict[str, object], path: Path, repo_root: Path) -> Path:
    """Write a stable JSON report artifact."""
    output_path = path if path.is_absolute() else repo_root / path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    report = build_report(repo_root)
    output_path = write_report(report, args.output, repo_root)
    print(f"ADR-043 section 2 report-only artifact written to {output_path}")
    return 0


def _truncate(value: str) -> str:
    if len(value) <= TEXT_LIMIT:
        return value
    return value[:TEXT_LIMIT] + "\n...[truncated]"


def _git_value(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
