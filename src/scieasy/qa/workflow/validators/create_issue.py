"""Stage 2 validator: ``create_issue``.

Done-when (ADR-042 §19.2): Issue created with strict v2 template.

In Phase 1 (shadow mode) the validator only enforces shape (issue_number
+ issue_url + URL pattern). The v2 issue template existence check ships
with the v2 template work (separate sub-PR; tracked under ADR-042 §19.2
follow-up).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from scieasy.qa.workflow.gate import StageContext, ValidationResult

_GITHUB_ISSUE_PATTERN = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+/issues/\d+$")


@dataclass
class CreateIssueShapeValidator:
    """Verify declared_data carries ``issue_number`` + ``issue_url``."""

    validator_id: str = "create_issue.shape"
    blocking: bool = True

    def __call__(self, ctx: StageContext) -> ValidationResult:
        data = ctx.declared_data

        issue_number = data.get("issue_number")
        if not isinstance(issue_number, int) or issue_number <= 0:
            return ValidationResult(
                validator_id=self.validator_id,
                status="fail",
                message="'issue_number' must be a positive int.",
                blocking=self.blocking,
            )

        issue_url = data.get("issue_url")
        if not isinstance(issue_url, str) or not _GITHUB_ISSUE_PATTERN.match(issue_url):
            return ValidationResult(
                validator_id=self.validator_id,
                status="fail",
                message=(f"'issue_url' must match {_GITHUB_ISSUE_PATTERN.pattern} (got {issue_url!r})."),
                blocking=self.blocking,
            )

        # TODO(#1145): verify the issue actually uses the strict v2
        #   template per ADR-042 §19.2.
        #   Out of scope per ADR-042 §19 — v2 issue template ships in a
        #   separate sub-PR.
        #   Followup: open as part of ADR-042 Phase 1H follow-on or §19
        #   template-author work.

        return ValidationResult(
            validator_id=self.validator_id,
            status="pass",
            message=f"create_issue shape OK (#{issue_number}).",
            blocking=self.blocking,
        )
