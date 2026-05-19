"""Verify test-first ordering evidence for scoped changes."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from .._shared import AuditFinding, AuditReport, git_sha, now_utc, schema_dependency_note


def _changed_paths(
    repo_root: Path,
    *,
    base_ref: str | None = None,
    head_ref: str = "HEAD",
) -> list[str]:
    if base_ref is None:
        args = ["git", "diff", "--name-only", head_ref]
    else:
        args = ["git", "diff", "--name-only", base_ref, head_ref]
    proc = subprocess.run(args, cwd=str(repo_root), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip()]


def verify_ordering(
    repo_root: Path,
    *,
    base_ref: str | None = None,
    head_ref: str = "HEAD",
    required: bool = False,
) -> AuditReport:
    repo_root = repo_root.resolve()

    if not required:
        return AuditReport(
            tool="test_quality.test_first_check",
            status="passed",
            generated_at=now_utc(),
            source_sha=git_sha(repo_root),
            findings=[],
            summary={"required": False, "not_required": True, "schema_dependency": schema_dependency_note()},
        )

    changed = _changed_paths(repo_root, base_ref=base_ref, head_ref=head_ref)
    changed_files = [path for path in changed if path.endswith(".py")]
    changed_tests = [path for path in changed_files if "/tests/" in ("/" + path) or path.startswith("tests/")]
    changed_code = [
        path
        for path in changed_files
        if "/tests/" not in ("/" + path) and not path.startswith("tests/")
    ]

    if not changed_code:
        return AuditReport(
            tool="test_quality.test_first_check",
            status="passed",
            generated_at=now_utc(),
            source_sha=git_sha(repo_root),
            findings=[],
            summary={
                "required": True,
                "changed_code_count": len(changed_code),
                "changed_test_count": len(changed_tests),
                "not_required": False,
                "schema_dependency": schema_dependency_note(),
            },
        )

    if not changed_tests:
        finding = AuditFinding(
            id="test-quality:ordering:test-first-missing",
            tool="test_quality.test_first_check",
            severity="error",
            finding_class="test-first-missing",
            message="Code changes without test changes for required scope.",
            path=None,
            subject="ordering",
            remediation="Add/modify tests together with code changes.",
            evidence={
                "changed_code_count": len(changed_code),
                "changed_test_count": len(changed_tests),
                "changed_code_files": changed_code,
            },
        )
        return AuditReport(
            tool="test_quality.test_first_check",
            status="failed",
            generated_at=now_utc(),
            source_sha=git_sha(repo_root),
            findings=[finding],
            summary={
                "required": True,
                "changed_code_count": len(changed_code),
                "changed_test_count": len(changed_tests),
                "not_required": False,
                "schema_dependency": schema_dependency_note(),
            },
        )

    return AuditReport(
        tool="test_quality.test_first_check",
        status="passed",
        generated_at=now_utc(),
        source_sha=git_sha(repo_root),
        findings=[],
        summary={
            "required": True,
            "changed_code_count": len(changed_code),
            "changed_test_count": len(changed_tests),
            "not_required": False,
            "schema_dependency": schema_dependency_note(),
        },
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify ADR-042 test-first evidence.")
    parser.add_argument("--base", default=None)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--required", action="store_true")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    return parser.parse_args()


def _run_cli() -> int:
    args = _parse_args()
    report = verify_ordering(
        Path(".").resolve(),
        base_ref=args.base,
        head_ref=args.head,
        required=args.required,
    )
    if args.format == "json":
        print(report.model_dump_json(indent=2))
    else:
        print(f"status={report.status} required={args.required}")
    return 1 if report.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(_run_cli())
