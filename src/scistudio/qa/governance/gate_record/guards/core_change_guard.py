"""core_change_guard calculator (ADR-042 Addendum 6 spec §4).

Produces: AI-authored protected-core change lacks admin-approved:core-change
provenance.

Ported from the legacy ``core_change_guard`` (deleted on this branch, on
``origin/main``). Reads ONLY ``GuardInputs``: protected-core surfaces come from
the evaluator's single ``surfaces`` classifier, the label vocabulary from
``labels``, and observed/requested labels + PR context from the bundle. The
guard keeps no protected-path list, label vocabulary, or git access of its own.

The rule body lives in ``_authorization.check_label_gated_surface``, shared with
``architecture_doc_guard`` (#2054). What is left here is the configuration that
makes this guard *this* guard: which surface, which label, what to say.
"""

from __future__ import annotations

import scistudio.qa.governance.gate_record.guards._authorization as authorization
import scistudio.qa.governance.gate_record.labels as label_vocab
from scistudio.qa.governance.gate_record.guards._base import GuardInputs
from scistudio.qa.schemas.report import AuditReport

_MESSAGE = (
    "protected core/runtime change requires admin-approved:core-change "
    "applied by an authorized maintainer or administrator approval"
)


def check(inputs: GuardInputs) -> AuditReport:
    """Hard-fail AI-authored protected-core changes without admin provenance.

    In CI mode authorization is verified against observed labels (actor
    permission provenance) or an admin approval review. In local modes the
    label cannot be provenance-verified, so a requested ``core-change`` label is
    treated as a recorded pre-PR intent and the finding is downgraded to a
    warning (the evaluator's pre-PR mode classifies it as a known gap).
    """

    return authorization.check_label_gated_surface(
        inputs,
        tool="core_change_guard",
        surface="protected_core",
        label=label_vocab.CORE_CHANGE_LABEL,
        rule_id="core_change_guard.missing-admin-approval",
        message=_MESSAGE,
        requested_summary_key="requested_core_change",
    )
