"""pr_merge_guard calculator (ADR-042 Addendum 6 spec §4).

Produces: AI merge attempt without authorized ``admin-approved:merge``
provenance.

Ported from the legacy ``pr_merge_guard`` (deleted on this branch). Merge intent
and actor come from the real GitHub event the evaluator places in
``pr_context`` (no hard-coded ``intent='comment'`` neutering). The label
vocabulary comes from ``labels``. The guard never reads the ledger or git
itself. The guard only fires in CI mode, where a real merge event exists.
"""

from __future__ import annotations

import scistudio.qa.governance.gate_record.labels as label_vocab
from scistudio.qa.governance.gate_record.guards._base import GuardInputs
from scistudio.qa.governance.gate_record.guards._stub import source_sha
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

# Real GitHub merge-automation intents (from the event, via pr_context).
MERGE_INTENTS: frozenset[str] = frozenset({"merge", "squash", "rebase", "enable-auto-merge"})


def check(inputs: GuardInputs) -> AuditReport:
    """Block AI merge automation that lacks ``admin-approved:merge`` provenance."""

    pr_context = inputs.pr_context or {}
    intent = str(pr_context.get("merge_intent", "")).strip().lower()
    # ``is_ai_actor`` defaults to True: any actor not explicitly flagged
    # non-AI is treated as AI (the legacy fail-closed default).
    actor = pr_context.get("actor")
    if isinstance(actor, dict):
        is_ai_actor = bool(actor.get("is_ai", True))
    else:
        is_ai_actor = bool(pr_context.get("is_ai_actor", True))

    needs_approval = inputs.mode == "ci" and intent in MERGE_INTENTS and is_ai_actor

    approved = False
    for item in inputs.observed_admin_labels:
        permission = item.actor_permission
        if (
            item.name == label_vocab.MERGE_LABEL
            and isinstance(permission, str)
            and permission.lower() in label_vocab.ADMIN_PERMISSIONS
        ):
            approved = True
            break

    findings: list[Finding] = []
    if needs_approval and not approved:
        findings.append(
            Finding(
                rule_id="pr_merge_guard.missing-admin-merge-approval",
                severity=Severity.ERROR,
                message="AI merge automation requires admin-approved:merge provenance",
                evidence={
                    "intent": intent,
                    "observed_labels": sorted(item.name for item in inputs.observed_admin_labels),
                },
            )
        )

    return AuditReport(
        tool="pr_merge_guard",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=source_sha(inputs.repo_root),
        findings=findings,
        summary={"intent": intent, "needs_approval": needs_approval, "approved": approved},
    )
