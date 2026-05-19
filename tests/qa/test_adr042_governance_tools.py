from datetime import UTC, datetime
from pathlib import Path

from scieasy.qa.audit.codemod_lint import check_codemod_lint
from scieasy.qa.audit.complete_artifacts import check_complete_artifacts
from scieasy.qa.governance.core_change_guard import check_core_change
from scieasy.qa.governance.human_bypass_guard import check_human_bypass
from scieasy.qa.governance.issue_link import IssueQuery, resolve_or_create
from scieasy.qa.governance.local_gate import (
    ActorPermission,
    AuthorizationSignal,
    GateScope,
    GateSession,
    IssueRecord,
    PullRequestMetadata,
    check_commit_msg,
    check_pre_commit,
)
from scieasy.qa.governance.persona_policy import check_persona_policy
from scieasy.qa.governance.pr_merge_guard import check_pr_merge


def _session(tmp_path: Path) -> GateSession:
    return GateSession(
        session_id="s1",
        task_kind="manager",
        branch="main",
        owner_directive="test",
        scope=GateScope(include=["docs/**"]),
        issues=[],
        persona="manager",
        runtime="codex",
    )


def test_commit_msg_requires_ai_trailers() -> None:
    report = check_commit_msg("ci: test\n")
    assert report.status == "failed"
    assert {finding.subject for finding in report.findings} >= {"Gate-Session", "Task-Kind", "Issue", "Assisted-by"}


def test_local_gate_fails_missing_issue_and_docs_landing(tmp_path: Path) -> None:
    # Check directly through staged fixture without relying on a git index.
    report = check_pre_commit(tmp_path, staged=[Path("docs/file.md")], session_id="missing")
    assert report.status == "failed"
    assert any(finding.id == "local-gate-missing-session" for finding in report.findings)
    session_report = check_pre_commit.__globals__["build_report"](
        tool="noop",
        repo_root=tmp_path,
        findings=[],
    )
    assert session_report.status == "passed"


class _Client:
    def __init__(self, matches):
        self.matches = matches
        self.created = False

    def search_issues(self, query):
        return self.matches

    def create_issue(self, query):
        self.created = True
        return self.matches[0]


def test_issue_link_prefers_existing_issue() -> None:
    issue = IssueRecord(number=1, url="https://example.test/1", source="existing", closes=True)
    client = _Client([issue])
    record = resolve_or_create(IssueQuery(repo="o/r", title="t", body="b"), client=client, create_if_missing=True)
    assert record.number == 1
    assert client.created is False


def test_persona_policy_rejects_unsupported_persona(tmp_path: Path) -> None:
    session = _session(tmp_path).model_copy(update={"persona": "invalid"})
    report = check_persona_policy(repo_root=tmp_path, session=session)
    assert report.status == "failed"
    assert any(finding.id == "persona-policy-unsupported" for finding in report.findings)


def test_human_bypass_requires_authorized_actor() -> None:
    pr = PullRequestMetadata(
        repo="o/r",
        number=1,
        head_sha="abc",
        base_ref="main",
        head_ref="branch",
        labels=["human-authored"],
        actors=[ActorPermission(login="guest", permission="read")],
    )
    report = check_human_bypass(pr)
    assert report.status == "failed"


def test_human_bypass_accepts_maintainer_label_signal() -> None:
    actor = ActorPermission(login="maintainer", permission="write")
    pr = PullRequestMetadata(
        repo="o/r",
        number=1,
        head_sha="abc",
        base_ref="main",
        head_ref="branch",
        labels=["human-authored"],
        authorization_signals=[
            AuthorizationSignal(
                operation="human-authored",
                signal_type="label",
                name="human-authored",
                actor="maintainer",
                actor_permission=actor,
                created_at=datetime.now(UTC),
                valid=True,
            )
        ],
    )
    report = check_human_bypass(pr)
    assert report.status == "passed"


def test_core_change_requires_admin_authorization() -> None:
    report = check_core_change(pr=None, changed_files=["src/scieasy/core/types/base.py"], session=None)
    assert report.status == "failed"
    assert report.findings[0].finding_class == "core-change"


def test_core_change_accepts_admin_authorization_signal() -> None:
    actor = ActorPermission(login="admin", permission="admin")
    pr = PullRequestMetadata(
        repo="o/r",
        number=1,
        head_sha="abc",
        base_ref="main",
        head_ref="branch",
        labels=["admin-approved:core-change"],
        authorization_signals=[
            AuthorizationSignal(
                operation="core-change",
                signal_type="label",
                name="admin-approved:core-change",
                actor="admin",
                actor_permission=actor,
                created_at=datetime.now(UTC),
                valid=True,
            )
        ],
    )
    report = check_core_change(pr=pr, changed_files=["src/scieasy/core/types/base.py"], session=None)
    assert report.status == "passed"


def test_pr_merge_requires_admin() -> None:
    pr = PullRequestMetadata(repo="o/r", number=1, head_sha="abc", base_ref="main", head_ref="b", labels=[])
    actor = ActorPermission(login="agent", permission="write")
    report = check_pr_merge(pr=pr, actor=actor, intent="merge")
    assert report.status == "failed"


def test_complete_artifacts_requires_tests_for_code(tmp_path: Path) -> None:
    report = check_complete_artifacts(
        repo_root=tmp_path,
        session=None,
        changed_files=["src/scieasy/qa/new_tool.py"],
    )
    assert report.status == "failed"
    assert any(finding.id == "complete-artifacts-missing-tests" for finding in report.findings)


def test_codemod_lint_requires_metadata_for_contract_change(tmp_path: Path) -> None:
    report = check_codemod_lint(repo_root=tmp_path, changed_files=["docs/specs/adr-042-test.md"])
    assert report.status == "failed"
    assert report.findings[0].id == "codemod-lint-missing-metadata"
