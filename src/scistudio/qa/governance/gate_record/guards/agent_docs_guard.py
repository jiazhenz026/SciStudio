"""Agent_docs_guard calculator."""
# Maintainer context (kept outside generated API documentation):
# agent_docs_guard calculator (#2438).
#
# Produces: a change to the owner-maintained documents SciStudio provisions into
# user projects for agents lacks ``admin-approved:agent-docs`` provenance.
#
# The bundled skills, the agent reference, and the AGENTS.md / CLAUDE.md
# template are what embedded and external agents read in a user's project. The
# owner maintains them, and before this guard nothing in CI stopped a PR from
# changing them. The surface list lives in ``surfaces`` and the label in
# ``labels``; the rule body is the one ``core_change_guard`` and
# ``architecture_doc_guard`` share, so all three give the same answer to "what
# counts as approval".
# Development references: #2054, #2438.

from __future__ import annotations

import scistudio.qa.governance.gate_record.guards._authorization as authorization
import scistudio.qa.governance.gate_record.labels as label_vocab
from scistudio.qa.governance.gate_record.guards._base import GuardInputs
from scistudio.qa.schemas.report import AuditReport

_MESSAGE = (
    "the provisioned agent documents are owner-maintained and this change has no "
    "owner approval: apply admin-approved:agent-docs as an authorized maintainer, "
    "or approve the PR as an administrator, or drop the change"
)


def check(inputs: GuardInputs) -> AuditReport:
    """Hard-fail an unapproved provisioned agent-document change in CI.

    ``admin-approved:bypass`` and ``human-authored`` release this guard exactly
    as they release the others; the evaluator applies them.
    """
    # Development references: #2438.

    return authorization.check_label_gated_surface(
        inputs,
        tool="agent_docs_guard",
        surface="protected_agent_docs",
        label=label_vocab.AGENT_DOCS_LABEL,
        rule_id="agent_docs_guard.missing-owner-approval",
        message=_MESSAGE,
        requested_summary_key="requested_agent_docs",
    )
