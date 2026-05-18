"""Stage 3 validator: ``change_plan``.

Done-when (ADR-042 §19.2): Plan posted as issue comment; files-in-plan
within declared ADR scope.

Phase 1 (shadow mode): shape check + URL pattern. The real "files-in-plan
within ADR scope" check requires the closure tool (TC-1B.4) and the ADR
``governs.files`` resolver.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from scieasy.qa.workflow.gate import StageContext, ValidationResult

_COMMENT_URL_PATTERN = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+/issues/\d+#issuecomment-\d+$")


@dataclass
class ChangePlanShapeValidator:
    """Verify declared_data carries comment URL + non-empty files list."""

    validator_id: str = "change_plan.shape"
    blocking: bool = True

    def __call__(self, ctx: StageContext) -> ValidationResult:
        data = ctx.declared_data

        url = data.get("change_plan_comment_url")
        if not isinstance(url, str) or not _COMMENT_URL_PATTERN.match(url):
            return ValidationResult(
                validator_id=self.validator_id,
                status="fail",
                message=(f"'change_plan_comment_url' must match {_COMMENT_URL_PATTERN.pattern} (got {url!r})."),
                blocking=self.blocking,
            )

        files = data.get("files_to_modify")
        if not isinstance(files, list) or not files or not all(isinstance(f, str) for f in files):
            return ValidationResult(
                validator_id=self.validator_id,
                status="fail",
                message="'files_to_modify' must be a non-empty list of str paths.",
                blocking=self.blocking,
            )

        # TODO(#1145): verify every file in files_to_modify falls within
        #   the union of declared ADRs' governs.files globs.
        #   Out of scope per ADR-042 §19 — depends on TC-1B.4 closure
        #   tool and ADR governs resolver.
        #   Followup: enable after track/adr-042/1b-audit-tools merges.

        return ValidationResult(
            validator_id=self.validator_id,
            status="pass",
            message=f"change_plan shape OK ({len(files)} files).",
            blocking=self.blocking,
        )
