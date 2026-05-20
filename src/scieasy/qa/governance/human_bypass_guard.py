"""Validate ADR-042 human and administrator override label provenance."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from scieasy.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

HUMAN_AUTHORED_LABEL = "human-authored"
AI_OVERRIDE_LABEL = "admin-approved:ai-override"
CORE_CHANGE_LABEL = "admin-approved:core-change"
MERGE_LABEL = "admin-approved:merge"
VALID_OVERRIDE_LABELS = frozenset(
    {
        HUMAN_AUTHORED_LABEL,
        AI_OVERRIDE_LABEL,
        CORE_CHANGE_LABEL,
        MERGE_LABEL,
    }
)
ADMIN_PERMISSIONS = frozenset({"admin", "maintain", "owner"})


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
    labels: set[str] = set()
    for label in raw_labels if isinstance(raw_labels, Sequence) and not isinstance(raw_labels, str) else []:
        if isinstance(label, str):
            labels.add(label)
        elif isinstance(label, Mapping) and isinstance(label.get("name"), str):
            labels.add(str(label["name"]))
    return labels


def _permission_for(event: Mapping[str, Any], pr: Mapping[str, Any]) -> str:
    permission = event.get("permission") or event.get("actor_permission")
    if isinstance(permission, str):
        return permission.lower()
    permissions = pr.get("actor_permissions", {})
    actor = event.get("actor")
    if isinstance(permissions, Mapping) and isinstance(actor, str):
        return str(permissions.get(actor, "")).lower()
    return ""


def _label_events(pr: Mapping[str, Any], label: str) -> list[Mapping[str, Any]]:
    raw_events = pr.get("label_events", [])
    if not isinstance(raw_events, Sequence) or isinstance(raw_events, str):
        return []
    return [
        event
        for event in raw_events
        if isinstance(event, Mapping) and event.get("label") == label and event.get("action", "labeled") == "labeled"
    ]


def label_has_authorized_provenance(pr: Mapping[str, Any], label: str) -> bool:
    """Return true when an override label was applied by an authorized actor."""

    return any(_permission_for(event, pr) in ADMIN_PERMISSIONS for event in _label_events(pr, label))


def _invalid_override_labels(labels: set[str]) -> list[str]:
    return sorted(
        label
        for label in labels
        if label not in VALID_OVERRIDE_LABELS and (label.startswith("human") or label.startswith("admin-approved"))
    )


def _has_ai_evidence(pr: Mapping[str, Any]) -> bool:
    if bool(pr.get("has_ai_evidence")):
        return True
    body = str(pr.get("body", ""))
    if "Assisted-by:" in body or "Gate-Record:" in body:
        return True
    commits = pr.get("commits", [])
    if not isinstance(commits, Sequence) or isinstance(commits, str):
        return False
    for commit in commits:
        message = str(commit.get("message", "")) if isinstance(commit, Mapping) else str(commit)
        if "Assisted-by:" in message or "Gate-Record:" in message:
            return True
    return False


def check(
    *,
    pr: Mapping[str, Any],
    require_bypass: bool = False,
    repo_root: Path | None = None,
) -> AuditReport:
    """Validate human-authored and admin override labels."""

    labels = _labels(pr)
    findings: list[Finding] = []

    for label in _invalid_override_labels(labels):
        findings.append(
            Finding(
                rule_id="human_bypass_guard.invalid-override-label",
                severity=Severity.ERROR,
                message="override label is not part of the ADR-042 vocabulary",
                evidence={"label": label, "valid_labels": sorted(VALID_OVERRIDE_LABELS)},
            )
        )

    for label in sorted(labels & VALID_OVERRIDE_LABELS):
        if not label_has_authorized_provenance(pr, label):
            findings.append(
                Finding(
                    rule_id="human_bypass_guard.unauthorized-label",
                    severity=Severity.ERROR,
                    message="override label must be applied by an authorized maintainer",
                    evidence={"label": label},
                )
            )

    human_label = HUMAN_AUTHORED_LABEL in labels
    ai_override = AI_OVERRIDE_LABEL in labels
    ai_evidence = _has_ai_evidence(pr)
    if human_label and ai_evidence and not ai_override:
        findings.append(
            Finding(
                rule_id="human_bypass_guard.ai-evidence-needs-admin-override",
                severity=Severity.ERROR,
                message=(
                    "human-authored does not bypass AI gate evidence when "
                    "AI evidence is present; admin-approved:ai-override is required"
                ),
            )
        )
    if require_bypass and not (human_label or ai_override):
        findings.append(
            Finding(
                rule_id="human_bypass_guard.missing-bypass-label",
                severity=Severity.ERROR,
                message="requested human/AI bypass requires an authorized ADR-042 override label",
            )
        )

    bypass_status = "not_requested"
    if human_label and not findings and not ai_evidence:
        bypass_status = "skipped-human"
    elif ai_override and not findings:
        bypass_status = "admin-ai-override"

    return AuditReport(
        tool="human_bypass_guard",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=_source_sha(repo_root),
        findings=findings,
        summary={
            "labels": sorted(labels),
            "valid_override_labels": sorted(VALID_OVERRIDE_LABELS),
            "has_ai_evidence": ai_evidence,
            "bypass_status": bypass_status,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr-json", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--require-bypass", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = check(pr=json.loads(args.pr_json), require_bypass=args.require_bypass, repo_root=args.repo_root)
    if args.format == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print("human_bypass_guard: pass" if not report.findings else "human_bypass_guard: fail")
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    sys.exit(main())
