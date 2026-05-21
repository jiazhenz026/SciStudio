"""Validate ADR-042 documentation landing evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from scistudio.qa.governance.paths import is_gate_record_path
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

IMPLEMENTATION_PREFIXES = (
    "src/",
    "tests/",
    "packages/",
    "frontend/",
    ".workflow/",
    ".github/workflows/",
    "scripts/hooks/",
)
GOVERNANCE_PREFIXES = ("docs/adr/", "docs/specs/", "docs/planning/", ".sentrux/")
DEFAULT_REQUIRED_CLASSES = ("docs", "changelog", "checklist")


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


def _requires_landing(changed_files: Sequence[str]) -> bool:
    for path in changed_files:
        if path == "CHANGELOG.md":
            continue
        # Gate-record evidence files live under .workflow/ but are per-PR
        # audit trail, not implementation work; they must not force a
        # docs/changelog/checklist landing requirement on records-only
        # changes (#1362).
        if is_gate_record_path(path):
            continue
        if path.startswith(IMPLEMENTATION_PREFIXES) or path.startswith(GOVERNANCE_PREFIXES):
            return True
    return False


def _evidence_for(docs_landing: Mapping[str, Any], class_name: str) -> Mapping[str, Any]:
    raw = docs_landing.get(class_name, {})
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, list | tuple):
        return {"paths": list(raw)}
    if isinstance(raw, str):
        if raw.strip().upper().startswith("N/A"):
            return {"not_applicable": True, "rationale": raw}
        return {"paths": [raw]}
    return {}


def _has_path_or_na(evidence: Mapping[str, Any]) -> bool:
    paths = evidence.get("paths") or evidence.get("updated") or evidence.get("files")
    if isinstance(paths, Sequence) and not isinstance(paths, str) and any(str(path).strip() for path in paths):
        return True
    rationale = str(evidence.get("rationale", "")).strip()
    return bool(evidence.get("not_applicable") and rationale)


def check(
    *,
    changed_files: Sequence[str | Path],
    docs_landing: Mapping[str, Any] | None = None,
    required_classes: Sequence[str] | None = None,
    repo_root: Path | None = None,
) -> AuditReport:
    """Hard-fail when required docs/changelog/checklist landing is missing."""

    normalized = _normalized(changed_files)
    landing = docs_landing or {}
    required = tuple(required_classes or DEFAULT_REQUIRED_CLASSES)
    findings: list[Finding] = []

    if _requires_landing(normalized):
        for class_name in required:
            evidence = _evidence_for(landing, class_name)
            if _has_path_or_na(evidence):
                continue
            findings.append(
                Finding(
                    rule_id=f"docs_landing.missing-{class_name}",
                    severity=Severity.ERROR,
                    message=(f"missing {class_name} landing evidence or explicit N/A rationale for governed change"),
                    evidence={"required_class": class_name, "changed_files": normalized},
                )
            )

    return AuditReport(
        tool="docs_landing",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=_source_sha(repo_root),
        findings=findings,
        summary={
            "changed_files": normalized,
            "required": list(required) if _requires_landing(normalized) else [],
            "landing_classes": sorted(landing),
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--docs-landing-json", default="{}")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = check(
        changed_files=args.changed_file,
        docs_landing=json.loads(args.docs_landing_json),
        repo_root=args.repo_root,
    )
    if args.format == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print("docs_landing: pass" if not report.findings else "docs_landing: fail")
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    sys.exit(main())
