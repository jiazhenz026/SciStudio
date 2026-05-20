from __future__ import annotations

import json

from scieasy.qa.governance.sentrux_gate import parse_sentrux_result, verify_free_tier_claims


def test_parse_sentrux_result_accepts_mcp_check_rules_shape() -> None:
    evidence = parse_sentrux_result(
        {
            "check_rules": {
                "ok": True,
                "mode": "free-tier",
                "rules_checked": 3,
                "total_rules_defined": 15,
                "summary": {
                    "quality_signal": 4161,
                    "cycle_summary": {"cycles": 0},
                    "complexity_summary": {"max": 8},
                    "test_gap_summary": {"missing": 2},
                },
            }
        }
    )

    assert evidence.status == "pass"
    assert evidence.mode == "free-tier"
    assert evidence.rules_checked == 3
    assert evidence.total_rules_defined == 15
    assert evidence.quality_signal == 4161
    assert evidence.cycles == {"cycles": 0}
    assert evidence.complexity == {"max": 8}
    assert evidence.test_gap == {"missing": 2}


def test_verify_free_tier_passes_for_source_change_with_free_tier_evidence() -> None:
    report = verify_free_tier_claims(
        {
            "mode": "free-tier",
            "status": "pass",
            "rules_checked": 3,
            "total_rules_defined": 15,
            "pro_required": False,
            "quality_signal": 4161,
        },
        changed_files=["src/scieasy/qa/governance/sentrux_gate.py"],
    )

    assert not report.blocks_merge
    assert report.summary["applicable"] is True
    assert report.summary["rules_checked"] == 3


def test_verify_free_tier_rejects_missing_evidence_for_source_change() -> None:
    report = verify_free_tier_claims(
        None,
        changed_files=["src/scieasy/runtime/engine.py"],
    )

    assert report.blocks_merge
    assert [finding.rule_id for finding in report.findings] == ["sentrux.free_tier.missing-evidence"]


def test_verify_free_tier_rejects_pro_only_claims() -> None:
    report = verify_free_tier_claims(
        {
            "mode": "free-tier",
            "status": "pass",
            "rules_checked": 3,
            "total_rules_defined": 15,
            "pro_required": True,
            "diagnostics": ["complete root-cause analysis (Pro)"],
        },
        changed_files=[".workflow/gate-record.schema.json"],
    )

    assert report.blocks_merge
    rule_ids = {finding.rule_id for finding in report.findings}
    assert "sentrux.free_tier.pro-required" in rule_ids
    assert "sentrux.free_tier.pro-only-claim" in rule_ids


def test_verify_free_tier_rejects_unchecked_rule_completion_claim() -> None:
    report = verify_free_tier_claims(
        {
            "mode": "free-tier",
            "status": "pass",
            "rules_checked": 3,
            "total_rules_defined": 15,
            "all_rules_completed": True,
        },
        changed_files=[".sentrux/rules.toml"],
    )

    assert report.blocks_merge
    assert any(finding.rule_id == "sentrux.free_tier.unchecked-rules-completed" for finding in report.findings)


def test_verify_free_tier_allows_docs_only_na_with_rationale() -> None:
    report = verify_free_tier_claims(
        {
            "mode": "not-applicable",
            "status": "skipped",
            "not_applicable": True,
            "rationale": "Contributor workflow prose only; no architecture, governance, or implementation files changed.",
        },
        changed_files=["docs/contributing/workflows/human-bypass.md"],
    )

    assert not report.blocks_merge
    assert report.summary["applicable"] is False


def test_verify_free_tier_rejects_docs_architecture_na() -> None:
    report = verify_free_tier_claims(
        {
            "mode": "not-applicable",
            "status": "skipped",
            "not_applicable": True,
            "rationale": "docs only",
        },
        changed_files=["docs/adr/ADR-042-addendum1.md"],
    )

    assert report.blocks_merge
    assert [finding.rule_id for finding in report.findings] == ["sentrux.free_tier.invalid-na"]


def test_parse_sentrux_result_accepts_cli_json_string() -> None:
    evidence = parse_sentrux_result(
        json.dumps(
            {
                "mode": "free",
                "success": True,
                "rules_checked": 2,
                "total_rules_defined": 2,
                "thresholds": {"max_cycles": 0},
            }
        )
    )

    assert evidence.mode == "free-tier"
    assert evidence.status == "pass"
    assert evidence.thresholds == {"max_cycles": 0}
