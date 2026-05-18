"""Validate the ADR-042/043 implementation tracker against repo state."""

from __future__ import annotations

import argparse
import importlib
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
TOOL_VERSION = "0.1-skeleton"


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
                config_hash="skeleton",
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
    """Validate the implementation tracker (ADR-043 section 2.1) against repo state."""
    started_at = datetime.now(UTC)
    root = resolve_repo_root(repo_root)
    tracker, findings = load_tracker(root)
    if tracker is not None:
        # TODO(#1113): Compare tracker status against the base ref to enforce monotonic advancement.
        #   Out of scope per ADR-043 §2 skeleton; implementation agent owns git-history-aware checks.
        #   Followup: #1113.
        for entry in tracker.sections:
            findings.extend(_check_entry(root, entry))

    if pr_aware:
        # TODO(#1113): Implement open-PR artifact-touch and tracker-update synchronization checks.
        #   Out of scope per ADR-043 §2 skeleton; requires GitHub PR context.
        #   Followup: #1113.
        findings.append(
            make_finding(
                "implementation-tracker.pr-aware-deferred",
                "PR-aware tracker synchronization checks are not implemented in this skeleton.",
                file=TRACKER_PATH,
                severity=Severity.WARNING,
            )
        )

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
        # TODO(#1113): Execute and record verification_checks before accepting verified status.
        #   Out of scope per ADR-043 §2 skeleton; implementation agent owns command execution.
        #   Followup: #1113.
        findings.append(
            make_finding(
                "implementation-tracker.verification-execution-deferred",
                f"{entry.section} is verified, but verification command execution is not implemented yet.",
                file=TRACKER_PATH,
                severity=Severity.WARNING,
            )
        )

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
