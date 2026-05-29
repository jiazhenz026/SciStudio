"""Unit tests for the ADR-042 Addendum 6 evaluator-owned guard calculators.

Each guard is driven through the frozen ``GuardInputs`` bundle (spec §4). For
every calculator there is at least a passing case and the key blocking case.
These tests own ``src/scistudio/qa/governance/gate_record/guards/*.py`` behavior;
the evaluator-integration assertions live in ``test_gate_evaluator.py``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from scistudio.qa.governance.gate_record.guards import (
    GuardInputs,
    core_change_guard,
    docs_landing,
    human_bypass_guard,
    issue_link,
    mod_guard,
    persona_policy,
    pr_merge_guard,
    sentrux_gate,
    test_engineer_scope_guard,
    weakened_ci_check,
)
from scistudio.qa.governance.gate_record.ledger import AdminLabel, IssueRef
from scistudio.qa.schemas.report import AuditStatus, Severity

REPO_ROOT = Path(__file__).resolve().parents[2]

_SURFACE_CLASSES = (
    "implementation",
    "test",
    "governance",
    "protected_core",
    "frontend",
    "packaging",
    "workflow_ci",
    "docs",
    "governed_docs",
    "sentrux",
)


def _inputs(
    *,
    mode: str = "local",
    task_kind: str = "bugfix",
    persona: str = "implementer",
    runtime: str = "claude-code",
    tier: int = 2,
    governance_touch: bool = False,
    changed_files: Sequence[str] = (),
    surfaces: Mapping[str, Sequence[str]] | None = None,
    effective_include: Sequence[str] = (),
    effective_exclude: Sequence[str] = (),
    declared_docs_paths: Sequence[str] = (),
    declared_test_paths: Sequence[str] = (),
    verified_docs_paths: Sequence[str] = (),
    verified_test_paths: Sequence[str] = (),
    issues: Sequence[IssueRef] = (),
    pr_body: str | None = None,
    pr_context: Mapping[str, Any] | None = None,
    requested_admin_labels: Sequence[AdminLabel] = (),
    observed_admin_labels: Sequence[AdminLabel] = (),
    extras: Mapping[str, Any] | None = None,
) -> GuardInputs:
    grouped: dict[str, list[str]] = {name: [] for name in _SURFACE_CLASSES}
    if surfaces is not None:
        for name, paths in surfaces.items():
            grouped[name] = list(paths)
    return GuardInputs(
        repo_root=REPO_ROOT,
        mode=mode,
        task_kind=task_kind,  # type: ignore[arg-type]
        persona=persona,  # type: ignore[arg-type]
        runtime=runtime,
        tier=tier,  # type: ignore[arg-type]
        governance_touch=governance_touch,
        changed_files=list(changed_files),
        diff_fingerprint=None,
        surfaces=grouped,
        effective_include=list(effective_include),
        effective_exclude=list(effective_exclude),
        declared_docs_paths=list(declared_docs_paths),
        declared_test_paths=list(declared_test_paths),
        verified_docs_paths=list(verified_docs_paths),
        verified_test_paths=list(verified_test_paths),
        issues=list(issues),
        pr_body=pr_body,
        pr_context=pr_context,
        requested_admin_labels=list(requested_admin_labels),
        observed_admin_labels=list(observed_admin_labels),
        extras=dict(extras or {}),
    )


def _rule_ids(report: Any) -> set[str]:
    return {finding.rule_id for finding in report.findings}


# ---------------------------------------------------------------------------
# core_change_guard
# ---------------------------------------------------------------------------


def test_core_change_passes_without_protected_change() -> None:
    report = core_change_guard.check(_inputs(surfaces={"protected_core": []}))
    assert report.status is AuditStatus.PASS
    assert not report.blocks_merge


def test_core_change_blocks_ci_protected_change_without_label() -> None:
    report = core_change_guard.check(_inputs(mode="ci", surfaces={"protected_core": ["src/scistudio/core/x.py"]}))
    assert report.blocks_merge
    assert "core_change_guard.missing-admin-approval" in _rule_ids(report)


def test_core_change_passes_with_verified_core_change_label() -> None:
    report = core_change_guard.check(
        _inputs(
            mode="ci",
            surfaces={"protected_core": ["src/scistudio/core/x.py"]},
            observed_admin_labels=[AdminLabel(name="admin-approved:core-change", actor_permission="admin")],
        )
    )
    assert report.status is AuditStatus.PASS
    assert not report.blocks_merge


def test_core_change_local_requested_label_is_warning_not_block() -> None:
    report = core_change_guard.check(
        _inputs(
            mode="local",
            surfaces={"protected_core": ["src/scistudio/core/x.py"]},
            requested_admin_labels=[AdminLabel(name="admin-approved:core-change")],
        )
    )
    # A requested (unverified) label downgrades the local finding to a warning.
    assert not report.blocks_merge
    assert any(f.severity == Severity.WARNING for f in report.findings)


# ---------------------------------------------------------------------------
# human_bypass_guard
# ---------------------------------------------------------------------------


def test_human_bypass_passes_with_no_override_labels() -> None:
    report = human_bypass_guard.check(_inputs(mode="ci"))
    assert report.status is AuditStatus.PASS


def test_human_bypass_blocks_invalid_override_label() -> None:
    report = human_bypass_guard.check(
        _inputs(mode="ci", observed_admin_labels=[AdminLabel(name="admin-approved:ai-override")])
    )
    assert report.blocks_merge
    assert "human_bypass_guard.invalid-override-label" in _rule_ids(report)


def test_human_bypass_blocks_human_authored_with_ai_runtime() -> None:
    report = human_bypass_guard.check(
        _inputs(
            mode="ci",
            runtime="claude-code",
            observed_admin_labels=[AdminLabel(name="human-authored", actor_permission="admin")],
        )
    )
    assert report.blocks_merge
    assert "human_bypass_guard.ai-evidence-needs-admin-bypass" in _rule_ids(report)


def test_human_bypass_unverified_label_blocks_in_ci() -> None:
    report = human_bypass_guard.check(
        _inputs(mode="ci", observed_admin_labels=[AdminLabel(name="admin-approved:bypass")])
    )
    assert "human_bypass_guard.unauthorized-label" in _rule_ids(report)


# ---------------------------------------------------------------------------
# pr_merge_guard
# ---------------------------------------------------------------------------


def test_pr_merge_passes_without_merge_intent() -> None:
    report = pr_merge_guard.check(_inputs(mode="ci", pr_context={"merge_intent": "comment"}))
    assert report.status is AuditStatus.PASS


def test_pr_merge_blocks_ai_merge_without_approval() -> None:
    report = pr_merge_guard.check(_inputs(mode="ci", pr_context={"merge_intent": "merge", "is_ai_actor": True}))
    assert report.blocks_merge
    assert "pr_merge_guard.missing-admin-merge-approval" in _rule_ids(report)


def test_pr_merge_passes_with_verified_merge_label() -> None:
    report = pr_merge_guard.check(
        _inputs(
            mode="ci",
            pr_context={"merge_intent": "squash"},
            observed_admin_labels=[AdminLabel(name="admin-approved:merge", actor_permission="maintain")],
        )
    )
    assert report.status is AuditStatus.PASS


def test_pr_merge_does_not_fire_in_local_mode() -> None:
    report = pr_merge_guard.check(_inputs(mode="local", pr_context={"merge_intent": "merge"}))
    assert report.status is AuditStatus.PASS


# ---------------------------------------------------------------------------
# mod_guard
# ---------------------------------------------------------------------------


def test_mod_guard_passes_without_governance_change() -> None:
    report = mod_guard.check(_inputs(surfaces={"governance": []}))
    assert report.status is AuditStatus.PASS


def test_mod_guard_blocks_governance_change_without_authorization() -> None:
    report = mod_guard.check(_inputs(mode="ci", surfaces={"governance": ["docs/ai-developer/rules.md"]}))
    assert report.blocks_merge
    assert "governance.mod_guard.unauthorized-change" in _rule_ids(report)


def test_mod_guard_passes_with_governance_touch() -> None:
    report = mod_guard.check(
        _inputs(
            mode="ci",
            governance_touch=True,
            surfaces={"governance": ["docs/ai-developer/rules.md"]},
        )
    )
    assert report.status is AuditStatus.PASS


def test_mod_guard_local_requested_bypass_is_warning() -> None:
    report = mod_guard.check(
        _inputs(
            mode="local",
            surfaces={"governance": [".github/workflows/ci.yml"]},
            requested_admin_labels=[AdminLabel(name="admin-approved:bypass")],
        )
    )
    assert not report.blocks_merge


# ---------------------------------------------------------------------------
# weakened_ci_check
# ---------------------------------------------------------------------------


def test_weakened_ci_passes_with_no_governed_diff() -> None:
    report = weakened_ci_check.check(_inputs())
    assert report.status is AuditStatus.PASS
    assert report.summary["governed_diff_supplied"] is False


def test_weakened_ci_blocks_removed_required_token() -> None:
    diff = (
        "diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml\n"
        "--- a/.github/workflows/ci.yml\n"
        "+++ b/.github/workflows/ci.yml\n"
        "-        run: ruff check .\n"
    )
    report = weakened_ci_check.check(_inputs(extras={"governed_diff_text": diff}))
    assert report.blocks_merge
    assert any(rid.startswith("weakened-ci.removed-") for rid in _rule_ids(report))


def test_weakened_ci_blocks_added_continue_on_error() -> None:
    diff = "diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml\n+        continue-on-error: true\n"
    report = weakened_ci_check.check(_inputs(extras={"governed_diff_text": diff}))
    assert report.blocks_merge
    assert "weakened-ci.added-continue-on-error" in _rule_ids(report)


def test_weakened_ci_blocks_removed_intrinsic_pre_commit_hook() -> None:
    # Ported from the deleted test_governance_weakened_ci_check.py: removing an
    # intrinsic pre-commit safety hook (detect-private-key) is a weakening.
    diff = (
        "diff --git a/.pre-commit-config.yaml b/.pre-commit-config.yaml\n"
        "--- a/.pre-commit-config.yaml\n"
        "+++ b/.pre-commit-config.yaml\n"
        "-      - id: detect-private-key\n"
    )
    report = weakened_ci_check.check(_inputs(extras={"governed_diff_text": diff}))
    assert report.blocks_merge
    assert "weakened-ci.removed-detect-private-key" in _rule_ids(report)


def test_weakened_ci_accepts_prelexed_lines() -> None:
    report = weakened_ci_check.check(
        _inputs(
            extras={
                "governed_diff_lines": [
                    [".pre-commit-config.yaml", "+", "run: git commit --no-verify"],
                ]
            }
        )
    )
    assert report.blocks_merge
    assert "weakened-ci.added-no-verify" in _rule_ids(report)


def test_weakened_ci_tokens_are_specific_not_generic_python_head() -> None:
    # Defect 1 regression (#1509): catalog commands launched via ``python -m``
    # (full_audit, wheel build) must contribute a SPECIFIC distinguishing token
    # (module path / subcommand), never the generic ``python -m`` head that
    # collides with any other ``python -m ...`` invocation.
    tokens = dict(weakened_ci_check._required_removal_tokens())
    assert "python -m" not in set(tokens.values())
    assert "python" not in set(tokens.values())
    assert tokens["full_audit"] == "scistudio.qa.audit.full_audit"
    assert tokens["wheel_release_smoke"] == "build"
    assert tokens["type_check"] == "mypy"
    assert tokens["import_contracts"] == "lint-imports"
    assert tokens["semantic_dup"] == "scripts/semantic_dup_scan.py"


def test_weakened_ci_does_not_flag_gate_record_ci_to_check_fold() -> None:
    # Defect 1 regression (#1509): folding the CI invocation from
    # ``python -m ...gate_record ci`` to ``... gate_record check --mode ci`` must
    # NOT be read as removing a required CI/pre-commit check token. With the old
    # truncated ``python -m`` token this removal false-matched full_audit/wheel.
    diff = (
        "diff --git a/.github/workflows/workflow-gate.yml b/.github/workflows/workflow-gate.yml\n"
        "--- a/.github/workflows/workflow-gate.yml\n"
        "+++ b/.github/workflows/workflow-gate.yml\n"
        "-          PYTHONPATH=src python -m scistudio.qa.governance.gate_record ci \\\n"
        "+          PYTHONPATH=src python -m scistudio.qa.governance.gate_record check \\\n"
        "+            --mode ci \\\n"
    )
    report = weakened_ci_check.check(_inputs(extras={"governed_diff_text": diff}))
    assert report.status is AuditStatus.PASS
    assert not report.blocks_merge


def test_weakened_ci_still_flags_genuine_full_audit_removal() -> None:
    # The token precision fix must NOT let a genuine removal slip: deleting the
    # full_audit invocation from a governed CI workflow is still a weakening.
    diff = (
        "diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml\n"
        "--- a/.github/workflows/ci.yml\n"
        "+++ b/.github/workflows/ci.yml\n"
        "-          PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root .\n"
    )
    report = weakened_ci_check.check(_inputs(extras={"governed_diff_text": diff}))
    assert report.blocks_merge
    assert "weakened-ci.removed-full_audit" in _rule_ids(report)


def test_weakened_ci_still_flags_deleted_pre_commit_hook() -> None:
    # A pre-commit hook genuinely deleted with no replacement still trips the
    # guard (the token precision change only narrows python -m, not real removals).
    diff = (
        "diff --git a/.pre-commit-config.yaml b/.pre-commit-config.yaml\n"
        "--- a/.pre-commit-config.yaml\n"
        "+++ b/.pre-commit-config.yaml\n"
        "-      - id: ruff\n"
    )
    report = weakened_ci_check.check(_inputs(extras={"governed_diff_text": diff}))
    assert report.blocks_merge
    assert "weakened-ci.removed-lint_format" in _rule_ids(report) or "weakened-ci.removed-format_check" in _rule_ids(
        report
    )


# ---------------------------------------------------------------------------
# sentrux_gate
# ---------------------------------------------------------------------------


def test_sentrux_missing_evidence_is_advisory_not_blocking() -> None:
    report = sentrux_gate.check(_inputs(changed_files=["src/scistudio/x.py"]))
    assert report.status is AuditStatus.PASS
    assert not report.blocks_merge
    assert "sentrux.free_tier.advisory-missing-evidence" in _rule_ids(report)


def test_sentrux_passing_evidence_passes() -> None:
    report = sentrux_gate.check(
        _inputs(
            changed_files=["src/scistudio/x.py"],
            extras={"sentrux_evidence": {"mode": "free-tier", "status": "pass", "rules_checked": 5}},
        )
    )
    assert report.status is AuditStatus.PASS


def test_sentrux_recorded_failure_blocks() -> None:
    report = sentrux_gate.check(
        _inputs(
            changed_files=["src/scistudio/x.py"],
            extras={"sentrux_evidence": {"mode": "free-tier", "status": "fail", "rules_checked": 5}},
        )
    )
    assert report.blocks_merge
    assert "sentrux.free_tier.not-passing" in _rule_ids(report)


def test_sentrux_pro_required_blocks() -> None:
    report = sentrux_gate.check(
        _inputs(
            changed_files=["src/scistudio/x.py"],
            extras={"sentrux_evidence": {"status": "pass", "pro_required": True}},
        )
    )
    assert report.blocks_merge
    assert "sentrux.free_tier.pro-required" in _rule_ids(report)


def test_sentrux_normalizer_unwraps_nested_payload() -> None:
    evidence = sentrux_gate.parse_sentrux_result({"result": {"ok": True, "execution_mode": "free"}})
    assert evidence.status == "pass"
    assert evidence.mode == sentrux_gate.FREE_TIER_MODE


def test_sentrux_normalizer_accepts_mcp_check_rules_summary_shape() -> None:
    # Ported from the deleted test_sentrux_gate.py: the MCP ``check_rules`` shape
    # with a nested ``summary`` block must normalize its quality/cycle/complexity
    # /test-gap fields onto the evidence model.
    evidence = sentrux_gate.parse_sentrux_result(
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


def test_sentrux_normalizer_accepts_cli_json_string() -> None:
    # Ported from the deleted test_sentrux_gate.py: a CLI JSON string with
    # ``success`` + ``thresholds`` normalizes correctly.
    import json

    evidence = sentrux_gate.parse_sentrux_result(
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


# ---------------------------------------------------------------------------
# test_engineer_scope_guard
# ---------------------------------------------------------------------------


def test_test_engineer_guard_skips_other_personas() -> None:
    report = test_engineer_scope_guard.check(_inputs(persona="implementer", changed_files=["src/scistudio/core/x.py"]))
    assert report.status is AuditStatus.PASS
    assert report.summary["applies"] is False


def test_test_engineer_guard_allows_test_paths() -> None:
    report = test_engineer_scope_guard.check(_inputs(persona="test_engineer", changed_files=["tests/qa/test_x.py"]))
    assert report.status is AuditStatus.PASS


def test_test_engineer_guard_blocks_production_code() -> None:
    report = test_engineer_scope_guard.check(
        _inputs(persona="test_engineer", changed_files=["src/scistudio/core/x.py"])
    )
    assert report.blocks_merge
    assert "test_engineer_scope_guard.blocked-path" in _rule_ids(report)


def test_test_engineer_guard_allows_scoped_qa_tooling() -> None:
    report = test_engineer_scope_guard.check(
        _inputs(
            persona="test_engineer",
            changed_files=["src/scistudio/qa/governance/x.py"],
            effective_include=["src/scistudio/qa/**"],
        )
    )
    assert report.status is AuditStatus.PASS


# ---------------------------------------------------------------------------
# docs_landing
# ---------------------------------------------------------------------------


def test_docs_landing_passes_for_non_governed_change() -> None:
    report = docs_landing.check(_inputs(surfaces={"implementation": []}))
    assert report.status is AuditStatus.PASS


def test_docs_landing_blocks_governed_change_without_evidence() -> None:
    report = docs_landing.check(_inputs(surfaces={"implementation": ["src/scistudio/x.py"]}))
    assert report.blocks_merge
    assert "docs_landing.missing-landing" in _rule_ids(report)


def test_docs_landing_passes_with_verified_docs() -> None:
    report = docs_landing.check(
        _inputs(
            surfaces={"implementation": ["src/scistudio/x.py"]},
            verified_docs_paths=["docs/specs/x.md"],
        )
    )
    assert report.status is AuditStatus.PASS


def test_docs_landing_passes_with_docs_na() -> None:
    report = docs_landing.check(
        _inputs(
            surfaces={"implementation": ["src/scistudio/x.py"]},
            extras={"docs_na": ["implementation: internal bugfix"]},
        )
    )
    assert report.status is AuditStatus.PASS


# ---------------------------------------------------------------------------
# issue_link
# ---------------------------------------------------------------------------


def test_issue_link_blocks_when_no_issue() -> None:
    report = issue_link.check(_inputs(issues=[]))
    assert report.blocks_merge
    assert "issue_link.missing" in _rule_ids(report)


def test_issue_link_passes_with_valid_issue_and_no_pr_body() -> None:
    report = issue_link.check(_inputs(issues=[IssueRef(number=1509, url="https://github.com/o/r/issues/1509")]))
    assert report.status is AuditStatus.PASS


def test_issue_link_blocks_missing_closing_keyword() -> None:
    report = issue_link.check(
        _inputs(
            issues=[IssueRef(number=1509, url="https://github.com/o/r/issues/1509")],
            pr_body="Some body without a closing keyword.",
        )
    )
    assert report.blocks_merge
    assert "issue_link.missing-closing-keyword" in _rule_ids(report)


def test_issue_link_passes_with_closing_keyword() -> None:
    report = issue_link.check(
        _inputs(
            issues=[IssueRef(number=1509, url="https://github.com/o/r/issues/1509")],
            pr_body="Closes #1509",
        )
    )
    assert report.status is AuditStatus.PASS


def test_issue_link_blocks_url_number_mismatch() -> None:
    report = issue_link.check(_inputs(issues=[IssueRef(number=1509, url="https://github.com/o/r/issues/42")]))
    assert "issue_link.url-number-mismatch" in _rule_ids(report)


# ---------------------------------------------------------------------------
# persona_policy
# ---------------------------------------------------------------------------


def test_persona_policy_passes_for_supported_persona() -> None:
    report = persona_policy.check(_inputs(persona="implementer", runtime="claude-code"))
    assert report.status is AuditStatus.PASS


def test_persona_policy_allows_live_implementer() -> None:
    # §4.2: live_implementer is added to the allowed personas.
    report = persona_policy.check(_inputs(persona="live_implementer", runtime="claude-code"))
    assert "persona_policy.unsupported-persona" not in _rule_ids(report)


@pytest.mark.parametrize("runtime", ["claude-code", "codex", "gemini", "agents"])
def test_persona_policy_live_implementer_pointer_resolves(runtime: str) -> None:
    # Defect 1 regression (#1509): the live-implementer skill pointer must ship
    # under every supported runtime root so a guided/live_implementer flow is no
    # longer dead-on-arrival. _inputs uses the real REPO_ROOT, so PASS proves the
    # on-disk skill pointer, persona guide, and root policy all resolve.
    report = persona_policy.check(_inputs(persona="live_implementer", runtime=runtime))
    assert report.status is AuditStatus.PASS, _rule_ids(report)
    assert "persona_policy.missing-skill-pointer" not in _rule_ids(report)


def test_persona_policy_blocks_unsupported_persona() -> None:
    report = persona_policy.check(_inputs(persona="reviewer_bot", runtime="claude-code"))
    assert report.blocks_merge
    assert "persona_policy.unsupported-persona" in _rule_ids(report)


def test_persona_policy_blocks_unsupported_runtime() -> None:
    report = persona_policy.check(_inputs(persona="implementer", runtime="mystery-runtime"))
    assert report.blocks_merge
    assert "persona_policy.unsupported-runtime-root" in _rule_ids(report)


def test_persona_policy_implementer_skill_mapping_is_fixed() -> None:
    # §4.2: the implementer skill maps to "implementer" (not the stale
    # "implementation-worker"); the on-disk pointer therefore resolves.
    assert persona_policy.REQUIRED_PERSONA_SKILLS["implementer"] == "implementer"
    report = persona_policy.check(_inputs(persona="implementer", runtime="claude-code"))
    assert "persona_policy.missing-skill-pointer" not in _rule_ids(report)


def test_guided_task_kind_is_not_rejected() -> None:
    # §4.2: guided is a valid task kind; persona_policy does not reject it.
    report = persona_policy.check(_inputs(persona="live_implementer", runtime="claude-code", task_kind="guided"))
    assert report.summary["task_kind"] == "guided"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
