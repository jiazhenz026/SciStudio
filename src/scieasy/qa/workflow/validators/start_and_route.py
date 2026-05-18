"""Stage 1 validator: ``start_and_route``.

Done-when (ADR-042 §19.2): Task started + ADRs declared + MAINTAINERS
resolved + codemod plan (if contract change) + skill plan (if new skill).

In Phase 1 (this PR) this validator only checks the **shape** of the
declared data, because the downstream resolvers (MAINTAINERS query, ADR
registry lookup, skill manifest check) do not exist yet — they ship in
TCs 1B.4 (closure), 1C.2 (MAINTAINERS bootstrap), and 1H.5-1H.7 (skills).
"""

from __future__ import annotations

from dataclasses import dataclass

from scieasy.qa.workflow.gate import StageContext, ValidationResult


@dataclass
class StartAndRouteShapeValidator:
    """Verify the declared payload has the keys ADR-042 §19.3 requires.

    Required keys in ``StageContext.declared_data``:

    - ``adrs``: list of int (ADR numbers).
    - ``contract_change``: bool.
    - ``new_skills``: list of str (skill names; empty list permitted).

    Real downstream resolution (does ADR-NN exist? does the MAINTAINERS
    entry cover the task author?) is deferred to TCs 1B.4 and 1C.2.
    """

    validator_id: str = "start_and_route.shape"
    blocking: bool = True

    def __call__(self, ctx: StageContext) -> ValidationResult:
        data = ctx.declared_data
        missing = [k for k in ("adrs", "contract_change", "new_skills") if k not in data]
        if missing:
            return ValidationResult(
                validator_id=self.validator_id,
                status="fail",
                message=f"Missing required keys in declared_data: {missing}",
                blocking=self.blocking,
            )

        if not isinstance(data["adrs"], list) or not all(isinstance(x, int) for x in data["adrs"]):
            return ValidationResult(
                validator_id=self.validator_id,
                status="fail",
                message="'adrs' must be a list of int ADR numbers.",
                blocking=self.blocking,
            )

        if not isinstance(data["contract_change"], bool):
            return ValidationResult(
                validator_id=self.validator_id,
                status="fail",
                message="'contract_change' must be a bool.",
                blocking=self.blocking,
            )

        if not isinstance(data["new_skills"], list) or not all(isinstance(x, str) for x in data["new_skills"]):
            return ValidationResult(
                validator_id=self.validator_id,
                status="fail",
                message="'new_skills' must be a list of str skill names.",
                blocking=self.blocking,
            )

        # TODO(#1145): real MAINTAINERS resolution + ADR registry lookup.
        #   Out of scope per ADR-042 §19 — depends on 1B.4 closure check
        #   and 1C.2 MAINTAINERS bootstrap.
        #   Followup: implement after track/adr-042/1b-audit-tools and
        #   track/adr-042/1c-ownership merge.

        return ValidationResult(
            validator_id=self.validator_id,
            status="pass",
            message=f"start_and_route shape OK (adrs={data['adrs']}).",
            blocking=self.blocking,
        )
