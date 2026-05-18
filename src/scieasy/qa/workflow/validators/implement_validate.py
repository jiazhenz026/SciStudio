"""Stage 5 validator: ``implement_validate``.

Done-when (ADR-042 §19.2): Implementation complete;
``python -m scieasy.qa.audit.full_audit --pre-push`` returns 0 errors;
all commits carry ``Assisted-by:`` if agent-authored.

In Phase 1 (shadow mode) this validator returns ``skip`` because the
downstream ``full_audit`` orchestrator does not exist yet — it ships in
TC-1B.7. Once 1B.7 lands, this validator will subprocess-call the
orchestrator and surface its findings.
"""

from __future__ import annotations

from dataclasses import dataclass

from scieasy.qa.workflow.gate import StageContext, ValidationResult


@dataclass
class ImplementValidatePlaceholder:
    """Scaffold for the implement_validate stage.

    Returns ``skip`` until TC-1B.7 ships the ``full_audit`` orchestrator.
    """

    validator_id: str = "implement_validate.full_audit"
    blocking: bool = False

    def __call__(self, ctx: StageContext) -> ValidationResult:
        # TODO(#1145): subprocess-call
        #   `python -m scieasy.qa.audit.full_audit --pre-push` and
        #   surface its 0-error contract via ValidationResult.
        #   Out of scope per ADR-042 §19 — depends on TC-1B.7
        #   (full_audit orchestrator) which doesn't exist yet.
        #   Followup: enable after track/adr-042/1b-audit-tools merges.
        return ValidationResult(
            validator_id=self.validator_id,
            status="skip",
            message=(
                "implement_validate skipped: TC-1B.7 full_audit orchestrator "
                "not yet shipped (Phase 1 shadow-mode scaffold)."
            ),
            blocking=self.blocking,
        )
