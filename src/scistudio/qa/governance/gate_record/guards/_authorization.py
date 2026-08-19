"""The one label-gated-surface policy, shared by the guards that apply it (#2054).

``core_change_guard`` and ``architecture_doc_guard`` gate different surfaces on
different labels, but the policy is a single one: *this surface may only change
when an authorization CI can verify the provenance of exists.* Each guard used
to carry its own copy of it, which is two places for one answer to drift — and
drift here is not cosmetic, because the guards would then disagree about whether
the same owner action authorized anything at all.

They are now two configurations of :func:`check_label_gated_surface` rather than
two implementations of the same rule. What differs between them is data: which
surface class the evaluator classified, which label authorizes it, and what to
say when it is missing.

Kept out of ``_base`` on purpose: ``_base`` owns the frozen ``GuardInputs``
bundle and the ``Guard`` type, which every guard imports. This is policy, and a
guard that does not gate on a label has no reason to see it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import scistudio.qa.governance.gate_record.labels as label_vocab
from scistudio.qa.governance.gate_record.guards._base import GuardInputs
from scistudio.qa.governance.gate_record.guards._stub import source_sha
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity


def has_admin_approval_review(pr_context: Mapping[str, Any] | None) -> bool:
    """Return True when an approving review carries admin/maintainer provenance.

    Someone who reviews and approves the PR has given approval in the surface
    where they read the diff. Requiring a label *as well* would only mean saying
    yes twice.
    """

    raw_reviews = (pr_context or {}).get("reviews", [])
    if not isinstance(raw_reviews, Sequence) or isinstance(raw_reviews, str):
        return False
    for review in raw_reviews:
        if not isinstance(review, Mapping):
            continue
        state = str(review.get("state", "")).upper()
        permission = str(review.get("permission", review.get("actor_permission", ""))).lower()
        if state == "APPROVED" and permission in label_vocab.ADMIN_PERMISSIONS:
            return True
    return False


def label_has_authorized_provenance(observed: Sequence[Any], label: str) -> bool:
    """Return True when an observed admin label was applied by an authorized actor.

    ``observed`` are ledger ``AdminLabel`` objects carrying CI-verified actor
    permission provenance. A label with no provenance is treated as unverified,
    which is the case that matters: an agent can put a label on its own PR, and
    only CI can say who actually applied it.
    """

    for item in observed:
        name = getattr(item, "name", None)
        permission = getattr(item, "actor_permission", None)
        if name == label and isinstance(permission, str) and permission.lower() in label_vocab.ADMIN_PERMISSIONS:
            return True
    return False


def check_label_gated_surface(
    inputs: GuardInputs,
    *,
    tool: str,
    surface: str,
    label: str,
    rule_id: str,
    message: str,
    requested_summary_key: str,
) -> AuditReport:
    """Report an unauthorized change to a label-gated surface.

    In CI mode authorization is verified against observed labels (actor
    permission provenance) or an admin approval review. In local modes the label
    cannot be provenance-verified, so a *requested* label is treated as recorded
    pre-PR intent and the finding is downgraded to a warning — the agent learns
    before it opens the PR, while CI stays the authority. Silence downgrades
    nothing: an unrecorded intent is not an intent.

    One finding per affected path, so the repair hint can name the files rather
    than say a surface was touched.
    """

    protected = list(inputs.surfaces.get(surface, []))
    is_ci = inputs.mode == "ci"

    approved = label_has_authorized_provenance(inputs.observed_admin_labels, label)
    approved = approved or has_admin_approval_review(inputs.pr_context)
    requested = label in {requested.name for requested in inputs.requested_admin_labels}

    findings: list[Finding] = []
    if protected and not approved:
        severity = Severity.ERROR if is_ci or not requested else Severity.WARNING
        findings = [Finding(rule_id=rule_id, severity=severity, file=path, message=message) for path in protected]

    return AuditReport(
        tool=tool,
        status=AuditStatus.FAIL
        if any(finding.severity == Severity.ERROR for finding in findings)
        else AuditStatus.PASS,
        source_sha=source_sha(inputs.repo_root),
        findings=findings,
        summary={
            "protected_files": protected,
            "approved": approved,
            requested_summary_key: requested,
            "mode": inputs.mode,
        },
    )
