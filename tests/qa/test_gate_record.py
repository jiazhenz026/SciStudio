from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scistudio.qa.governance.gate_record import (
    CANONICAL_STAGE_ORDER,
    CheckEvidence,
    GateRecord,
    GateStage,
    SentruxEvidence,
    _discover_gate_record,
    _is_governance_path,
    _is_test_path,
    check_commit_msg,
    check_pr_ready,
    check_pre_commit,
    check_pre_push,
    main,
    validate_gate_record,
)


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema_version": "1",
        "record_path": ".workflow/records/1267-gate-record-core.json",
        "task_id": "1267-gate-record-core",
        "task_kind": "feature",
        "branch": "feat/issue-1267/gate-record-core",
        "owner_directive": "Implement ADR-042 Addendum 1 Track B.",
        "issues": [{"number": 1267, "url": "https://github.com/zjzcpj/SciStudio/issues/1267"}],
        "scope": {
            "include": [
                "src/scistudio/qa/governance/gate_record.py",
                "src/scistudio/qa/governance/__init__.py",
                ".workflow/**",
                "tests/qa/test_gate_record*.py",
            ],
            "exclude": ["docs/adr/ADR-042.md"],
        },
        "governance_touch": True,
        "stages": [{"stage": stage.value, "status": "done"} for stage in CANONICAL_STAGE_ORDER],
        "planned_files": ["src/scistudio/qa/governance/gate_record.py"],
        "changed_test_paths": ["tests/qa/test_gate_record.py"],
        "admin_labels": [{"name": "admin-approved:core-change", "applied_by": "@owner"}],
        "required_checks": ["ruff", "pytest", "full_audit", "sentrux"],
        "check_results": [
            {
                "name": "pytest",
                "command_or_tool": "pytest tests/qa/test_gate_record.py",
                "status": "pass",
                "exit_code": 0,
            }
        ],
        "sentrux": {
            "mode": "free-tier",
            "command_or_tool": "sentrux check .",
            "status": "pass",
            "rules_checked": 3,
            "total_rules_defined": 15,
            "pro_required": False,
        },
        "full_audit": {
            "command": "python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json",
            "status": "pass",
            "exit_code": 0,
            "output_path": "docs/audit/full-audit-latest.json",
            "blocks_merge": False,
        },
    }
    record.update(overrides)
    return record


def test_gate_record_accepts_canonical_six_stage_model() -> None:
    record = GateRecord.model_validate(_record())

    assert record.stages[0].stage is GateStage.SCOPE_AND_ISSUE
    assert record.stages[-1].stage is GateStage.COMMIT_AND_SUBMIT_PR
    assert record.admin_labels[0].name == "admin-approved:core-change"


def test_gate_record_rejects_missing_or_reordered_stage() -> None:
    data = _record(stages=[{"stage": GateStage.PLAN.value, "status": "done"}])

    try:
        GateRecord.model_validate(data)
    except ValidationError as exc:
        assert "six ADR-042 Addendum 1 stages" in str(exc)
    else:  # pragma: no cover - explicit assertion path
        raise AssertionError("GateRecord accepted an invalid stage sequence")


def test_sentrux_evidence_rejects_pro_required_claims() -> None:
    with pytest.raises(ValidationError, match="pro_required"):
        SentruxEvidence.model_validate(
            {
                "mode": "free-tier",
                "command_or_tool": "sentrux check .",
                "status": "pass",
                "pro_required": True,
            }
        )


def test_sentrux_evidence_rejects_impossible_rule_counts() -> None:
    with pytest.raises(ValidationError, match="rules_checked cannot exceed total_rules_defined"):
        SentruxEvidence.model_validate(
            {
                "mode": "free-tier",
                "command_or_tool": "sentrux check .",
                "status": "pass",
                "rules_checked": 4,
                "total_rules_defined": 3,
                "pro_required": False,
            }
        )


def test_full_audit_known_debt_is_allowed_but_unclassified_failures_block() -> None:
    known_debt = _record(
        full_audit={
            "command": "python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json",
            "status": "fail",
            "exit_code": 1,
            "output_path": "docs/audit/full-audit-latest.json",
            "blocks_merge": True,
            "known_debt": ["frontmatter legacy backlog"],
        }
    )
    assert not validate_gate_record(known_debt).blocks_merge

    unclassified = _record(
        full_audit={
            "command": "python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json",
            "status": "fail",
            "exit_code": 1,
            "output_path": "docs/audit/full-audit-latest.json",
            "blocks_merge": True,
            "unclassified_failures": ["new doc drift"],
        }
    )
    report = validate_gate_record(unclassified)
    assert report.blocks_merge
    assert {finding.rule_id for finding in report.findings} == {
        "gate-record.full-audit.unclassified-failures",
        "gate-record.full-audit.unclassified-fail-status",
    }


def test_check_evidence_rejects_passing_nonzero_exit_code() -> None:
    with pytest.raises(ValidationError, match="passing checks cannot record a non-zero exit_code"):
        CheckEvidence.model_validate(
            {
                "name": "ruff",
                "command_or_tool": "ruff check .",
                "status": "pass",
                "exit_code": 1,
            }
        )


def test_governance_path_excludes_gate_record_evidence_files() -> None:
    """#1340: gate-record evidence files under ``.workflow/records/**`` are
    written by every AI-authored PR by design. They live under ``.workflow/``
    but are not governance policy, so they must not trigger the governance
    touch rule on their own. Real governance touches (gate code, hooks, CI)
    still count.
    """

    assert _is_governance_path(".workflow/active") is True
    assert _is_governance_path(".workflow/hooks/pre-commit") is True
    assert _is_governance_path(".github/workflows/workflow-gate.yml") is True
    assert _is_governance_path(".pre-commit-config.yaml") is True
    assert _is_governance_path("docs/adr/ADR-042.md") is True
    assert _is_governance_path("docs/adr/ADR-042-addendum1.md") is True
    assert _is_governance_path("src/scistudio/qa/governance/gate_record.py") is True

    assert _is_governance_path(".workflow/records/1340-wire-vulture.json") is False
    assert _is_governance_path(".workflow/records/some-future.json") is False

    assert _is_governance_path("src/scistudio/engine/scheduler.py") is False
    assert _is_governance_path("CHANGELOG.md") is False


def test_gate_record_without_governance_touch_accepts_records_only_change() -> None:
    """A PR whose only ``.workflow/**`` change is its own gate-record evidence
    file must validate cleanly with ``governance_touch=false`` (#1340).
    """

    record = _record(
        governance_touch=False,
        scope={"include": ["src/scistudio/engine/scheduler.py", ".workflow/records/**"], "exclude": []},
    )
    report = validate_gate_record(
        record,
        changed_files=[
            "src/scistudio/engine/scheduler.py",
            ".workflow/records/1267-gate-record-core.json",
        ],
    )

    governance_findings = [f for f in report.findings if f.rule_id == "gate-record.governance-touch.missing"]
    assert governance_findings == []


def test_amend_cli_flips_governance_touch_to_true(tmp_path: Path) -> None:
    """#1340: amend --governance-touch flips the record's governance_touch
    flag to True. This closes the CLI gap where start was the only command
    that could set governance_touch, forcing direct JSON edits when an
    in-flight gate record legitimately needed to certify a governance touch.
    """

    record_path = tmp_path / ".workflow" / "records" / "1340-amend-governance-touch.json"

    assert (
        main(
            [
                "start",
                "--repo-root",
                str(tmp_path),
                "--issue",
                "1340",
                "--slug",
                "amend governance touch",
                "--task-kind",
                "feature",
                "--branch",
                "feat/issue-1340/amend-governance-touch",
                "--owner-directive",
                "test the new amend --governance-touch flag",
                "--include",
                "src/scistudio/qa/governance/gate_record.py",
                "--record",
                str(record_path),
            ]
        )
        == 0
    )

    record_before = json.loads(record_path.read_text(encoding="utf-8"))
    assert record_before["governance_touch"] is False

    assert (
        main(
            [
                "amend",
                "--record",
                str(record_path),
                "--reason",
                "extend scope to include a governance code edit not foreseen at start",
                "--include",
                "src/scistudio/qa/governance/mod_guard.py",
                "--governance-touch",
            ]
        )
        == 0
    )

    record_after = json.loads(record_path.read_text(encoding="utf-8"))
    assert record_after["governance_touch"] is True
    assert any(
        amendment.get("reason", "").startswith("extend scope to include a governance code edit")
        for amendment in record_after["amendments"]
    )


def test_amend_without_governance_touch_flag_preserves_existing_value(tmp_path: Path) -> None:
    """A plain ``amend`` call without ``--governance-touch`` must not toggle
    governance_touch. The flag is opt-in: silence means leave the existing
    value alone.
    """

    record_path = tmp_path / ".workflow" / "records" / "1340-amend-preserve.json"
    assert (
        main(
            [
                "start",
                "--repo-root",
                str(tmp_path),
                "--issue",
                "1340",
                "--slug",
                "amend preserve",
                "--task-kind",
                "feature",
                "--branch",
                "feat/issue-1340/amend-preserve",
                "--owner-directive",
                "directive",
                "--include",
                "src/scistudio/qa/governance/**",
                "--governance-touch",
                "--record",
                str(record_path),
            ]
        )
        == 0
    )

    assert json.loads(record_path.read_text(encoding="utf-8"))["governance_touch"] is True

    assert (
        main(
            [
                "amend",
                "--record",
                str(record_path),
                "--reason",
                "plain scope amendment, no governance_touch change",
                "--include",
                "tests/qa/test_extra.py",
            ]
        )
        == 0
    )

    assert json.loads(record_path.read_text(encoding="utf-8"))["governance_touch"] is True


def test_gate_record_still_requires_governance_touch_for_real_governance_files() -> None:
    """Editing actual governance code (gate_record.py, CI workflows) must
    still require ``governance_touch=true``. This is the inverse of the
    records-only carve-out — the rule fix in #1340 must not weaken the real
    governance protection.
    """

    record = _record(
        governance_touch=False,
        scope={"include": ["src/scistudio/qa/governance/**", ".workflow/records/**"], "exclude": []},
    )
    report = validate_gate_record(
        record,
        changed_files=[
            "src/scistudio/qa/governance/gate_record.py",
            ".workflow/records/1267-gate-record-core.json",
        ],
    )

    governance_findings = [f for f in report.findings if f.rule_id == "gate-record.governance-touch.missing"]
    assert len(governance_findings) == 1
    assert governance_findings[0].file == "src/scistudio/qa/governance/gate_record.py"


def test_pr_ready_does_not_require_commit_and_submit_pr_stage_done() -> None:
    """#1340: ``pr-ready`` runs BEFORE ``gh pr create``. The
    ``commit_and_submit_pr`` stage is set by ``finalize``, which needs a
    commit SHA and PR URL. Requiring that stage done at pr-ready time would
    be a chicken-and-egg: no PR exists yet, so no finalize, so the stage
    can never be done, so pr-ready can never pass on a fresh branch.
    """

    record_data = _record()
    pending_stages: list[dict[str, object]] = []
    for stage in record_data["stages"]:
        copy = dict(stage)
        if stage["stage"] == GateStage.COMMIT_AND_SUBMIT_PR.value:
            copy["status"] = "pending"
        pending_stages.append(copy)
    record_data["stages"] = pending_stages

    pr_body = "## Summary\n- thing\n\nGate record: .workflow/records/1267-gate-record-core.json\n\nCloses #1267\n"
    report = check_pr_ready_via_function = validate_gate_record(
        record_data,
        changed_files=["src/scistudio/qa/governance/gate_record.py"],
        pr_body=pr_body,
        require_pr_body=True,
        require_post_pr_stages=False,
    )

    stage_findings = [f for f in report.findings if f.rule_id == "gate-record.stage.not-done"]
    assert stage_findings == []
    del check_pr_ready_via_function


def test_ci_still_requires_commit_and_submit_pr_stage_done() -> None:
    """The chicken-and-egg carve-out is opt-in. CI (which runs after the PR
    exists and after ``finalize`` should have been called) keeps requiring
    every stage done — including ``commit_and_submit_pr``.
    """

    record_data = _record()
    pending_stages: list[dict[str, object]] = []
    for stage in record_data["stages"]:
        copy = dict(stage)
        if stage["stage"] == GateStage.COMMIT_AND_SUBMIT_PR.value:
            copy["status"] = "pending"
        pending_stages.append(copy)
    record_data["stages"] = pending_stages

    pr_body = "## Summary\n- thing\n\nGate record: .workflow/records/1267-gate-record-core.json\n\nCloses #1267\n"
    report = validate_gate_record(
        record_data,
        changed_files=["src/scistudio/qa/governance/gate_record.py"],
        pr_body=pr_body,
        require_pr_body=True,
    )

    stage_findings = [
        f
        for f in report.findings
        if f.rule_id == "gate-record.stage.not-done" and f.evidence.get("stage") == GateStage.COMMIT_AND_SUBMIT_PR.value
    ]
    assert len(stage_findings) == 1, "CI must still require commit_and_submit_pr to be done"


def test_pre_push_does_not_require_commit_and_submit_pr_stage_done() -> None:
    """``pre-push`` runs BEFORE ``git push``. The PR doesn't exist yet; the
    commit_and_submit_pr stage cannot be done. Same carve-out as pr-ready.
    """

    record_data = _record()
    pending_stages: list[dict[str, object]] = []
    for stage in record_data["stages"]:
        copy = dict(stage)
        if stage["stage"] == GateStage.COMMIT_AND_SUBMIT_PR.value:
            copy["status"] = "pending"
        pending_stages.append(copy)
    record_data["stages"] = pending_stages

    report = validate_gate_record(
        record_data,
        changed_files=["src/scistudio/qa/governance/gate_record.py"],
        require_post_pr_stages=False,
    )

    stage_findings = [f for f in report.findings if f.rule_id == "gate-record.stage.not-done"]
    assert stage_findings == []


def _write_record_file(path: Path, *, task_kind: str, task_id: str = "test") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"task_kind": task_kind, "task_id": task_id}),
        encoding="utf-8",
    )
    return path


def test_discover_gate_record_returns_single_record_unchanged(tmp_path: Path) -> None:
    record = _write_record_file(
        tmp_path / ".workflow" / "records" / "1340-wire-vulture.json",
        task_kind="feature",
    )

    resolved = _discover_gate_record(tmp_path, [".workflow/records/1340-wire-vulture.json"])

    assert resolved == record


def test_discover_gate_record_picks_manager_record_on_umbrella(tmp_path: Path) -> None:
    """#1340: umbrella PRs created by the manager persona accumulate sub-PR
    records in their diff. The umbrella's own record has ``task_kind: manager``;
    sub-PR records have implementation task kinds (feature/bugfix/etc).
    Discovery must pick the manager record as the primary.
    """

    umbrella = _write_record_file(
        tmp_path / ".workflow" / "records" / "1266-umbrella.json",
        task_kind="manager",
        task_id="1266-umbrella",
    )
    _write_record_file(
        tmp_path / ".workflow" / "records" / "1267-sub-a.json",
        task_kind="feature",
        task_id="1267-sub-a",
    )
    _write_record_file(
        tmp_path / ".workflow" / "records" / "1268-sub-b.json",
        task_kind="bugfix",
        task_id="1268-sub-b",
    )

    resolved = _discover_gate_record(
        tmp_path,
        [
            ".workflow/records/1267-sub-a.json",
            ".workflow/records/1266-umbrella.json",
            ".workflow/records/1268-sub-b.json",
        ],
    )

    assert resolved == umbrella


def test_discover_gate_record_returns_none_for_multiple_manager_records(tmp_path: Path) -> None:
    """Defensive case: if a PR somehow carries multiple manager records, the
    umbrella heuristic does not apply and discovery falls back to the
    single-record-on-disk path (which returns None when more than one exists).
    """

    _write_record_file(
        tmp_path / ".workflow" / "records" / "100-m1.json",
        task_kind="manager",
    )
    _write_record_file(
        tmp_path / ".workflow" / "records" / "200-m2.json",
        task_kind="manager",
    )

    resolved = _discover_gate_record(
        tmp_path,
        [".workflow/records/100-m1.json", ".workflow/records/200-m2.json"],
    )

    assert resolved is None


def test_discover_gate_record_returns_none_for_multiple_non_manager_records(tmp_path: Path) -> None:
    """If a PR carries multiple records but none are manager-kind, this is
    not the umbrella case — fail closed (return None so the caller emits the
    standard 'exactly one gate record' error).
    """

    _write_record_file(
        tmp_path / ".workflow" / "records" / "100-feature.json",
        task_kind="feature",
    )
    _write_record_file(
        tmp_path / ".workflow" / "records" / "200-bugfix.json",
        task_kind="bugfix",
    )

    resolved = _discover_gate_record(
        tmp_path,
        [".workflow/records/100-feature.json", ".workflow/records/200-bugfix.json"],
    )

    assert resolved is None


def test_check_commit_msg_requires_adr042_trailers() -> None:
    report = check_commit_msg(
        """feat(#1267): add gate record core

Gate-Record: .workflow/records/1267-gate-record-core.json
Task-Kind: feature
Issue: #1267
Assisted-by: Codex:gpt-5
"""
    )
    assert not report.blocks_merge

    missing = check_commit_msg("feat: no trailers\n")
    assert missing.blocks_merge
    assert "Gate-Record" in {finding.message.rsplit(" ", 1)[-1] for finding in missing.findings}


def test_ai_facing_cli_records_canonical_workflow(tmp_path: Path) -> None:
    record_path = tmp_path / ".workflow" / "records" / "1267-gate-record-core.json"

    assert (
        main(
            [
                "start",
                "--repo-root",
                str(tmp_path),
                "--issue",
                "1267",
                "--issue-url",
                "https://github.com/zjzcpj/SciStudio/issues/1267",
                "--slug",
                "Gate Record Core",
                "--task-kind",
                "feature",
                "--branch",
                "feat/issue-1267/gate-record-core",
                "--owner-directive",
                "Implement ADR-042 Addendum 1 Track B.",
                "--include",
                "src/scistudio/qa/governance/**",
                "--include",
                "tests/qa/test_gate_record*.py",
                "--governance-touch",
                "--record",
                str(record_path),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "plan",
                "--record",
                str(record_path),
                "--files",
                "src/scistudio/qa/governance/gate_record.py",
                "--checks",
                "ruff check .",
                "--tests",
                "tests/qa/test_gate_record.py",
                "--docs",
                "docs/specs/adr-042-gate-record-sentrux-workflow.md",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "docs",
                "--record",
                str(record_path),
                "--updated",
                "docs/specs/adr-042-gate-record-sentrux-workflow.md",
                "--updated",
                "docs/planning/adr-042-addendum1-implementation-checklist.md",
                "--na",
                "changelog=Gate governance migration keeps CHANGELOG tracked.",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "amend",
                "--record",
                str(record_path),
                "--reason",
                "Implementation confirmed within planned scope.",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "check",
                "--record",
                str(record_path),
                "--name",
                "pytest",
                "--command",
                "pytest tests/qa/test_gate_record.py --timeout=60",
                "--status",
                "pass",
                "--exit-code",
                "0",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "check",
                "--record",
                str(record_path),
                "--full-audit",
                "--command",
                "python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json",
                "--status",
                "pass",
                "--exit-code",
                "0",
                "--output-path",
                "docs/audit/full-audit-latest.json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "sentrux",
                "--record",
                str(record_path),
                "--command-or-tool",
                "sentrux mcp check-rules",
                "--status",
                "pass",
                "--mode",
                "free-tier",
                "--rules-checked",
                "3",
                "--total-rules-defined",
                "15",
                "--threshold",
                "max_cycles=0",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "finalize",
                "--record",
                str(record_path),
                "--commit",
                "abc1234",
                "--pr-number",
                "1276",
                "--pr",
                "https://github.com/zjzcpj/SciStudio/pull/1276",
                "--closes",
                "#1267",
            ]
        )
        == 0
    )

    payload = json.loads(record_path.read_text(encoding="utf-8"))
    record = GateRecord.model_validate(payload)
    assert [stage.status for stage in record.stages] == ["done", "done", "done", "done", "done", "done"]
    assert record.record_path == ".workflow/records/1267-gate-record-core.json"
    assert record.full_audit is not None
    assert record.sentrux is not None
    assert record.commit is not None
    assert record.docs_landing["docs"]["paths"] == ["docs/specs/adr-042-gate-record-sentrux-workflow.md"]
    assert record.docs_landing["checklist"]["paths"] == ["docs/planning/adr-042-addendum1-implementation-checklist.md"]
    assert record.docs_landing["changelog"]["not_applicable"] is True


def test_start_cli_accepts_hotfix_task_kind(tmp_path: Path) -> None:
    record_path = tmp_path / ".workflow" / "records" / "1300-hotfix-crash.json"

    assert (
        main(
            [
                "start",
                "--repo-root",
                str(tmp_path),
                "--issue",
                "1300",
                "--slug",
                "hotfix crash",
                "--task-kind",
                "hotfix",
                "--branch",
                "hotfix/crash",
                "--owner-directive",
                "Retroactively record the completed hotfix gate.",
                "--include",
                "src/scistudio/runtime/**",
                "--include",
                "tests/**",
                "--record",
                str(record_path),
            ]
        )
        == 0
    )

    record = GateRecord.model_validate(json.loads(record_path.read_text(encoding="utf-8")))
    assert record.task_kind == "hotfix"
    assert record.branch == "hotfix/crash"


def test_pre_commit_is_lightweight_until_final_gate(tmp_path: Path) -> None:
    missing_record = check_pre_commit(tmp_path, staged_files=["src/scistudio/example.py"])
    assert not missing_record.blocks_merge
    assert missing_record.summary["skipped"] == "no gate record present yet; final push/PR/CI gate remains required"

    data = _record(
        full_audit=None,
        sentrux=None,
        changed_test_paths=[],
        scope={"include": ["src/scistudio/**"], "exclude": []},
    )
    record_path = tmp_path / ".workflow" / "records" / "1267-gate-record-core.json"
    record_path.parent.mkdir(parents=True)
    record_path.write_text(json.dumps(data), encoding="utf-8")

    report = check_pre_commit(tmp_path, gate_record=record_path, staged_files=["src/scistudio/example.py"])
    assert not report.blocks_merge

    outside_scope = check_pre_commit(tmp_path, gate_record=record_path, staged_files=["docs/adr/ADR-042.md"])
    assert outside_scope.blocks_merge
    assert "gate-record.scope.outside-include" in {finding.rule_id for finding in outside_scope.findings}


@pytest.mark.parametrize(
    "label",
    [
        "human-authored",
        "admin-approved:ai-override",
        "admin-approved:core-change",
        "admin-approved:merge",
    ],
)
def test_override_labels_bypass_local_intermediate_hooks(tmp_path: Path, label: str) -> None:
    pre_commit = check_pre_commit(
        tmp_path,
        staged_files=["docs/adr/ADR-042.md"],
        bypass_labels=[label],
    )
    commit_msg = check_commit_msg("fix: missing trailers", bypass_labels=[label])
    pre_push = check_pre_push(tmp_path, bypass_labels=[label])
    pr_ready = check_pr_ready(tmp_path, pr_body="", pr_labels=[label])

    for report in (pre_commit, commit_msg, pre_push, pr_ready):
        assert not report.blocks_merge
        assert report.summary["bypass_labels"] == [label]


def test_invalid_override_label_does_not_bypass_local_hooks(tmp_path: Path) -> None:
    report = check_pr_ready(tmp_path, pr_body="", pr_labels=["admin-approved-core-change"])

    assert report.blocks_merge
    assert "gate-record.override-label.invalid" in {finding.rule_id for finding in report.findings}


class TestIsTestPathPytestConventions:
    """Pre-#1389 behaviour: pytest conventions must keep classifying correctly."""

    @pytest.mark.parametrize(
        "path",
        [
            "tests/qa/test_gate_record.py",
            "tests/api/test_filesystem.py",
            "tests/blocks/code/test_exchange.py",
            "src/scistudio/utils/tests/test_paths.py",
            "src/scistudio/foo/test_bar.py",
            "src/scistudio/foo/bar_test.py",
        ],
    )
    def test_pytest_conventions_classify_as_test(self, path: str) -> None:
        assert _is_test_path(path) is True


class TestIsTestPathVitestRecognition:
    """#1389: vitest co-located test files must classify as test paths.

    Pre-fix behaviour treated `frontend/src/components/Foo.test.tsx` as an
    implementation file with no test change, forcing vitest-only PRs to
    either restructure tests or burn an `admin-approved:ai-override` label
    (PRs #1383, #1299, #1313, #1320). The classifier now recognises the
    canonical vitest filename suffixes and the `__tests__/` directory
    convention.
    """

    @pytest.mark.parametrize(
        "path",
        [
            "frontend/src/components/PortEditorTable.test.tsx",
            "frontend/src/components/PortEditorTable.test.ts",
            "frontend/src/api/capabilities.test.tsx",
            "frontend/src/hooks/useSSE.spec.tsx",
            "frontend/src/hooks/useSSE.spec.ts",
            "frontend/src/utils/format.test.js",
            "frontend/src/utils/format.spec.jsx",
        ],
    )
    def test_vitest_filename_suffixes_classify_as_test(self, path: str) -> None:
        assert _is_test_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "frontend/src/__tests__/LossySaveWarning.test.tsx",
            "frontend/src/components/__tests__/foo.tsx",
            "packages/scistudio-blocks-imaging/__tests__/load.test.tsx",
        ],
    )
    def test_underscore_tests_dir_classifies_as_test(self, path: str) -> None:
        assert _is_test_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            # Codex P2 from PR #1396: top-level `__tests__/` directory must
            # classify even without a leading slash. Pre-fix `/__tests__/`
            # substring check rejected these.
            "__tests__/foo.tsx",
            "__tests__/nested/bar.test.tsx",
        ],
    )
    def test_top_level_underscore_tests_dir_classifies_as_test(self, path: str) -> None:
        assert _is_test_path(path) is True


class TestIsTestPathImplementationStays:
    """Regression: implementation files must NOT be misclassified as tests."""

    @pytest.mark.parametrize(
        "path",
        [
            "frontend/src/components/PortEditorTable.tsx",
            "frontend/src/api/capabilities.ts",
            "src/scistudio/qa/governance/gate_record.py",
            "packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/load_image.py",
            "scripts/scistudio_pr_create.py",
            "docs/adr/ADR-042.md",
            ".workflow/records/1267-gate-record-core.json",
            "frontend/src/components/PortEditorTableHelper.ts",
        ],
    )
    def test_non_test_paths_classify_as_non_test(self, path: str) -> None:
        assert _is_test_path(path) is False


class TestVitestChangedTestPathAccepted:
    """End-to-end: GateRecord schema accepts vitest path in changed_test_paths."""

    def test_schema_accepts_vitest_co_located_test(self) -> None:
        payload = _record(
            scope={
                "include": [
                    "frontend/src/components/PortEditorTable.tsx",
                    "frontend/src/components/PortEditorTable.test.tsx",
                ],
                "exclude": [],
            },
            changed_test_paths=["frontend/src/components/PortEditorTable.test.tsx"],
        )
        record = GateRecord.model_validate(payload)
        assert record.changed_test_paths == ["frontend/src/components/PortEditorTable.test.tsx"]

    def test_schema_still_rejects_non_test_path_in_changed_test_paths(self) -> None:
        payload = _record(
            changed_test_paths=["frontend/src/components/PortEditorTable.tsx"],
        )
        with pytest.raises(ValidationError, match="non-test"):
            GateRecord.model_validate(payload)
