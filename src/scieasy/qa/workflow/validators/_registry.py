"""Validator ID → callable registry for Workflow v2 stages.

``.workflow/schema-v2.yaml`` references validators by string ID; this
module is the single source of truth that maps ID → instantiated
``Validator`` callable.

The registry is intentionally explicit (no entry-point auto-discovery)
so the static set of validators is auditable per ADR-042 §28.1 (no
hidden behaviour).

References
----------
ADR-042 §19.5 — stage definitions in code.
ADR-042 §28.1 — meta-recursion / no hidden behaviour requirement.
"""

from __future__ import annotations

from scieasy.qa.workflow.gate import Validator
from scieasy.qa.workflow.validators.branch import BranchNameValidator
from scieasy.qa.workflow.validators.change_plan import ChangePlanShapeValidator
from scieasy.qa.workflow.validators.complete_artifacts import (
    CompleteArtifactsPlaceholder,
)
from scieasy.qa.workflow.validators.create_issue import CreateIssueShapeValidator
from scieasy.qa.workflow.validators.implement_validate import (
    ImplementValidatePlaceholder,
)
from scieasy.qa.workflow.validators.start_and_route import (
    StartAndRouteShapeValidator,
)
from scieasy.qa.workflow.validators.submit_reconcile import (
    SubmitReconcileShapeValidator,
)

# Public mapping. Keys are exactly the ``validator_id`` strings that
# ``schema-v2.yaml`` references.
VALIDATORS: dict[str, Validator] = {
    "start_and_route.shape": StartAndRouteShapeValidator(),
    "create_issue.shape": CreateIssueShapeValidator(),
    "change_plan.shape": ChangePlanShapeValidator(),
    "branch.name_format": BranchNameValidator(),
    "implement_validate.full_audit": ImplementValidatePlaceholder(),
    "complete_artifacts.check": CompleteArtifactsPlaceholder(),
    "submit_reconcile.shape": SubmitReconcileShapeValidator(),
}


def get_validator(validator_id: str) -> Validator:
    """Look up a registered validator by ID.

    Raises ``KeyError`` (with helpful message) if the ID is unknown.
    The gate loader catches this and reports a descriptive error
    pointing at ``schema-v2.yaml``.
    """
    try:
        return VALIDATORS[validator_id]
    except KeyError as exc:
        known = sorted(VALIDATORS.keys())
        raise KeyError(
            f"Unknown validator_id {validator_id!r}. "
            f"Known: {known}. "
            f"Did you forget to register a new validator in "
            f"scieasy.qa.workflow.validators._registry?"
        ) from exc
