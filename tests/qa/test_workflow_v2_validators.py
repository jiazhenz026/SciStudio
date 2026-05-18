"""Unit tests for Workflow v2 per-stage validators (TC-1H.2).

Each validator is tested for pass / fail (and skip where applicable),
plus declared_data shape edge cases. Aimed at ≥95% line coverage per
ADR-042 §21.6 day-one bar for new QA code.
"""

from __future__ import annotations

import pytest

from scieasy.qa.workflow.gate import StageContext
from scieasy.qa.workflow.validators.branch import BranchNameValidator
from scieasy.qa.workflow.validators.change_plan import ChangePlanShapeValidator
from scieasy.qa.workflow.validators.complete_artifacts import (
    CompleteArtifactsPlaceholder,
)
from scieasy.qa.workflow.validators.create_issue import CreateIssueShapeValidator
from scieasy.qa.workflow.validators.implement_validate import (
    ImplementValidatePlaceholder,
)
from scieasy.qa.workflow.validators.start_and_route import (
    StartAndRouteShapeValidator,
)
from scieasy.qa.workflow.validators.submit_reconcile import (
    SubmitReconcileShapeValidator,
)


def _ctx(
    stage_name: str,
    declared_data: dict,
    branch: str = "feat/issue-1145/adr-042/test",
) -> StageContext:
    return StageContext(
        task_id="20260518-test",
        stage_name=stage_name,
        repo_root="/tmp/repo",
        pr_number=None,
        branch=branch,
        declared_data=declared_data,
    )


# ─── start_and_route ────────────────────────────────────────────────────────


class TestStartAndRoute:
    def test_pass_minimal(self):
        v = StartAndRouteShapeValidator()
        r = v(_ctx("start_and_route", {"adrs": [42], "contract_change": False, "new_skills": []}))
        assert r.status == "pass"
        assert r.validator_id == "start_and_route.shape"
        assert "OK" in r.message

    def test_pass_with_skills_and_contract_change(self):
        v = StartAndRouteShapeValidator()
        r = v(
            _ctx(
                "start_and_route",
                {"adrs": [42, 43], "contract_change": True, "new_skills": ["doc-drift-guard"]},
            )
        )
        assert r.status == "pass"

    def test_fail_missing_keys(self):
        v = StartAndRouteShapeValidator()
        r = v(_ctx("start_and_route", {"adrs": [42]}))
        assert r.status == "fail"
        assert "Missing required keys" in r.message
        assert "contract_change" in r.message and "new_skills" in r.message

    def test_fail_adrs_not_list(self):
        v = StartAndRouteShapeValidator()
        r = v(_ctx("start_and_route", {"adrs": "42", "contract_change": False, "new_skills": []}))
        assert r.status == "fail"
        assert "'adrs'" in r.message

    def test_fail_adrs_non_int_element(self):
        v = StartAndRouteShapeValidator()
        r = v(
            _ctx(
                "start_and_route",
                {"adrs": [42, "43"], "contract_change": False, "new_skills": []},
            )
        )
        assert r.status == "fail"
        assert "'adrs'" in r.message

    def test_fail_contract_change_not_bool(self):
        v = StartAndRouteShapeValidator()
        r = v(
            _ctx(
                "start_and_route",
                {"adrs": [42], "contract_change": "false", "new_skills": []},
            )
        )
        assert r.status == "fail"
        assert "'contract_change'" in r.message

    def test_fail_new_skills_not_list(self):
        v = StartAndRouteShapeValidator()
        r = v(
            _ctx(
                "start_and_route",
                {"adrs": [42], "contract_change": False, "new_skills": "doc-drift-guard"},
            )
        )
        assert r.status == "fail"
        assert "'new_skills'" in r.message

    def test_fail_new_skills_non_str_element(self):
        v = StartAndRouteShapeValidator()
        r = v(
            _ctx(
                "start_and_route",
                {"adrs": [42], "contract_change": False, "new_skills": ["valid", 42]},
            )
        )
        assert r.status == "fail"
        assert "'new_skills'" in r.message

    def test_default_blocking_true(self):
        v = StartAndRouteShapeValidator()
        assert v.blocking is True
        r = v(_ctx("start_and_route", {"adrs": [42], "contract_change": False, "new_skills": []}))
        assert r.blocking is True


# ─── create_issue ───────────────────────────────────────────────────────────


class TestCreateIssue:
    def test_pass(self):
        v = CreateIssueShapeValidator()
        r = v(
            _ctx(
                "create_issue",
                {
                    "issue_number": 1145,
                    "issue_url": "https://github.com/zjzcpj/SciEasy/issues/1145",
                },
            )
        )
        assert r.status == "pass"
        assert "#1145" in r.message

    def test_fail_no_issue_number(self):
        v = CreateIssueShapeValidator()
        r = v(_ctx("create_issue", {"issue_url": "https://github.com/x/y/issues/1"}))
        assert r.status == "fail"
        assert "'issue_number'" in r.message

    def test_fail_issue_number_zero(self):
        v = CreateIssueShapeValidator()
        r = v(
            _ctx(
                "create_issue",
                {"issue_number": 0, "issue_url": "https://github.com/x/y/issues/1"},
            )
        )
        assert r.status == "fail"

    def test_fail_issue_number_negative(self):
        v = CreateIssueShapeValidator()
        r = v(
            _ctx(
                "create_issue",
                {"issue_number": -1, "issue_url": "https://github.com/x/y/issues/1"},
            )
        )
        assert r.status == "fail"

    def test_fail_bad_url(self):
        v = CreateIssueShapeValidator()
        r = v(
            _ctx(
                "create_issue",
                {"issue_number": 1, "issue_url": "https://example.com/issues/1"},
            )
        )
        assert r.status == "fail"
        assert "'issue_url'" in r.message

    def test_fail_pull_url_not_issue(self):
        # /pull/N is not /issues/N
        v = CreateIssueShapeValidator()
        r = v(
            _ctx(
                "create_issue",
                {"issue_number": 1, "issue_url": "https://github.com/x/y/pull/1"},
            )
        )
        assert r.status == "fail"


# ─── change_plan ────────────────────────────────────────────────────────────


class TestChangePlan:
    def test_pass(self):
        v = ChangePlanShapeValidator()
        r = v(
            _ctx(
                "change_plan",
                {
                    "change_plan_comment_url": "https://github.com/x/y/issues/1#issuecomment-99",
                    "files_to_modify": ["src/scieasy/qa/foo.py"],
                },
            )
        )
        assert r.status == "pass"
        assert "1 files" in r.message

    def test_fail_bad_url(self):
        v = ChangePlanShapeValidator()
        r = v(
            _ctx(
                "change_plan",
                {
                    "change_plan_comment_url": "https://example.com/comment",
                    "files_to_modify": ["a.py"],
                },
            )
        )
        assert r.status == "fail"
        assert "change_plan_comment_url" in r.message

    def test_fail_empty_files_list(self):
        v = ChangePlanShapeValidator()
        r = v(
            _ctx(
                "change_plan",
                {
                    "change_plan_comment_url": "https://github.com/x/y/issues/1#issuecomment-99",
                    "files_to_modify": [],
                },
            )
        )
        assert r.status == "fail"
        assert "files_to_modify" in r.message

    def test_fail_files_not_list(self):
        v = ChangePlanShapeValidator()
        r = v(
            _ctx(
                "change_plan",
                {
                    "change_plan_comment_url": "https://github.com/x/y/issues/1#issuecomment-99",
                    "files_to_modify": "a.py",
                },
            )
        )
        assert r.status == "fail"

    def test_fail_files_non_str_element(self):
        v = ChangePlanShapeValidator()
        r = v(
            _ctx(
                "change_plan",
                {
                    "change_plan_comment_url": "https://github.com/x/y/issues/1#issuecomment-99",
                    "files_to_modify": ["a.py", 42],
                },
            )
        )
        assert r.status == "fail"


# ─── branch ─────────────────────────────────────────────────────────────────


class TestBranch:
    @pytest.mark.parametrize(
        "name",
        [
            "feat/issue-1145/adr-042/workflow-v2-shadow",
            "fix/issue-1/ADR-035/some-bug",
            "docs/issue-99/adr-040/agents-md",
            "chore/issue-2/adr-042/registry",
            "refactor/issue-1234/ADR-001/cleanup",
            "test/issue-5/adr-042/coverage-bump",
        ],
    )
    def test_pass_valid_names(self, name):
        v = BranchNameValidator()
        r = v(_ctx("branch", {}, branch=name))
        assert r.status == "pass", f"expected pass for {name}, got {r.message}"

    @pytest.mark.parametrize(
        "name",
        [
            "main",
            "feature/foo",  # 'feature' not in allowed type set
            "feat/issue-1/foo",  # missing /adr-NN
            "feat/issue-1/adr-042",  # missing slug
            "feat/issue-N/adr-042/slug",  # non-numeric issue
            "feat/issue-1/adr042/slug",  # missing dash in adr
            "feat/issue-1/adr-42/UPPER",  # slug must be lower-kebab
            "",
        ],
    )
    def test_fail_invalid_names(self, name):
        v = BranchNameValidator()
        r = v(_ctx("branch", {}, branch=name))
        assert r.status == "fail", f"expected fail for {name!r}, got {r.message}"
        assert "branch name must match" in r.message


# ─── implement_validate ─────────────────────────────────────────────────────


class TestImplementValidate:
    def test_returns_skip(self):
        v = ImplementValidatePlaceholder()
        r = v(_ctx("implement_validate", {}))
        assert r.status == "skip"
        assert r.validator_id == "implement_validate.full_audit"
        assert "TC-1B.7" in r.message

    def test_non_blocking(self):
        v = ImplementValidatePlaceholder()
        assert v.blocking is False
        r = v(_ctx("implement_validate", {}))
        assert r.blocking is False


# ─── complete_artifacts ─────────────────────────────────────────────────────


class TestCompleteArtifacts:
    def test_returns_skip(self):
        v = CompleteArtifactsPlaceholder()
        r = v(_ctx("complete_artifacts", {}))
        assert r.status == "skip"
        assert r.validator_id == "complete_artifacts.check"

    def test_non_blocking(self):
        v = CompleteArtifactsPlaceholder()
        assert v.blocking is False


# ─── submit_reconcile ───────────────────────────────────────────────────────


class TestSubmitReconcile:
    def test_pass(self):
        v = SubmitReconcileShapeValidator()
        r = v(
            _ctx(
                "submit_reconcile",
                {"pr_number": 999, "pr_url": "https://github.com/zjzcpj/SciEasy/pull/999"},
            )
        )
        assert r.status == "pass"
        assert "#999" in r.message

    def test_fail_no_pr_number(self):
        v = SubmitReconcileShapeValidator()
        r = v(
            _ctx(
                "submit_reconcile",
                {"pr_url": "https://github.com/x/y/pull/1"},
            )
        )
        assert r.status == "fail"

    def test_fail_zero_pr_number(self):
        v = SubmitReconcileShapeValidator()
        r = v(
            _ctx(
                "submit_reconcile",
                {"pr_number": 0, "pr_url": "https://github.com/x/y/pull/1"},
            )
        )
        assert r.status == "fail"

    def test_fail_bad_pr_url(self):
        v = SubmitReconcileShapeValidator()
        r = v(
            _ctx(
                "submit_reconcile",
                {"pr_number": 1, "pr_url": "https://github.com/x/y/issues/1"},
            )
        )
        assert r.status == "fail"
        assert "pr_url" in r.message
