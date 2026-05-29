"""core_change_guard calculator (ADR-042 Addendum 6 spec §4).

Produces: AI-authored protected-core change lacks admin-approved:core-change
provenance.

Ported from the legacy ``core_change_guard`` (deleted on this branch, on
``origin/main``). Reads ONLY ``GuardInputs``: protected-core surfaces come from
the evaluator's single ``surfaces`` classifier, the label vocabulary from
``labels``, and observed/requested labels + PR context from the bundle. The
guard keeps no protected-path list, label vocabulary, or git access of its own.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from scistudio.qa.governance.gate_record import labels as label_vocab
from scistudio.qa.governance.gate_record.guards import GuardInputs
from scistudio.qa.governance.gate_record.guards._stub import source_sha
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity


def _has_admin_approval_review(pr_context: Mapping[str, Any] | None) -> bool:
    """Return True when an approving review carries admin/maintainer provenance."""

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


def _label_has_authorized_provenance(observed: Sequence[Any], label: str) -> bool:
    """Return True when an observed admin label was applied by an authorized actor.

    ``observed`` are ledger ``AdminLabel`` objects carrying CI-verified actor
    permission provenance (``actor_permission``). A label with no provenance is
    treated as unverified (CI is the only authority that fills provenance).
    """

    for item in observed:
        name = getattr(item, "name", None)
        permission = getattr(item, "actor_permission", None)
        if name == label and isinstance(permission, str) and permission.lower() in label_vocab.ADMIN_PERMISSIONS:
            return True
    return False


def check(inputs: GuardInputs) -> AuditReport:
    """Hard-fail AI-authored protected-core changes without admin provenance.

    In CI mode authorization is verified against observed labels (actor
    permission provenance) or an admin approval review. In local modes the
    label cannot be provenance-verified, so a requested ``core-change`` label is
    treated as a recorded pre-PR intent and the finding is downgraded to a
    warning (the evaluator's pre-PR mode classifies it as a known gap).
    """

    protected = list(inputs.surfaces.get("protected_core", []))
    is_ci = inputs.mode == "ci"

    approved = _label_has_authorized_provenance(inputs.observed_admin_labels, label_vocab.CORE_CHANGE_LABEL)
    approved = approved or _has_admin_approval_review(inputs.pr_context)
    requested = label_vocab.CORE_CHANGE_LABEL in {label.name for label in inputs.requested_admin_labels}

    findings: list[Finding] = []
    if protected and not approved:
        # Local/pre-PR: a requested label is intent, not verified provenance.
        severity = Severity.ERROR if is_ci or not requested else Severity.WARNING
        message = (
            "protected core/runtime change requires admin-approved:core-change "
            "applied by an authorized maintainer or administrator approval"
        )
        findings = [
            Finding(
                rule_id="core_change_guard.missing-admin-approval",
                severity=severity,
                file=path,
                message=message,
            )
            for path in protected
        ]

    return AuditReport(
        tool="core_change_guard",
        status=AuditStatus.FAIL if any(f.severity == Severity.ERROR for f in findings) else AuditStatus.PASS,
        source_sha=source_sha(inputs.repo_root),
        findings=findings,
        summary={
            "protected_files": protected,
            "approved": approved,
            "requested_core_change": requested,
            "mode": inputs.mode,
        },
    )
