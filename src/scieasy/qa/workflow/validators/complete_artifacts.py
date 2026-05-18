"""Stage 6 validator: ``complete_artifacts``.

Done-when (ADR-042 §19.2): Docstrings + ADR governs updated + MAINTAINERS
updated + translation enqueued + CHANGELOG entry + codemod committed (if
contract change) + RBP attached + skills installed cross-runtime.

Phase 1 (shadow mode) ships a scaffold that returns ``skip``. The real
``complete_artifacts.check`` orchestrator ships in TC-1B.7.
"""

from __future__ import annotations

from dataclasses import dataclass

from scieasy.qa.workflow.gate import StageContext, ValidationResult


@dataclass
class CompleteArtifactsPlaceholder:
    """Scaffold for the complete_artifacts stage.

    Returns ``skip`` until TC-1B.7 ships the orchestrator.
    """

    validator_id: str = "complete_artifacts.check"
    blocking: bool = False

    def __call__(self, ctx: StageContext) -> ValidationResult:
        # TODO(#1145): subprocess-call
        #   `python -m scieasy.qa.audit.complete_artifacts --check`
        #   per ADR-042 §19.2 stage-6 "How" column.
        #   Out of scope per ADR-042 §19 — depends on TC-1B.7
        #   (complete_artifacts orchestrator) which doesn't exist yet.
        #   Followup: enable after track/adr-042/1b-audit-tools merges.
        return ValidationResult(
            validator_id=self.validator_id,
            status="skip",
            message=(
                "complete_artifacts skipped: TC-1B.7 orchestrator not yet shipped (Phase 1 shadow-mode scaffold)."
            ),
            blocking=self.blocking,
        )
