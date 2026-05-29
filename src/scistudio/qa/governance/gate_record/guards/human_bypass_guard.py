"""human_bypass_guard calculator (ADR-042 Addendum 6 spec §4).

Produces: ``human-authored`` / ``admin-approved:bypass`` claimed without
verified maintainer/admin provenance, or an invalid override-label vocabulary.

Ported from the legacy ``human_bypass_guard`` (deleted on this branch). The
shared label vocabulary now lives in ``labels`` (no longer exported from here),
and the legacy ``admin-approved:ai-override`` label is migrated to
``admin-approved:bypass``. AI evidence is derived from the ledger ``runtime``
field rather than the legacy commit-message heuristic (digest decision).
"""

from __future__ import annotations

from scistudio.qa.governance.gate_record import labels as label_vocab
from scistudio.qa.governance.gate_record.guards import GuardInputs
from scistudio.qa.governance.gate_record.guards._stub import source_sha
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

# Runtimes that mark work as AI-authored (so ``human-authored`` cannot silently
# bypass AI gate evidence). A non-AI runtime (e.g. an empty/"human" value)
# means no AI evidence is present.
_AI_RUNTIME_PREFIXES: tuple[str, ...] = ("claude", "codex", "gemini", "gpt", "ai", "agent")


def _runtime_is_ai(runtime: str) -> bool:
    normalized = runtime.strip().lower()
    if not normalized or normalized in {"human", "none", "manual"}:
        return False
    return any(normalized.startswith(prefix) for prefix in _AI_RUNTIME_PREFIXES)


def check(inputs: GuardInputs) -> AuditReport:
    """Validate human/admin override-label provenance against observed labels.

    Provenance is only verifiable in CI mode (observed labels carry
    ``actor_permission``). In local modes requested bypass labels are recorded
    intent and are not failed for missing provenance.
    """

    is_ci = inputs.mode == "ci"
    observed = list(inputs.observed_admin_labels)
    observed_names = {label.name for label in observed}
    findings: list[Finding] = []

    # 1. Invalid override-label vocabulary (any human*/admin-approved* label
    #    outside the canonical set) — checked against observed labels.
    for invalid in label_vocab.invalid_admin_labels(observed_names):
        if invalid.startswith(("human", "admin-approved")):
            findings.append(
                Finding(
                    rule_id="human_bypass_guard.invalid-override-label",
                    severity=Severity.ERROR,
                    message="override label is not part of the ADR-042 vocabulary",
                    evidence={"label": invalid, "valid_labels": sorted(label_vocab.VALID_LABELS)},
                )
            )

    # 2. Observed override labels must carry authorized maintainer provenance
    #    (CI mode only — local labels are intent, not verified).
    if is_ci:
        for label in sorted(observed_names & label_vocab.VALID_LABELS):
            provenance = next(
                (
                    item.actor_permission
                    for item in observed
                    if item.name == label and isinstance(item.actor_permission, str)
                ),
                None,
            )
            if provenance is None or provenance.lower() not in label_vocab.ADMIN_PERMISSIONS:
                findings.append(
                    Finding(
                        rule_id="human_bypass_guard.unauthorized-label",
                        severity=Severity.ERROR,
                        message="override label must be applied by an authorized maintainer",
                        evidence={"label": label},
                    )
                )

    # 3. ``human-authored`` does not bypass AI gate evidence when the runtime is
    #    AI-authored; that requires ``admin-approved:bypass``.
    human_label = label_vocab.HUMAN_AUTHORED_LABEL in observed_names
    bypass_label = label_vocab.BYPASS_LABEL in observed_names
    ai_evidence = _runtime_is_ai(inputs.runtime)
    if human_label and ai_evidence and not bypass_label:
        findings.append(
            Finding(
                rule_id="human_bypass_guard.ai-evidence-needs-admin-bypass",
                severity=Severity.ERROR,
                message=(
                    "human-authored does not bypass AI gate evidence when the runtime is AI-authored; "
                    "admin-approved:bypass is required"
                ),
                evidence={"runtime": inputs.runtime},
            )
        )

    bypass_status = "not_requested"
    if human_label and not findings and not ai_evidence:
        bypass_status = "skipped-human"
    elif bypass_label and not findings:
        bypass_status = "admin-bypass"

    return AuditReport(
        tool="human_bypass_guard",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=source_sha(inputs.repo_root),
        findings=findings,
        summary={
            "observed_labels": sorted(observed_names),
            "valid_labels": sorted(label_vocab.VALID_LABELS),
            "ai_evidence": ai_evidence,
            "bypass_status": bypass_status,
            "mode": inputs.mode,
        },
    )
