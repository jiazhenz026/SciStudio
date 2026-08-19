"""architecture_doc_guard calculator (#2054).

Produces: a change to the owner-controlled architecture document lacks
``admin-approved:architecture-doc`` provenance.

``docs/architecture/ARCHITECTURE.md`` is the owner's artifact. A change to it
needs the owner's specific prior approval, and until this guard existed nothing
in CI asked for one: PR #2036 carried a thirty-line addition through every check
green, Full Audit included, and it was caught by the owner reading the diff. The
gap was less an oversight in the checks than an inversion in the classifier —
``surfaces.is_architecture_doc_path`` exists, and its only consumer counts a
touch of this document as a *documentation obligation satisfied*. Editing it
made a PR look better, not worse.

The rule body is ``core_change_guard``'s, literally: both delegate to
``_authorization.check_label_gated_surface``. That is the point rather than a
convenience — the two must not drift into different answers to "what counts as
approval", and one implementation is what makes that hold. Reads ONLY
``GuardInputs``; the guard keeps no path list, label vocabulary, or git access
of its own.
"""

from __future__ import annotations

import scistudio.qa.governance.gate_record.guards._authorization as authorization
import scistudio.qa.governance.gate_record.labels as label_vocab
from scistudio.qa.governance.gate_record.guards._base import GuardInputs
from scistudio.qa.schemas.report import AuditReport

_MESSAGE = (
    "the architecture document is owner-controlled and this change has no owner "
    "approval: apply admin-approved:architecture-doc as an authorized maintainer, "
    "or approve the PR as an administrator, or drop the change"
)


def check(inputs: GuardInputs) -> AuditReport:
    """Hard-fail an unapproved architecture-document change in CI.

    ``admin-approved:bypass`` and ``human-authored`` release this guard exactly
    as they release the others (owner decision, #2054). The evaluator applies
    them; this guard does not re-implement a bypass vocabulary.
    """

    return authorization.check_label_gated_surface(
        inputs,
        tool="architecture_doc_guard",
        surface="protected_architecture",
        label=label_vocab.ARCHITECTURE_DOC_LABEL,
        rule_id="architecture_doc_guard.missing-owner-approval",
        message=_MESSAGE,
        requested_summary_key="requested_architecture_doc",
    )
