"""mod_guard calculator (governance_mod_guard) (ADR-042 Addendum 6 spec §4).

Produces: governance-file change without a declared ``governance_touch`` +
verified authorization.

Ported from the legacy ``mod_guard`` (deleted on this branch). The governance
surface is the evaluator's single ``surfaces.is_governance_path`` classifier
(now including ``docs/ai-developer/**`` per §7.8); it replaces the standalone
``PROTECTED_PATTERNS`` that overlapped ``core_change_guard``. The two
environment-variable bypass channels (``SCISTUDIO_GOVERNANCE_CHANGE_APPROVED``
and ``SCISTUDIO_GATE_BYPASS_LABELS``) are removed: authorization now flows
through the ledger ``governance_touch`` flag plus ``requested`` (local intent) /
``observed`` (CI-verified) admin labels.
"""

from __future__ import annotations

from scistudio.qa.governance.gate_record import labels as label_vocab
from scistudio.qa.governance.gate_record.guards import GuardInputs
from scistudio.qa.governance.gate_record.guards._stub import source_sha
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity


def _has_verified_bypass(inputs: GuardInputs) -> bool:
    """Return True when a bypass label carries authorized provenance (CI only)."""

    for item in inputs.observed_admin_labels:
        permission = item.actor_permission
        if (
            item.name == label_vocab.BYPASS_LABEL
            and isinstance(permission, str)
            and permission.lower() in label_vocab.ADMIN_PERMISSIONS
        ):
            return True
    return False


def check(inputs: GuardInputs) -> AuditReport:
    """Fail when governance-critical files change without authorization.

    Authorization = a declared ``governance_touch`` on the ledger, OR a
    verified ``admin-approved:bypass`` (CI mode). In local modes a requested
    bypass label is recorded intent (the evaluator's pre-PR mode classifies the
    missing CI provenance as a known gap), so a governance change with neither
    ``governance_touch`` nor a requested bypass is the local block case.
    """

    governance = list(inputs.surfaces.get("governance", []))
    is_ci = inputs.mode == "ci"

    authorized = inputs.governance_touch or _has_verified_bypass(inputs)
    requested_bypass = label_vocab.BYPASS_LABEL in {label.name for label in inputs.requested_admin_labels}

    findings: list[Finding] = []
    if governance and not authorized:
        # Local: a requested bypass with no governance_touch is intent; the
        # missing CI provenance is a pre-PR gap, not a hard local block.
        severity = Severity.ERROR if is_ci or not requested_bypass else Severity.WARNING
        findings = [
            Finding(
                rule_id="governance.mod_guard.unauthorized-change",
                severity=severity,
                file=path,
                message=(
                    "governance-critical file changed without authorization; "
                    "declare governance_touch in the ledger and obtain owner review"
                ),
            )
            for path in governance
        ]

    return AuditReport(
        tool="governance_mod_guard",
        status=AuditStatus.FAIL if any(f.severity == Severity.ERROR for f in findings) else AuditStatus.PASS,
        source_sha=source_sha(inputs.repo_root),
        findings=findings,
        summary={
            "changed_governance_files": governance,
            "governance_touch": inputs.governance_touch,
            "authorized": authorized,
            "requested_bypass": requested_bypass,
            "mode": inputs.mode,
        },
    )
