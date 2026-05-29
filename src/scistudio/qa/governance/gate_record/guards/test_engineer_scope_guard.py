"""test_engineer_scope_guard calculator (ADR-042 Addendum 6 spec §4).

Produces: test_engineer persona touched production/build/governance code without authorization.

STUB: returns an empty passing report so the evaluator runs end-to-end.
"""

from __future__ import annotations

from scistudio.qa.governance.gate_record.guards import GuardInputs
from scistudio.qa.governance.gate_record.guards._stub import empty_report
from scistudio.qa.schemas.report import AuditReport


def check(inputs: GuardInputs) -> AuditReport:
    """Evaluate the test_engineer_scope_guard obligation.

    # TODO(#1509): B2 implement real calculator.
    #   Out of scope for the core (B1) build per ADR-042 Addendum 6 + spec §4.
    #   Followup: https://github.com/scistudio/SciStudio/issues/1509
    """

    return empty_report("test_engineer_scope_guard", inputs.repo_root)
