"""architecture_doc_guard calculator (#2054).

Produces: a change to the owner-controlled architecture document lacks
``admin-approved:architecture-doc`` provenance.

``docs/architecture/ARCHITECTURE.md`` is the owner's artifact. A change to it
needs the owner's specific prior approval, and until this guard existed nothing
in CI asked for one: PR #2036 carried a thirty-line addition through every
check green, Full Audit included, and it was caught by the owner reading the
diff. The gap was not an oversight in the checks so much as an inversion in the
classifier — ``surfaces.is_architecture_doc_path`` exists, and its only
consumer counts a touch of this document as a *documentation obligation
satisfied*. Editing it made a PR look better, not worse.

The shape is deliberately ``core_change_guard``'s, because the requirement is
the same one: a surface that may only change with an authorization CI can
verify the provenance of. Sharing the shape is what keeps the two from drifting
into different answers to "what counts as approval".

Reads ONLY ``GuardInputs``: the protected surface comes from the evaluator's
``surfaces`` classifier, the label vocabulary from ``labels``, and the observed
labels + PR context from the bundle. The guard keeps no path list, no label
vocabulary, and no git access of its own.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import scistudio.qa.governance.gate_record.labels as label_vocab
from scistudio.qa.governance.gate_record.guards._base import GuardInputs
from scistudio.qa.governance.gate_record.guards._stub import source_sha
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity


def _has_admin_approval_review(pr_context: Mapping[str, Any] | None) -> bool:
    """Return True when an approving review carries admin/maintainer provenance.

    An owner who reviews and approves the PR has given the specific approval the
    document requires, in the surface where they read the diff. Requiring the
    label *in addition* would only mean the owner had to say yes twice.
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


def _label_has_authorized_provenance(observed: Sequence[Any], label: str) -> bool:
    """Return True when an observed admin label was applied by an authorized actor.

    ``observed`` are ledger ``AdminLabel`` objects carrying CI-verified actor
    permission provenance. A label with no provenance is unverified, which is
    the case that matters most here: an agent can add a label to its own PR,
    and only CI can say who actually applied it.
    """

    for item in observed:
        name = getattr(item, "name", None)
        permission = getattr(item, "actor_permission", None)
        if name == label and isinstance(permission, str) and permission.lower() in label_vocab.ADMIN_PERMISSIONS:
            return True
    return False


def check(inputs: GuardInputs) -> AuditReport:
    """Hard-fail an unapproved architecture-document change in CI.

    In CI mode authorization is verified against observed labels (actor
    permission provenance) or an admin approval review. In local modes the
    label cannot be provenance-verified, so a *requested* label is treated as
    recorded pre-PR intent and the finding is downgraded to a warning — the
    agent is told before it opens the PR, and CI is still the authority.

    ``admin-approved:bypass`` and ``human-authored`` release this guard exactly
    as they release the others (owner decision, #2054). The evaluator applies
    them; this guard does not re-implement a bypass vocabulary.
    """

    protected = list(inputs.surfaces.get("protected_architecture", []))
    is_ci = inputs.mode == "ci"

    approved = _label_has_authorized_provenance(inputs.observed_admin_labels, label_vocab.ARCHITECTURE_DOC_LABEL)
    approved = approved or _has_admin_approval_review(inputs.pr_context)
    requested = label_vocab.ARCHITECTURE_DOC_LABEL in {label.name for label in inputs.requested_admin_labels}

    findings: list[Finding] = []
    if protected and not approved:
        # Local/pre-PR: a requested label is intent, not verified provenance.
        severity = Severity.ERROR if is_ci or not requested else Severity.WARNING
        message = (
            "the architecture document is owner-controlled and this change has no "
            "owner approval: apply admin-approved:architecture-doc as an authorized "
            "maintainer, or approve the PR as an administrator, or drop the change"
        )
        findings = [
            Finding(
                rule_id="architecture_doc_guard.missing-owner-approval",
                severity=severity,
                file=path,
                message=message,
            )
            for path in protected
        ]

    return AuditReport(
        tool="architecture_doc_guard",
        status=AuditStatus.FAIL if any(f.severity == Severity.ERROR for f in findings) else AuditStatus.PASS,
        source_sha=source_sha(inputs.repo_root),
        findings=findings,
        summary={
            "protected_files": protected,
            "approved": approved,
            "requested_architecture_doc": requested,
            "mode": inputs.mode,
        },
    )
