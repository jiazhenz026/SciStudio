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

import scistudio.qa.governance.gate_record.labels as label_vocab
from scistudio.qa.governance.gate_record.guards._base import GuardInputs
from scistudio.qa.governance.gate_record.guards._stub import source_sha
from scistudio.qa.governance.gate_record.ledger import AdminLabel
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


def _invalid_label_findings(observed_names: set[str]) -> list[Finding]:
    findings: list[Finding] = []
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
    return findings


def _authorized_bypass(observed: list[AdminLabel], observed_names: set[str]) -> tuple[bool, list[Finding]]:
    findings: list[Finding] = []
    authorized = False
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
        elif label == label_vocab.BYPASS_LABEL:
            authorized = True
    return authorized, findings


def _requested_bypass_findings(is_ci: bool, requested_names: set[str], authorized_bypass: bool) -> list[Finding]:
    if not (is_ci and label_vocab.BYPASS_LABEL in requested_names and not authorized_bypass):
        return []
    return [
        Finding(
            rule_id="human_bypass_guard.requested-bypass-needs-provenance",
            severity=Severity.ERROR,
            message="requested admin-approved:bypass must be present on the PR with maintainer provenance",
            evidence={"requested_label": label_vocab.BYPASS_LABEL},
        )
    ]


def _ai_human_label_findings(human_label: bool, bypass_label: bool, ai_evidence: bool, runtime: str) -> list[Finding]:
    if not (human_label and ai_evidence and not bypass_label):
        return []
    return [
        Finding(
            rule_id="human_bypass_guard.ai-evidence-needs-admin-bypass",
            severity=Severity.ERROR,
            message=(
                "human-authored does not bypass AI gate evidence when the runtime is AI-authored; "
                "admin-approved:bypass is required"
            ),
            evidence={"runtime": runtime},
        )
    ]


def _bypass_status(human_label: bool, bypass_label: bool, ai_evidence: bool, findings: list[Finding]) -> str:
    if human_label and not findings and not ai_evidence:
        return "skipped-human"
    if bypass_label and not findings:
        return "admin-bypass"
    return "not_requested"


def _label_scope(inputs: GuardInputs) -> tuple[list[AdminLabel], set[str], set[str]]:
    observed = list(inputs.observed_admin_labels)
    return observed, {label.name for label in observed}, {label.name for label in inputs.requested_admin_labels}


def _evaluate_override_labels(
    inputs: GuardInputs,
    observed: list[AdminLabel],
    observed_names: set[str],
    requested_names: set[str],
) -> tuple[list[Finding], bool, bool, bool]:
    is_ci = inputs.mode == "ci"
    findings = _invalid_label_findings(observed_names)
    authorized_bypass = False
    if is_ci:
        authorized_bypass, provenance_findings = _authorized_bypass(observed, observed_names)
        findings.extend(provenance_findings)
    findings.extend(_requested_bypass_findings(is_ci, requested_names, authorized_bypass))
    human_label = label_vocab.HUMAN_AUTHORED_LABEL in observed_names
    bypass_label = label_vocab.BYPASS_LABEL in observed_names
    ai_evidence = _runtime_is_ai(inputs.runtime)
    findings.extend(_ai_human_label_findings(human_label, bypass_label, ai_evidence, inputs.runtime))
    return findings, human_label, bypass_label, ai_evidence


def _summary(
    inputs: GuardInputs,
    observed_names: set[str],
    human_label: bool,
    bypass_label: bool,
    ai_evidence: bool,
    findings: list[Finding],
) -> dict[str, object]:
    return {
        "observed_labels": sorted(observed_names),
        "valid_labels": sorted(label_vocab.VALID_LABELS),
        "ai_evidence": ai_evidence,
        "bypass_status": _bypass_status(human_label, bypass_label, ai_evidence, findings),
        "mode": inputs.mode,
    }


def _report(
    inputs: GuardInputs,
    observed_names: set[str],
    findings: list[Finding],
    human_label: bool,
    bypass_label: bool,
    ai_evidence: bool,
) -> AuditReport:
    return AuditReport(
        tool="human_bypass_guard",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=source_sha(inputs.repo_root),
        findings=findings,
        summary=_summary(inputs, observed_names, human_label, bypass_label, ai_evidence, findings),
    )


def check(inputs: GuardInputs) -> AuditReport:
    observed, observed_names, requested_names = _label_scope(inputs)
    findings, human_label, bypass_label, ai_evidence = _evaluate_override_labels(
        inputs, observed, observed_names, requested_names
    )
    return _report(inputs, observed_names, findings, human_label, bypass_label, ai_evidence)
