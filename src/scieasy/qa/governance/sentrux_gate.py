"""Validate Sentrux free-tier evidence for ADR-042 gate records."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator

from scieasy.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

FREE_TIER_MODE = "free-tier"
SENTRUX_EVIDENCE_NAME = "sentrux.free_tier"

_SOURCE_PREFIXES = (
    "src/",
    "tests/",
    "packages/",
    "frontend/",
    "scripts/hooks/",
)
_WORKFLOW_PREFIXES = (
    ".github/workflows/",
    ".workflow/",
    ".sentrux/",
)
_ARCHITECTURE_DOC_PREFIXES = (
    "docs/adr/",
    "docs/specs/",
    "docs/architecture/",
)
_GOVERNANCE_FILES = {
    ".pre-commit-config.yaml",
    "AGENTS.md",
}
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


def _source_sha(repo_root: Path | None = None) -> str:
    if repo_root is None:
        return "unknown"
    try:
        import subprocess

        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _as_mapping(raw: Mapping[str, Any] | str | Path) -> Mapping[str, Any]:
    if isinstance(raw, Path):
        return json.loads(raw.read_text(encoding="utf-8"))
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith(("{", "[")):
            return json.loads(stripped)
        if Path(stripped).exists():
            return json.loads(Path(stripped).read_text(encoding="utf-8"))
        return json.loads(stripped)
    return raw


def _unwrap_payload(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    payload: Mapping[str, Any] = raw
    for key in ("sentrux", "evidence", "result", "check_rules", "scan"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            payload = nested
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
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
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


def sentrux_applies_to_changes(changed_files: Sequence[str] | None) -> bool:
    """Return true when changed files require Sentrux evidence."""

    if not changed_files:
        return True
    for path in changed_files:
        normalized = path.replace("\\", "/")
        if normalized in _GOVERNANCE_FILES:
            return True
        if normalized.startswith(_SOURCE_PREFIXES + _WORKFLOW_PREFIXES + _ARCHITECTURE_DOC_PREFIXES):
            return True
    return False


def _finding(rule_id: str, message: str, *, file: str = "") -> Finding:
    return Finding(rule_id=rule_id, severity=Severity.ERROR, file=file, message=message)


def _unchecked_completion_claims(evidence: SentruxEvidence) -> list[Finding]:
    findings: list[Finding] = []
    rules_checked = evidence.rules_checked
    total_rules_defined = evidence.total_rules_defined
    if rules_checked is None or total_rules_defined is None or total_rules_defined <= rules_checked:
        return findings
    if evidence.all_rules_completed:
        findings.append(
            _finding(
                "sentrux.free_tier.unchecked-rules-completed",
                "Sentrux evidence claims all rules completed although free-tier output did not check every rule.",
            )
        )
    if evidence.completed_rules_count is not None and evidence.completed_rules_count > rules_checked:
        findings.append(
            _finding(
                "sentrux.free_tier.unchecked-rules-completed",
                "Sentrux evidence claims more completed rules than rules_checked.",
            )
        )
    if evidence.completed_rules and len(evidence.completed_rules) > rules_checked:
        findings.append(
            _finding(
                "sentrux.free_tier.unchecked-rules-completed",
                "Sentrux evidence lists more completed rules than rules_checked.",
            )
        )
    return findings


def verify_free_tier_claims(
    evidence: Mapping[str, Any] | str | Path | SentruxEvidence | None,
    *,
    changed_files: Sequence[str] | None = None,
    repo_root: Path | None = None,
) -> AuditReport:
    """Validate Sentrux evidence against ADR-042 free-tier gate semantics."""

    applies = sentrux_applies_to_changes(changed_files)
    source_sha = _source_sha(repo_root)
    findings: list[Finding] = []

    if evidence is None:
        if applies:
            findings.append(
                _finding(
                    "sentrux.free_tier.missing-evidence",
                    "Sentrux evidence is required for source, workflow, architecture, governance, or Sentrux rule changes.",
                )
            )
        return AuditReport(
            tool="sentrux_gate",
            status=AuditStatus.FAIL if findings else AuditStatus.PASS,
            source_sha=source_sha,
            findings=findings,
            summary={"applicable": applies, "evidence_present": False},
        )

    try:
        normalized = evidence if isinstance(evidence, SentruxEvidence) else parse_sentrux_result(evidence)
    except (json.JSONDecodeError, OSError, ValidationError, ValueError) as exc:
        findings.append(_finding("sentrux.free_tier.invalid-evidence", f"Invalid Sentrux evidence: {exc}"))
        return AuditReport(
            tool="sentrux_gate",
            status=AuditStatus.FAIL,
            source_sha=source_sha,
            findings=findings,
            summary={"applicable": applies, "evidence_present": True},
        )

    if normalized.not_applicable or normalized.status == "skipped" or normalized.mode == "not-applicable":
        if applies:
            findings.append(
                _finding(
                    "sentrux.free_tier.invalid-na",
                    "Sentrux N/A evidence is not allowed for source, workflow, architecture, governance, or Sentrux rule changes.",
                )
            )
        elif not normalized.rationale:
            findings.append(
                _finding(
                    "sentrux.free_tier.missing-na-rationale",
                    "Documentation-only Sentrux N/A evidence must include a rationale.",
                )
            )
    else:
        if normalized.mode != FREE_TIER_MODE:
            findings.append(
                _finding(
                    "sentrux.free_tier.invalid-mode",
                    "Sentrux evidence must declare mode='free-tier'.",
                )
            )
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
        if normalized.status != "pass":
            findings.append(
                _finding(
                    "sentrux.free_tier.nonpassing-status",
                    f"Sentrux free-tier evidence must pass; got status={normalized.status!r}.",
                )
            )
        if normalized.rules_checked is None:
            findings.append(
                _finding(
                    "sentrux.free_tier.missing-rules-checked",
                    "Sentrux evidence must include rules_checked when applicable.",
                )
            )
        elif normalized.rules_checked < 0:
            findings.append(_finding("sentrux.free_tier.invalid-rules-checked", "rules_checked must be non-negative."))
        if normalized.total_rules_defined is not None and normalized.total_rules_defined < 0:
            findings.append(
                _finding("sentrux.free_tier.invalid-total-rules", "total_rules_defined must be non-negative.")
            )
        findings.extend(_unchecked_completion_claims(normalized))

    return AuditReport(
        tool="sentrux_gate",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=source_sha,
        findings=findings,
        summary={
            "applicable": applies,
            "evidence_present": True,
            "mode": normalized.mode,
            "status": normalized.status,
            "rules_checked": normalized.rules_checked,
            "total_rules_defined": normalized.total_rules_defined,
            "quality_signal": normalized.quality_signal,
            "cycles": normalized.cycles,
            "complexity": normalized.complexity,
            "test_gap": normalized.test_gap,
            "pro_required": normalized.pro_required,
            "pro_claims": normalized.pro_claims,
        },
    )


def _render_text(report: AuditReport) -> str:
    if not report.findings:
        return "sentrux_gate: pass"
    lines = ["sentrux_gate: fail"]
    lines.extend(f"- {finding.rule_id}: {finding.message}" for finding in report.findings)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="Path to Sentrux MCP/CLI JSON evidence")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = verify_free_tier_claims(
        args.evidence,
        changed_files=args.changed_file,
        repo_root=args.repo_root,
    )
    if args.format == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print(_render_text(report))
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    sys.exit(main())
