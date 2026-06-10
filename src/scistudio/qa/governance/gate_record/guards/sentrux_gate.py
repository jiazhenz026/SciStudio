"""sentrux_gate calculator (ADR-042 Addendum 6 spec §4).

Produces: advisory or blocking findings on Sentrux free-tier evidence.

Ported from the legacy ``sentrux_gate`` (deleted on this branch). The
``SentruxEvidence`` model and ``parse_sentrux_result`` normalizer are carried
forward verbatim as the canonical evidence normalizer (spec §4 / digest). The
standalone ``sentrux_applies_to_changes`` predicate is dropped in favor of the
single ``surfaces.sentrux_applies`` classifier (resolving the §4.1 asymmetry).

Active-addendum semantics (ADR-042 Addendum 3, as exercised by the CI tests):
Sentrux is opt-in. Missing evidence for an applicable change is advisory (an
INFO finding), not blocking. A recorded non-passing / pro-required / invalid
evidence payload blocks (ERROR). The evaluator supplies normalized or raw
evidence via ``GuardInputs.extras['sentrux_evidence']``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator

import scistudio.qa.governance.gate_record.surfaces as surfaces
from scistudio.qa.governance.gate_record.guards._base import GuardInputs
from scistudio.qa.governance.gate_record.guards._stub import source_sha
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

FREE_TIER_MODE = "free-tier"
SENTRUX_EVIDENCE_NAME = "sentrux.free_tier"

_PRO_ONLY_KEYS = (
    "pro",
    "pro_diagnostics",
    "pro_only",
    "root_cause_analysis",
    "complete_root_cause_analysis",
    "advanced_dependency_graph",
)


class SentruxEvidence(BaseModel):
    """Normalized Sentrux evidence accepted from MCP or CLI output."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str = SENTRUX_EVIDENCE_NAME
    mode: str | None = Field(default=None, validation_alias=AliasChoices("mode", "tier", "execution_mode"))
    status: str | None = None
    command_or_tool: str | None = Field(
        default=None, validation_alias=AliasChoices("command_or_tool", "command", "tool")
    )
    rules_checked: int | None = None
    total_rules_defined: int | None = None
    quality_signal: Any | None = None
    cycles: Any | None = Field(default=None, validation_alias=AliasChoices("cycles", "cycle", "cycle_summary"))
    complexity: Any | None = Field(default=None, validation_alias=AliasChoices("complexity", "complexity_summary"))
    test_gap: Any | None = Field(
        default=None, validation_alias=AliasChoices("test_gap", "test_gap_summary", "test_gaps")
    )
    thresholds: Mapping[str, Any] = Field(default_factory=dict)
    pro_required: bool = False
    pro_claims: list[str] = Field(default_factory=list)
    checked_rules: list[str] = Field(default_factory=list)
    completed_rules: list[str] = Field(default_factory=list)
    completed_rules_count: int | None = None
    all_rules_completed: bool = False
    not_applicable: bool = False
    rationale: str | None = None
    output_path: str | None = None
    raw_summary: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return "pass" if value else "fail"
        lowered = str(value).strip().lower()
        if lowered in {"ok", "success", "successful", "passed", "pass", "true"}:
            return "pass"
        if lowered in {"failed", "fail", "error", "errors", "false"}:
            return "fail"
        if lowered in {"skipped", "skip", "n/a", "na", "not_applicable", "not-applicable"}:
            return "skipped"
        return lowered

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: Any) -> str | None:
        if value is None:
            return None
        lowered = str(value).strip().lower().replace("_", "-")
        if lowered in {"free", "free-tier", "freetier"}:
            return FREE_TIER_MODE
        if lowered in {"n/a", "na", "not-applicable", "not applicable"}:
            return "not-applicable"
        return lowered


def _ensure_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Sentrux evidence must be a JSON object")
    return cast(Mapping[str, Any], value)


def _load_json_mapping(value: str) -> Mapping[str, Any]:
    return _ensure_mapping(json.loads(value))


def _as_mapping(raw: Mapping[str, Any] | str | Path) -> Mapping[str, Any]:
    if isinstance(raw, Path):
        return _load_json_mapping(raw.read_text(encoding="utf-8"))
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith(("{", "[")):
            return _load_json_mapping(stripped)
        if Path(stripped).exists():
            return _load_json_mapping(Path(stripped).read_text(encoding="utf-8"))
        return _load_json_mapping(stripped)
    return raw


def _unwrap_payload(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    payload: Mapping[str, Any] = raw
    for key in ("sentrux", "evidence", "result", "check_rules", "scan"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            payload = cast(Mapping[str, Any], nested)
    return payload


def _status_from_payload(payload: Mapping[str, Any]) -> Any:
    for key in ("status", "state", "result"):
        value = payload.get(key)
        if isinstance(value, str | bool):
            return value
    if "ok" in payload:
        return payload["ok"]
    if "success" in payload:
        return payload["success"]
    return None


def _collect_pro_claims(payload: Mapping[str, Any]) -> list[str]:
    claims: list[str] = []
    for key in _PRO_ONLY_KEYS:
        value = payload.get(key)
        if value in (None, False, [], {}, ""):
            continue
        if key == "pro" and value is False:
            continue
        claims.append(key)
    diagnostics = payload.get("diagnostics") or payload.get("features") or payload.get("claims")
    if isinstance(diagnostics, Mapping):
        for key, value in diagnostics.items():
            key_text = str(key).lower()
            value_text = str(value).lower()
            if "pro" in key_text or "pro-only" in value_text or "root-cause" in value_text:
                claims.append(str(key))
    elif isinstance(diagnostics, Sequence) and not isinstance(diagnostics, str):
        for item in diagnostics:
            item_text = str(item).lower()
            if "pro" in item_text or "root-cause" in item_text:
                claims.append(str(item))
    return sorted(set(claims))


def parse_sentrux_result(raw: Mapping[str, Any] | str | Path) -> SentruxEvidence:
    """Normalize Sentrux MCP or CLI evidence into a deterministic model."""

    mapping = _as_mapping(raw)
    payload = _unwrap_payload(mapping)
    summary_raw = payload.get("summary")
    summary = cast(Mapping[str, Any], summary_raw) if isinstance(summary_raw, Mapping) else {}
    merged: dict[str, Any] = {**dict(summary), **dict(payload)}
    if "status" not in merged:
        merged["status"] = _status_from_payload(payload)
    if "mode" not in merged and "free_tier" in merged:
        merged["mode"] = FREE_TIER_MODE if merged["free_tier"] else merged.get("mode")
    if "pro_claims" not in merged:
        merged["pro_claims"] = _collect_pro_claims(merged)
    if "raw_summary" not in merged:
        merged["raw_summary"] = dict(summary)
    return SentruxEvidence.model_validate(merged)


def _finding(rule_id: str, message: str, *, severity: Severity = Severity.ERROR, file: str = "") -> Finding:
    return Finding(rule_id=rule_id, severity=severity, file=file, message=message)


def check(inputs: GuardInputs) -> AuditReport:
    """Validate Sentrux evidence with active-addendum (opt-in) semantics."""

    applies = surfaces.sentrux_applies_to_changes(inputs.changed_files)
    raw_evidence = inputs.extras.get("sentrux_evidence")
    source = source_sha(inputs.repo_root)
    findings: list[Finding] = []

    # Missing evidence: advisory (opt-in per the active addendum). Not blocking.
    if raw_evidence is None:
        if applies:
            findings.append(
                _finding(
                    "sentrux.free_tier.advisory-missing-evidence",
                    "Sentrux evidence is recommended for source/workflow/architecture changes (advisory, opt-in).",
                    severity=Severity.INFO,
                )
            )
        return AuditReport(
            tool="sentrux_gate",
            status=AuditStatus.PASS,
            source_sha=source,
            findings=findings,
            summary={"applicable": applies, "evidence_present": False, "mode": inputs.mode},
        )

    try:
        normalized = raw_evidence if isinstance(raw_evidence, SentruxEvidence) else parse_sentrux_result(raw_evidence)
    except (json.JSONDecodeError, OSError, ValidationError, ValueError) as exc:
        findings.append(_finding("sentrux.free_tier.invalid-evidence", f"Invalid Sentrux evidence: {exc}"))
        return AuditReport(
            tool="sentrux_gate",
            status=AuditStatus.FAIL,
            source_sha=source,
            findings=findings,
            summary={"applicable": applies, "evidence_present": True, "mode": inputs.mode},
        )

    # Recorded skipped/N/A is allowed (opt-in). A recorded failing run blocks:
    # the developer ran Sentrux, observed a real failure, and is proceeding.
    if not (normalized.not_applicable or normalized.status == "skipped" or normalized.mode == "not-applicable"):
        if normalized.pro_required:
            findings.append(
                _finding(
                    "sentrux.free_tier.pro-required",
                    "Sentrux evidence must not require Pro during the free-tier period.",
                )
            )
        if normalized.pro_claims:
            findings.append(
                _finding(
                    "sentrux.free_tier.pro-only-claim",
                    f"Sentrux evidence includes Pro-only claims: {', '.join(normalized.pro_claims)}.",
                )
            )
        if normalized.status not in (None, "pass"):
            findings.append(
                _finding(
                    "sentrux.free_tier.not-passing",
                    f"Sentrux evidence records a non-passing run; status={normalized.status!r}.",
                )
            )

    return AuditReport(
        tool="sentrux_gate",
        status=AuditStatus.FAIL if any(f.severity == Severity.ERROR for f in findings) else AuditStatus.PASS,
        source_sha=source,
        findings=findings,
        summary={
            "applicable": applies,
            "evidence_present": True,
            "mode": normalized.mode,
            "status": normalized.status,
            "rules_checked": normalized.rules_checked,
            "pro_required": normalized.pro_required,
            "pro_claims": normalized.pro_claims,
        },
    )
