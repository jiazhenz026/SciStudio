"""Block AI merge automation unless ADR-042 merge approval is present."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from scistudio.qa.governance.human_bypass_guard import MERGE_LABEL, label_has_authorized_provenance
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

MERGE_INTENTS = frozenset({"merge", "squash", "rebase", "enable-auto-merge"})


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


def _labels(pr: Mapping[str, Any]) -> set[str]:
    raw_labels = pr.get("labels", [])
    if not isinstance(raw_labels, Sequence) or isinstance(raw_labels, str):
        return set()
    return {
        str(label.get("name") if isinstance(label, Mapping) else label)
        for label in raw_labels
        if isinstance(label, str | Mapping)
    }


def check(
    *,
    pr: Mapping[str, Any],
    intent: str,
    actor: Mapping[str, Any] | None = None,
    repo_root: Path | None = None,
) -> AuditReport:
    """Validate that merge automation has explicit administrator approval."""

    labels = _labels(pr)
    is_ai_actor = bool((actor or {}).get("is_ai", True))
    needs_approval = intent in MERGE_INTENTS and is_ai_actor
    approved = MERGE_LABEL in labels and label_has_authorized_provenance(pr, MERGE_LABEL)
    findings: list[Finding] = []

    if needs_approval and not approved:
        findings.append(
            Finding(
                rule_id="pr_merge_guard.missing-admin-merge-approval",
                severity=Severity.ERROR,
                message="AI merge automation requires admin-approved:merge provenance",
                evidence={"intent": intent, "labels": sorted(labels)},
            )
        )

    return AuditReport(
        tool="pr_merge_guard",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=_source_sha(repo_root),
        findings=findings,
        summary={"intent": intent, "needs_approval": needs_approval, "approved": approved},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr-json", required=True)
    parser.add_argument("--intent", choices=sorted(MERGE_INTENTS), default="merge")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = check(pr=json.loads(args.pr_json), intent=args.intent, repo_root=args.repo_root)
    if args.format == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print("pr_merge_guard: pass" if not report.findings else "pr_merge_guard: fail")
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    sys.exit(main())
