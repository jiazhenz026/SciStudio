"""Require administrator approval for ADR-042 protected core changes."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from scistudio.qa.governance.human_bypass_guard import (
    ADMIN_PERMISSIONS,
    CORE_CHANGE_LABEL,
    label_has_authorized_provenance,
)
from scistudio.qa.governance.paths import is_gate_record_path
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

PROTECTED_GLOBS = (
    "src/scistudio/core/**",
    "src/scistudio/engine/**",
    "src/scistudio/blocks/**",
    "src/scistudio/workflow/**",
    "src/scistudio/utils/**",
    "src/scistudio/qa/governance/**",
    "src/scistudio/qa/audit/**",
    "src/scistudio/qa/schemas/**",
    ".github/workflows/**",
    ".workflow/**",
    ".pre-commit-config.yaml",
)


def _source_sha(repo_root: Path | None) -> str:
    if repo_root is None:
        return "unknown"
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _normalized(paths: Sequence[str | Path]) -> list[str]:
    return [str(path).replace("\\", "/") for path in paths]


def _labels(pr: Mapping[str, Any] | None) -> set[str]:
    raw_labels = (pr or {}).get("labels", [])
    if not isinstance(raw_labels, Sequence) or isinstance(raw_labels, str):
        return set()
    return {
        str(label.get("name") if isinstance(label, Mapping) else label)
        for label in raw_labels
        if isinstance(label, str | Mapping)
    }


def _has_admin_approval_review(pr: Mapping[str, Any] | None) -> bool:
    raw_reviews = (pr or {}).get("reviews", [])
    if not isinstance(raw_reviews, Sequence) or isinstance(raw_reviews, str):
        return False
    for review in raw_reviews:
        if not isinstance(review, Mapping):
            continue
        state = str(review.get("state", "")).upper()
        permission = str(review.get("permission", review.get("actor_permission", ""))).lower()
        if state == "APPROVED" and permission in ADMIN_PERMISSIONS:
            return True
    return False


def _is_protected(path: str, protected_globs: Sequence[str]) -> bool:
    # Gate-record evidence files under .workflow/records/** live under the
    # ``.workflow/**`` protected glob but are per-PR audit trail rows that
    # every AI-authored PR creates by design; they must not require admin
    # approval to land. See ``governance.paths`` for the shared exclusion
    # rule used across governance modules (#1362).
    if is_gate_record_path(path):
        return False
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in protected_globs)


def check(
    *,
    changed_files: Sequence[str | Path],
    pr: Mapping[str, Any] | None = None,
    session: Mapping[str, Any] | None = None,
    protected_globs: Sequence[str] = PROTECTED_GLOBS,
    repo_root: Path | None = None,
) -> AuditReport:
    """Hard-fail protected core/governance changes without admin approval."""

    normalized = _normalized(changed_files)
    protected = [path for path in normalized if _is_protected(path, protected_globs)]
    labels = _labels(pr)
    approved = bool(session and session.get("allow_core_change"))
    approved = approved or (
        CORE_CHANGE_LABEL in labels and label_has_authorized_provenance(pr or {}, CORE_CHANGE_LABEL)
    )
    approved = approved or _has_admin_approval_review(pr)

    findings = []
    if protected and not approved:
        findings = [
            Finding(
                rule_id="core_change_guard.missing-admin-approval",
                severity=Severity.ERROR,
                file=path,
                message=(
                    "protected core/governance change requires admin-approved:core-change or administrator approval"
                ),
            )
            for path in protected
        ]

    return AuditReport(
        tool="core_change_guard",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=_source_sha(repo_root),
        findings=findings,
        summary={"protected_files": protected, "approved": approved},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--pr-json", default="{}")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = check(changed_files=args.changed_file, pr=json.loads(args.pr_json), repo_root=args.repo_root)
    if args.format == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print("core_change_guard: pass" if not report.findings else "core_change_guard: fail")
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    sys.exit(main())
