"""Validate the ADR-042/043 implementation tracker against repo state."""

from __future__ import annotations

import argparse
import importlib
import shlex
import subprocess
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from scieasy.qa.schemas.report import AuditReport, Finding, Severity, ToolRun
from scieasy.qa.schemas.tracker import ImplementationTracker, SectionStatus, TrackerEntry

TRACKER_PATH = Path("docs/audit/adr-042-implementation-tracker.yaml")
TOOL_VERSION = "0.2"
STATUS_ORDER = {
    SectionStatus.NOT_STARTED: 0,
    SectionStatus.IN_PROGRESS: 1,
    SectionStatus.IMPLEMENTED: 2,
    SectionStatus.VERIFIED: 3,
}


def resolve_repo_root(repo_root: Path | None = None) -> Path:
    """Resolve the repository root for CLI and test callers."""
    start = Path.cwd() if repo_root is None else Path(repo_root)
    start = start.resolve()
    candidates = [start, *start.parents]
    for candidate in candidates:
        if (candidate / "pyproject.toml").is_file() and (candidate / "docs").is_dir():
            return candidate
    return start


def make_finding(
    rule_id: str,
    message: str,
    *,
    file: str | Path,
    severity: Severity = Severity.ERROR,
    symbol: str | None = None,
    suggested_fix: str | None = None,
) -> Finding:
    """Build a common :class:`Finding` without repeating defaults."""
    return Finding(
        rule_id=rule_id,
        severity=severity,
        file=str(file).replace("\\", "/"),
        symbol=symbol,
        message=message,
        suggested_fix=suggested_fix,
    )


def build_report(tool: str, findings: list[Finding], repo_root: Path, started_at: datetime) -> AuditReport:
    """Package findings into the ADR-042 AuditReport envelope."""
    completed_at = datetime.now(UTC)
    has_errors = any(finding.severity == Severity.ERROR for finding in findings)
    has_warnings = any(finding.severity == Severity.WARNING for finding in findings)
    exit_status = "errors" if has_errors else "warnings" if has_warnings else "ok"
    severity_counts = Counter(finding.severity for finding in findings)
    drift_counts = Counter(finding.drift_class for finding in findings if finding.drift_class is not None)

    return AuditReport(
        run_id=f"{tool}-{uuid.uuid4()}",
        repo_sha=_git_value(repo_root, "rev-parse", "HEAD"),
        repo_branch=_git_value(repo_root, "branch", "--show-current"),
        generated_at=completed_at,
        runs=[
            ToolRun(
                tool=tool,
                version=TOOL_VERSION,
                config_hash="local",
                started_at=started_at,
                completed_at=completed_at,
                exit_status=exit_status,
                findings=findings,
            )
        ],
        total_findings=len(findings),
        by_severity={severity: count for severity, count in severity_counts.items() if count},
        by_drift_class={drift_class: count for drift_class, count in drift_counts.items() if count},
        bidirectional_closure_ok=not has_errors,
        translation_ok=True,
    )


def load_tracker(repo_root: Path, tracker_path: Path = TRACKER_PATH) -> tuple[ImplementationTracker | None, list[Finding]]:
    """Load and pydantic-validate the implementation tracker file."""
    path = repo_root / tracker_path
    if not path.is_file():
        return None, [
            make_finding(
                "implementation-tracker.missing",
                f"Implementation tracker is missing at {tracker_path}",
                file=tracker_path,
                suggested_fix="Create docs/audit/adr-042-implementation-tracker.yaml.",
            )
        ]

    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return None, [
            make_finding(
                "implementation-tracker.invalid-yaml",
                f"Tracker YAML could not be parsed: {exc}",
                file=tracker_path,
            )
        ]

    try:
        tracker = ImplementationTracker.model_validate(raw)
    except ValidationError as exc:
        return None, [
            make_finding(
                "implementation-tracker.schema-invalid",
                f"Tracker YAML failed schema validation: {exc}",
                file=tracker_path,
            )
        ]
    return tracker, []


def run(repo_root: Path | None = None, *, pr_aware: bool = False) -> AuditReport:
    """Validate the implementation tracker (ADR-043 section 2.1) against actual repo state."""
    started_at = datetime.now(UTC)
    root = resolve_repo_root(repo_root)
    tracker, findings = load_tracker(root)
    if tracker is not None:
        findings.extend(_check_monotonic_status(root, tracker))
        for entry in tracker.sections:
            findings.extend(_check_entry(root, entry))

    if pr_aware:
        findings.extend(_check_local_pr_diff(root, tracker))

    return build_report("adr_implementation_check", findings, root, started_at)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for tracker validation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--pr-aware", action="store_true")
    parser.add_argument("--section", default=None, help="Display findings for sections containing this text.")
    parser.add_argument("--json", action="store_true", help="Emit the structured AuditReport JSON.")
    args = parser.parse_args(argv)

    report = run(args.repo_root, pr_aware=args.pr_aware)
    findings = report.runs[0].findings
    if args.section:
        findings = [finding for finding in findings if args.section in finding.message or args.section in finding.file]

    if args.json:
        print(report.model_dump_json(indent=2))
    elif findings:
        print("ADR implementation tracker check found issues:")
        for finding in findings:
            print(f"  [{finding.severity}] {finding.rule_id}: {finding.message}")
    else:
        print("ADR implementation tracker check passed.")

    return 1 if any(finding.severity == Severity.ERROR for finding in findings) else 0


def _check_entry(repo_root: Path, entry: TrackerEntry) -> list[Finding]:
    findings: list[Finding] = []
    if entry.status == SectionStatus.IN_PROGRESS and not _changed_required_artifacts(repo_root, entry):
        findings.append(
            make_finding(
                "implementation-tracker.in-progress-no-artifact-change",
                f"{entry.section} is in_progress but no declared artifact is changed locally.",
                file=TRACKER_PATH,
            )
        )

    if entry.status not in {SectionStatus.IMPLEMENTED, SectionStatus.VERIFIED}:
        return findings

    for relative_path in [*entry.requires_artifacts.files, *entry.requires_artifacts.tests]:
        if not (repo_root / relative_path).is_file():
            findings.append(
                make_finding(
                    "implementation-tracker.artifact-missing",
                    f"{entry.section} is marked {entry.status} but required artifact is missing: {relative_path}",
                    file=relative_path,
                )
            )

    for symbol in entry.requires_artifacts.symbols:
        findings.extend(_check_symbol(entry, symbol))

    if entry.status == SectionStatus.VERIFIED:
        if entry.verified_at is None:
            findings.append(
                make_finding(
                    "implementation-tracker.verified-at-missing",
                    f"{entry.section} is verified but verified_at is not set.",
                    file=TRACKER_PATH,
                )
            )
        if not entry.verification_checks:
            findings.append(
                make_finding(
                    "implementation-tracker.verification-checks-missing",
                    f"{entry.section} is verified but declares no verification checks.",
                    file=TRACKER_PATH,
                )
            )
        findings.extend(_run_verifier_command(repo_root, entry))

    return findings


def _check_symbol(entry: TrackerEntry, symbol: str) -> list[Finding]:
    module_name, _, attr_path = symbol.rpartition(".")
    if not module_name or not attr_path:
        return [
            make_finding(
                "implementation-tracker.symbol-invalid",
                f"{entry.section} declares an invalid dotted symbol: {symbol}",
                file=TRACKER_PATH,
                symbol=symbol,
            )
        ]

    try:
        obj: Any = importlib.import_module(module_name)
        for attr in attr_path.split("."):
            obj = getattr(obj, attr)
    except Exception as exc:
        return [
            make_finding(
                "implementation-tracker.symbol-missing",
                f"{entry.section} is marked {entry.status} but symbol is not importable: {symbol} ({exc})",
                file=TRACKER_PATH,
                symbol=symbol,
            )
        ]
    return []


def _check_monotonic_status(repo_root: Path, tracker: ImplementationTracker) -> list[Finding]:
    previous = _load_tracker_from_git(repo_root, "HEAD", TRACKER_PATH)
    if previous is None:
        return []

    findings: list[Finding] = []
    prior_by_section = {entry.section: entry.status for entry in previous.sections}
    for entry in tracker.sections:
        prior_status = prior_by_section.get(entry.section)
        if prior_status is not None and STATUS_ORDER[entry.status] < STATUS_ORDER[prior_status]:
            findings.append(
                make_finding(
                    "implementation-tracker.status-regressed",
                    f"{entry.section} regressed from {prior_status} to {entry.status}.",
                    file=TRACKER_PATH,
                )
            )
    return findings


def _load_tracker_from_git(repo_root: Path, ref: str, tracker_path: Path) -> ImplementationTracker | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{tracker_path.as_posix()}"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return ImplementationTracker.model_validate(yaml.safe_load(result.stdout))
    except (ValidationError, yaml.YAMLError):
        return None


def _changed_required_artifacts(repo_root: Path, entry: TrackerEntry) -> set[str]:
    changed = _changed_files(repo_root)
    required = {str(path).replace("\\", "/") for path in [*entry.requires_artifacts.files, *entry.requires_artifacts.tests]}
    return changed & required


def _changed_files(repo_root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    names = {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    names.update(line.strip().replace("\\", "/") for line in untracked.stdout.splitlines() if line.strip())
    return names


def _check_local_pr_diff(repo_root: Path, tracker: ImplementationTracker | None) -> list[Finding]:
    if tracker is None:
        return []
    changed = _changed_files(repo_root)
    if not changed or TRACKER_PATH.as_posix() in changed:
        return []

    findings: list[Finding] = []
    for entry in tracker.sections:
        touched = _changed_required_artifacts(repo_root, entry)
        if touched:
            findings.append(
                make_finding(
                    "implementation-tracker.artifact-change-without-tracker-update",
                    f"{entry.section} declares changed artifact(s) {sorted(touched)} but the tracker file was not changed.",
                    file=TRACKER_PATH,
                )
            )
    # TODO(#1113): Validate remote GitHub PR openness/merge state for implemented_in_pr. Out of scope per ADR-043 §2. Followup: #1113.
    return findings


def _run_verifier_command(repo_root: Path, entry: TrackerEntry) -> list[Finding]:
    try:
        argv = shlex.split(entry.verifier_command)
    except ValueError as exc:
        return [
            make_finding(
                "implementation-tracker.verifier-command-invalid",
                f"{entry.section} verifier_command cannot be parsed: {exc}",
                file=TRACKER_PATH,
            )
        ]
    if not argv:
        return [
            make_finding(
                "implementation-tracker.verifier-command-empty",
                f"{entry.section} verifier_command is empty.",
                file=TRACKER_PATH,
            )
        ]

    result = subprocess.run(argv, cwd=repo_root, check=False, capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        return []
    output = (result.stdout + result.stderr).strip()
    if len(output) > 800:
        output = output[:800] + "..."
    return [
        make_finding(
            "implementation-tracker.verifier-command-failed",
            f"{entry.section} verifier_command failed with exit code {result.returncode}: {output}",
            file=TRACKER_PATH,
        )
    ]


def _git_value(repo_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return "unknown"
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
