"""docs_landing calculator (ADR-042 Addendum 6 spec §4).

Produces: governed change without docs/changelog/checklist landing or an
explicit N/A rationale.

Ported from the legacy ``docs_landing`` (deleted on this branch). The
implementation/governance surface classification now comes from the evaluator's
single ``surfaces`` classifier instead of the guard's own
``IMPLEMENTATION_PREFIXES``/``GOVERNANCE_PREFIXES`` sets. Docs evidence is
reconciled against the observed diff: only ``verified_docs_paths`` (declared docs
paths the evaluator confirmed are in the diff) count, never claimed-but-unverified
paths (spec §3.3.4). A docs N/A rationale supplied by the evaluator (via
``extras['docs_na']``) satisfies the obligation.
"""

from __future__ import annotations

from collections.abc import Sequence

from scistudio.qa.governance.gate_record.guards import GuardInputs
from scistudio.qa.governance.gate_record.guards._stub import source_sha
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity


def _governed_change(inputs: GuardInputs) -> list[str]:
    """Return changed files on a governed surface that require docs landing."""

    governed: list[str] = []
    for cls in ("implementation", "governance", "governed_docs"):
        governed.extend(inputs.surfaces.get(cls, []))
    # CHANGELOG.md itself is the landing artifact, not a governed change.
    return sorted({path for path in governed if path != "CHANGELOG.md"})


def _has_docs_na(inputs: GuardInputs) -> bool:
    raw = inputs.extras.get("docs_na")
    if isinstance(raw, Sequence) and not isinstance(raw, str):
        return any(bool(item) for item in raw)
    return bool(raw)


def check(inputs: GuardInputs) -> AuditReport:
    """Hard-fail when a governed change lacks verified docs landing or N/A."""

    governed = _governed_change(inputs)
    verified_docs = list(inputs.verified_docs_paths)
    docs_na = _has_docs_na(inputs)
    findings: list[Finding] = []

    if governed and not verified_docs and not docs_na:
        findings.append(
            Finding(
                rule_id="docs_landing.missing-landing",
                severity=Severity.ERROR,
                message=(
                    "governed change requires docs/changelog/checklist landing evidence or an explicit N/A rationale"
                ),
                evidence={"governed_files": governed},
            )
        )

    return AuditReport(
        tool="docs_landing",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=source_sha(inputs.repo_root),
        findings=findings,
        summary={
            "governed_files": governed,
            "verified_docs_paths": verified_docs,
            "docs_na": docs_na,
        },
    )
