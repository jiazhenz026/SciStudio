"""Stage 7 validator: ``submit_reconcile``.

Done-when (ADR-042 §19.2): PR opened, CI all green, Codex review
reconciled (all P0/P1 addressed).

Phase 1 (shadow mode) validates the PR shape (number + URL pattern). The
"CI green + Codex reconciled" check is a GitHub API + Codex API call;
deferred to TC-1B.7 + the pr-maintainer skill (TC-1H.6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from scieasy.qa.workflow.gate import StageContext, ValidationResult

_PR_URL_PATTERN = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+/pull/\d+$")


@dataclass
class SubmitReconcileShapeValidator:
    """Verify declared_data carries ``pr_number`` + ``pr_url``."""

    validator_id: str = "submit_reconcile.shape"
    blocking: bool = True

    def __call__(self, ctx: StageContext) -> ValidationResult:
        data = ctx.declared_data

        pr_number = data.get("pr_number")
        if not isinstance(pr_number, int) or pr_number <= 0:
            return ValidationResult(
                validator_id=self.validator_id,
                status="fail",
                message="'pr_number' must be a positive int.",
                blocking=self.blocking,
            )

        pr_url = data.get("pr_url")
        if not isinstance(pr_url, str) or not _PR_URL_PATTERN.match(pr_url):
            return ValidationResult(
                validator_id=self.validator_id,
                status="fail",
                message=(f"'pr_url' must match {_PR_URL_PATTERN.pattern} (got {pr_url!r})."),
                blocking=self.blocking,
            )

        # TODO(#1145): verify CI all green + Codex review reconciled
        #   per ADR-042 §19.2 stage-7 done-when.
        #   Out of scope per ADR-042 §19 — depends on TC-1H.6
        #   pr-maintainer skill + GitHub Checks API integration.
        #   Followup: enable after Phase 1H Sub-PR 3 (skills) ships.

        return ValidationResult(
            validator_id=self.validator_id,
            status="pass",
            message=f"submit_reconcile shape OK (PR #{pr_number}).",
            blocking=self.blocking,
        )
