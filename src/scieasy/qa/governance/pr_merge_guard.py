"""Block AI-initiated PR merges without administrator authorization."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa.governance._auth import actor_authorized, has_authorized_signal, review_authorized
from scieasy.qa.governance.local_gate import ActorPermission, PullRequestMetadata


def check_pr_merge(
    *,
    pr: PullRequestMetadata,
    actor: ActorPermission,
    intent: Literal["merge", "squash", "rebase", "enable-auto-merge"],
):
    findings = []
    authorized = has_authorized_signal(
        pr,
        operation="merge",
        name="admin-approved:merge",
        signal_type="label",
        admin_only=True,
    ) or review_authorized(pr.reviews, admin_only=True)
    if not authorized and not actor_authorized(actor, admin_only=True):
        findings.append(
            build_finding(
                finding_id="pr-merge-guard-missing-admin-authorization",
                tool="pr_merge_guard",
                finding_class="merge-authorization",
                severity="error",
                message=f"PR {intent} requires admin-approved:merge or administrator actor.",
                subject=intent,
            )
        )
    return build_report(tool="pr_merge_guard", repo_root=Path.cwd(), findings=findings)


def check(
    *,
    pr: PullRequestMetadata,
    actor: ActorPermission,
    intent: Literal["merge", "squash", "rebase", "enable-auto-merge"],
):
    return check_pr_merge(pr=pr, actor=actor, intent=intent)
