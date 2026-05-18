"""Stage 4 validator: ``branch``.

Done-when (ADR-042 §19.2): Branch from latest ``main``; name
``<type>/issue-<N>/<adr>/<slug>``.

Phase 1 (shadow mode): validate the branch-name pattern only. The
"branched from latest main" check is a git-state assertion that needs
network access; deferred to TC-1B.7 (orchestrators) where pre-push
``full_audit`` runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from scieasy.qa.workflow.gate import StageContext, ValidationResult

# ADR-042 §19.2 stage 4 branch-name format:
#   <type>/issue-<N>/<adr>/<slug>
# type ∈ {feat, fix, docs, chore, refactor, test}
# N is the issue number
# <adr> is an ADR identifier (e.g. "adr-042" or "ADR-042")
# <slug> is kebab-case identifier
_BRANCH_PATTERN = re.compile(r"^(feat|fix|docs|chore|refactor|test)/issue-\d+/[Aa][Dd][Rr]-\d+/[a-z0-9][a-z0-9-]*$")


@dataclass
class BranchNameValidator:
    """Enforce the ADR-042 §19.2 stage-4 branch-name format."""

    validator_id: str = "branch.name_format"
    blocking: bool = True

    def __call__(self, ctx: StageContext) -> ValidationResult:
        name = ctx.branch
        if not isinstance(name, str) or not _BRANCH_PATTERN.match(name):
            return ValidationResult(
                validator_id=self.validator_id,
                status="fail",
                message=(
                    "branch name must match "
                    f"{_BRANCH_PATTERN.pattern} (got {name!r}). "
                    "Format: <type>/issue-<N>/<adr>/<slug>"
                ),
                blocking=self.blocking,
            )

        # TODO(#1145): also verify the branch is up-to-date with latest
        #   origin/main.
        #   Out of scope per ADR-042 §19 — git-state check deferred to
        #   TC-1B.7 full_audit --pre-push.
        #   Followup: enable after track/adr-042/1b-audit-tools merges.

        return ValidationResult(
            validator_id=self.validator_id,
            status="pass",
            message=f"branch name OK ({name}).",
            blocking=self.blocking,
        )
