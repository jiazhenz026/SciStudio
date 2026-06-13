"""Rewritten CLI + verification tests for ADR-042 Addendum 6 (spec §5 / §10).

Owns the rewritten ``gate_record`` CLI surface (init / plan / amend / check /
finalize), alias delegation (§5.8), deterministic branch-scoped discovery (§5.1),
the migrated label vocabulary (``admin-approved:bypass``), and the Addendum 6 §4
acceptance behaviours not covered elsewhere: local == ci use the same evaluator
path, version/env parity fails closed when unreproducible (§7.10), incremental
check validity by covered surface + input fingerprint, per-task-kind obligation
inference for all eight kinds, and ``guided`` scope expansion via directive/scope
events without bypassing final tier-selected checks.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scistudio.qa.governance.gate_record import cli, evaluator, io, workflow
from scistudio.qa.governance.gate_record.checks import event_is_valid_for
from scistudio.qa.governance.gate_record.ledger import CheckEvent, GateLedger, TestEvent

RECORDS_DIR = ".workflow/records"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "track/x")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _run(repo: Path, *argv: str) -> int:
    return cli.main(["--repo-root", str(repo), *argv])


def _commit(repo: Path, rel: str, content: str = "x\n") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", f"add {rel}")


# ---------------------------------------------------------------------------
# init: creates the ledger, succeeds with NO issue (bootstrapping bug fixed).
# ---------------------------------------------------------------------------


def test_init_creates_ledger_without_issue(git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = _run(
        git_repo,
        "init",
        "--task-kind",
        "bugfix",
        "--persona",
        "implementer",
        "--runtime",
        "claude-code",
        "--branch",
        "track/x",
        "--owner-directive",
        "fix the thing",
        "--print-instructions",
        "false",
    )
    assert rc == workflow.EXIT_OK
    records = list((git_repo / RECORDS_DIR).glob("*.json"))
    assert len(records) == 1
    ledger = io.load_ledger(records[0])
    assert ledger.schema_version == 2
    assert ledger.task_kind == "bugfix"
    assert ledger.issues == []  # init no longer requires an issue.


def test_init_prints_task_instructions(git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _run(
        git_repo,
        "init",
        "--task-kind",
        "feature",
        "--persona",
        "implementer",
        "--runtime",
        "claude-code",
        "--branch",
        "track/x",
        "--owner-directive",
        "build a feature",
    )
    out = capsys.readouterr().out
    assert "gate ledger:" in out
    # Instruction generator renders task identity + persona guidance.
    assert "feature" in out.lower()


# ---------------------------------------------------------------------------
# plan / amend: append-only field updates.
# ---------------------------------------------------------------------------


def _init(git_repo: Path, **extra: str) -> Path:
    argv = [
        "init",
        "--task-kind",
        extra.get("task_kind", "bugfix"),
        "--persona",
        extra.get("persona", "implementer"),
        "--runtime",
        "claude-code",
        "--branch",
        "track/x",
        "--owner-directive",
        "do the work",
        "--print-instructions",
        "false",
    ]
    _run(git_repo, *argv)
    return next((git_repo / RECORDS_DIR).glob("*.json"))


def test_plan_appends_scope_and_issue(git_repo: Path) -> None:
    record = _init(git_repo)
    rc = _run(git_repo, "plan", "--include", "src/scistudio/**", "--issue", "1509")
    assert rc == workflow.EXIT_OK
    ledger = io.load_ledger(record)
    assert "src/scistudio/**" in ledger.effective_include()
    assert any(ref.number == 1509 for ref in ledger.issues)


def test_amend_requires_reason(git_repo: Path) -> None:
    _init(git_repo)
    # argparse marks --reason required; passing none is a usage error.
    with pytest.raises(SystemExit):
        _run(git_repo, "amend", "--include", "src/x.py")


def test_amend_records_scope_supersession(git_repo: Path) -> None:
    record = _init(git_repo)
    _run(git_repo, "plan", "--include", "src/a/**")
    rc = _run(git_repo, "amend", "--reason", "owner expansion", "--remove-include", "src/a/**", "--include", "src/b/**")
    assert rc == workflow.EXIT_OK
    ledger = io.load_ledger(record)
    assert "src/b/**" in ledger.effective_include()
    assert "src/a/**" not in ledger.effective_include()
    # Removal is a supersession event, not a deletion of history.
    assert any(e.action == "remove-include" for e in ledger.scope_events)


def test_amend_rejects_invalid_admin_label(git_repo: Path) -> None:
    _init(git_repo)
    with pytest.raises(SystemExit):
        # admin-approved:ai-override no longer exists (migrated to :bypass).
        _run(git_repo, "amend", "--reason", "x", "--admin-label", "admin-approved:ai-override")


def test_amend_accepts_migrated_bypass_label(git_repo: Path) -> None:
    record = _init(git_repo)
    rc = _run(git_repo, "amend", "--reason", "owner bypass", "--admin-label", "admin-approved:bypass")
    assert rc == workflow.EXIT_OK
    ledger = io.load_ledger(record)
    assert "admin-approved:bypass" in ledger.requested_label_names()


# ---------------------------------------------------------------------------
# Deterministic discovery (§5.1): branch-scoped, no stale matches.
# ---------------------------------------------------------------------------


def test_discovery_uses_only_current_branch_ledger(git_repo: Path) -> None:
    # An active ledger for the current branch.
    _init(git_repo)
    # A stale record from another branch must NOT match.
    other = GateLedger.model_validate(
        {
            "record_id": "other",
            "runtime": "claude-code",
            "task_kind": "bugfix",
            "persona": "implementer",
            "branch": "some/other-branch",
            "owner_directive": "unrelated",
        }
    )
    io.write_ledger(git_repo / RECORDS_DIR / "9999-other.json", other, repo_root=git_repo)
    discovery = io.discover_ledger(git_repo)
    assert discovery.found
    assert discovery.path is not None
    assert io.load_ledger(discovery.path).branch == "track/x"


def test_discovery_ignores_finalized_and_old_format_records(git_repo: Path) -> None:
    _init(git_repo)
    # A finalized same-branch record (post-PR) is no longer the active ledger.
    finalized = GateLedger.model_validate(
        {
            "record_id": "done",
            "runtime": "claude-code",
            "task_kind": "bugfix",
            "persona": "implementer",
            "branch": "track/x",
            "owner_directive": "already shipped",
            "pull_request": {"url": "https://github.com/o/r/pull/1", "number": 1},
        }
    )
    io.write_ledger(git_repo / RECORDS_DIR / "1-done.json", finalized, repo_root=git_repo)
    # An old-format (schema v1) record on the same branch must not match.
    (git_repo / RECORDS_DIR / "legacy.json").write_text(
        json.dumps({"schema_version": "1", "branch": "track/x", "task_id": "legacy"}),
        encoding="utf-8",
    )
    discovery = io.discover_ledger(git_repo)
    assert discovery.found
    assert discovery.path is not None
    assert io.load_ledger(discovery.path).record_id != "done"


def test_discovery_can_include_specific_finalized_record(git_repo: Path) -> None:
    finalized = GateLedger.model_validate(
        {
            "record_id": "done",
            "runtime": "claude-code",
            "task_kind": "bugfix",
            "persona": "implementer",
            "branch": "track/x",
            "owner_directive": "already shipped",
            "pull_request": {"url": "https://github.com/o/r/pull/1", "number": 1},
        }
    )
    record_path = git_repo / RECORDS_DIR / "1-done.json"
    io.write_ledger(record_path, finalized, repo_root=git_repo)

    default_discovery = io.discover_ledger(git_repo)
    assert not default_discovery.found

    included = io.discover_ledger(git_repo, include_finalized_paths=[record_path])
    assert included.found
    assert included.path == record_path


def test_discovery_reports_temporarily_unreadable_ledger(git_repo: Path) -> None:
    records_dir = git_repo / RECORDS_DIR
    records_dir.mkdir(parents=True)
    record_path = records_dir / "1586-partial.json"
    record_path.write_text("{", encoding="utf-8")

    discovery = io.discover_ledger(git_repo)
    assert not discovery.found
    assert discovery.has_unreadable
    assert discovery.unreadable == [record_path]

    resolved, err = workflow._resolve_ledger_path(git_repo, None)
    assert resolved is None
    assert err is not None
    assert err.exit_code == workflow.EXIT_SCHEMA
    assert "temporarily unreadable" in "\n".join(err.lines)


def test_discovery_ignores_stale_v1_record_alongside_v2(git_repo: Path) -> None:
    # Codex P1 #1 (#1509): the deleted 1509-adr042-add6-guards.json was a
    # throwaway schema-v1 scope record on a sub-branch, superseded by the v2
    # umbrella ledger. Even on the SAME branch a stale v1 record must never be
    # discovered as the active ledger; only the v2 record resolves.
    branch = "track/adr-042-add6/umbrella"
    v2 = GateLedger.model_validate(
        {
            "record_id": "1509-umbrella-integration",
            "runtime": "claude-code",
            "task_kind": "feature",
            "persona": "implementer",
            "branch": branch,
            "owner_directive": "umbrella integration",
        }
    )
    io.write_ledger(git_repo / RECORDS_DIR / "1509-umbrella-integration.json", v2, repo_root=git_repo)
    # A stale schema-v1 throwaway record on the same branch (as the deleted file).
    (git_repo / RECORDS_DIR / "1509-adr042-add6-guards.json").write_text(
        json.dumps({"schema_version": "1", "branch": branch, "task_id": "1509-adr042-add6-guards"}),
        encoding="utf-8",
    )
    discovery = io.discover_ledger(git_repo, branch=branch)
    assert discovery.found
    assert discovery.path is not None
    assert discovery.path.name == "1509-umbrella-integration.json"
    assert io.load_ledger(discovery.path).record_id == "1509-umbrella-integration"


def test_discovery_zero_matches_reports_run_init(git_repo: Path) -> None:
    discovery = io.discover_ledger(git_repo)
    assert not discovery.found
    assert discovery.candidates == []


def test_discovery_multiple_same_branch_is_ambiguous(git_repo: Path) -> None:
    for name in ("a", "b"):
        ledger = GateLedger.model_validate(
            {
                "record_id": name,
                "runtime": "claude-code",
                "task_kind": "bugfix",
                "persona": "implementer",
                "branch": "track/x",
                "owner_directive": "d",
            }
        )
        io.write_ledger(git_repo / RECORDS_DIR / f"{name}.json", ledger, repo_root=git_repo)
    discovery = io.discover_ledger(git_repo)
    assert not discovery.found
    assert discovery.ambiguous
    assert len(discovery.candidates) == 2


def test_check_says_run_init_when_no_ledger(git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = _run(git_repo, "check")
    out = capsys.readouterr().out
    assert rc == workflow.EXIT_USAGE
    assert "run init" in out.lower()


# ---------------------------------------------------------------------------
# CI branch resolution (#1509): in `pull_request` events the checkout is a
# detached merge commit, so `git rev-parse --abbrev-ref HEAD` is not the PR
# branch. Discovery must scope to the CI-provided PR branch ref instead.
# ---------------------------------------------------------------------------


def test_ci_branch_resolution_finds_ledger_in_detached_head(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Ledger for the PR branch (not the branch git currently has checked out).
    pr_branch = "track/adr-042-add6/umbrella"
    ledger = GateLedger.model_validate(
        {
            "record_id": "umbrella",
            "runtime": "claude-code",
            "task_kind": "manager",
            "persona": "manager",
            "branch": pr_branch,
            "owner_directive": "umbrella integration",
        }
    )
    io.write_ledger(git_repo / RECORDS_DIR / "1509-umbrella.json", ledger, repo_root=git_repo)

    # Simulate a CI detached-HEAD checkout: HEAD points at a commit, no branch.
    _git(git_repo, "checkout", "-q", "--detach", "HEAD")
    # Without CI env, the detached HEAD yields no branch -> single-ledger fallback.
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    assert io.current_branch(git_repo) is None

    # With the GitHub Actions PR env set, the PR branch is resolved and matches.
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_HEAD_REF", pr_branch)
    monkeypatch.setenv("GITHUB_REF_NAME", pr_branch)
    assert io.current_branch(git_repo) == pr_branch
    discovery = io.discover_ledger(git_repo)
    assert discovery.found
    assert discovery.path is not None
    assert io.load_ledger(discovery.path).branch == pr_branch


def test_ci_branch_resolution_falls_back_to_ref_name(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # GITHUB_REF_NAME is the fallback when GITHUB_HEAD_REF is unset (e.g. push).
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    monkeypatch.setenv("GITHUB_REF_NAME", "track/x")
    assert io.current_branch(git_repo) == "track/x"


def test_detached_head_single_ledger_fallback(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # No CI env and a detached HEAD: discovery cannot scope to a branch, but a
    # lone non-finalized v2 ledger is unambiguous and is used as a last resort.
    other = GateLedger.model_validate(
        {
            "record_id": "lone",
            "runtime": "claude-code",
            "task_kind": "bugfix",
            "persona": "implementer",
            "branch": "some/other-branch",
            "owner_directive": "the only active gate work",
        }
    )
    io.write_ledger(git_repo / RECORDS_DIR / "1-lone.json", other, repo_root=git_repo)
    _git(git_repo, "checkout", "-q", "--detach", "HEAD")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    assert io.current_branch(git_repo) is None
    discovery = io.discover_ledger(git_repo)
    assert discovery.found
    assert discovery.path is not None
    assert io.load_ledger(discovery.path).record_id == "lone"


def test_detached_head_multiple_ledgers_stays_ambiguous(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # With more than one active ledger and no resolvable branch, never guess:
    # report the candidates so the caller passes --record.
    for name in ("a", "b"):
        ledger = GateLedger.model_validate(
            {
                "record_id": name,
                "runtime": "claude-code",
                "task_kind": "bugfix",
                "persona": "implementer",
                "branch": f"track/{name}",
                "owner_directive": "d",
            }
        )
        io.write_ledger(git_repo / RECORDS_DIR / f"{name}.json", ledger, repo_root=git_repo)
    _git(git_repo, "checkout", "-q", "--detach", "HEAD")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    discovery = io.discover_ledger(git_repo)
    assert not discovery.found
    assert discovery.ambiguous
    assert len(discovery.candidates) == 2


# ---------------------------------------------------------------------------
# Alias delegation (§5.8): aliases delegate to the new code, own no decision.
# ---------------------------------------------------------------------------


def test_start_alias_delegates_to_init(git_repo: Path) -> None:
    rc = _run(
        git_repo,
        "start",
        "--task-kind",
        "bugfix",
        "--persona",
        "implementer",
        "--runtime",
        "claude-code",
        "--branch",
        "track/x",
        "--owner-directive",
        "via alias",
        "--print-instructions",
        "false",
    )
    assert rc == workflow.EXIT_OK
    assert list((git_repo / RECORDS_DIR).glob("*.json"))


def test_pre_push_alias_runs_check_in_pre_push_mode(git_repo: Path) -> None:
    record = _init(git_repo)
    _run(git_repo, "plan", "--include", "src/scistudio/**", "--issue", "1509")
    _commit(git_repo, "src/scistudio/x.py")
    # pre-push alias delegates to check --mode pre-push. --skip-execution keeps
    # the assertion about MODE delegation independent of real check tooling.
    _run(git_repo, "pre-push", "--base", "HEAD~1", "--head", "HEAD", "--skip-execution")
    ledger = io.load_ledger(record)
    # The alias delegated to check --mode pre-push (single evaluator path).
    assert ledger.reconcile_events[-1].mode == "pre-push"
    # A WIP in-scope push records NO PR-readiness obligation gaps (§3.4); any
    # remaining gaps are diff-coherence / environment guards, never PR-readiness.
    unsatisfied = ledger.reconcile_events[-1].unsatisfied
    assert "issue.required" not in unsatisfied
    assert "tests.changed_test_required" not in unsatisfied
    assert "docs.docs_required_or_na" not in unsatisfied
    assert "guard.docs_landing" not in unsatisfied
    assert "guard.issue_link" not in unsatisfied


def test_pr_ready_alias_runs_check_in_pre_pr_mode(git_repo: Path) -> None:
    record = _init(git_repo)
    _run(git_repo, "plan", "--include", "src/scistudio/**")
    _commit(git_repo, "src/scistudio/x.py")
    # No issue linked -> pre-pr blocks on PR-readiness (issue obligation). Use
    # --skip-execution so the failure is the PR-readiness gap, not check tooling.
    rc = _run(git_repo, "pr-ready", "--base", "HEAD~1", "--head", "HEAD", "--skip-execution")
    assert rc == workflow.EXIT_FAIL
    # And the reconcile event records the pre-pr mode (single evaluator path).
    ledger = io.load_ledger(record)
    assert ledger.reconcile_events[-1].mode == "pre-pr"


# ---------------------------------------------------------------------------
# Fix C: --only / --skip-execution cannot report final readiness (§7.5).
# ---------------------------------------------------------------------------


def test_skip_execution_prints_not_final_readiness_banner(git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _init(git_repo)
    _run(git_repo, "plan", "--include", "src/scistudio/**", "--issue", "1509")
    _commit(git_repo, "src/scistudio/x.py")
    # local recovery: --skip-execution leaves mandatory tier checks unrun. It must
    # print the "NOT final PR readiness" banner naming which mandatory checks were
    # skipped, and must NOT print the unqualified "reconciliation passed" line
    # (which would falsely claim final readiness).
    _run(git_repo, "check", "--base", "HEAD~1", "--head", "HEAD", "--skip-execution")
    out = capsys.readouterr().out.lower()
    assert "not final pr readiness" in out
    assert "mandatory" in out
    # Never the bare final-readiness claim while mandatory checks are unrun.
    assert "\nreconciliation passed" not in out


def test_local_recovery_may_exit_zero_when_only_unrun_checks_remain(
    git_repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Neutralize unrelated guards so the ONLY gap is the unrun mandatory checks;
    # this isolates the §7.5 rule that local recovery may exit 0 but with the
    # not-final-readiness banner.
    monkeypatch.setattr(evaluator, "GUARD_REGISTRY", {}, raising=True)
    _init(git_repo)
    _run(
        git_repo,
        "plan",
        "--include",
        "src/scistudio/**",
        "--include",
        "tests/**",
        "--issue",
        "1509",
        "--docs-na",
        "implementation:internal change",
        "--test-path",
        "tests/test_x.py",
    )
    (git_repo / "src/scistudio").mkdir(parents=True, exist_ok=True)
    (git_repo / "src/scistudio/x.py").write_text("x = 1\n", encoding="utf-8")
    (git_repo / "tests").mkdir(parents=True, exist_ok=True)
    (git_repo / "tests/test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _git(git_repo, "add", "src/scistudio/x.py", "tests/test_x.py")
    _git(git_repo, "commit", "-q", "-m", "impl + test")
    rc = _run(git_repo, "check", "--base", "HEAD~1", "--head", "HEAD", "--skip-execution")
    out = capsys.readouterr().out.lower()
    assert "not final pr readiness" in out
    # Local recovery may exit 0; the banner is the required signal, not failure.
    assert rc == workflow.EXIT_OK


def test_only_recovery_in_pre_pr_is_not_final_readiness(git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _init(git_repo)
    _run(git_repo, "plan", "--include", "src/scistudio/**", "--issue", "1509")
    _commit(git_repo, "src/scistudio/x.py")
    # pre-pr (strict) with --only runs a subset; mandatory tier checks remain
    # unrun, so this is NOT final readiness and must not exit 0 as if ready.
    rc = _run(git_repo, "check", "--mode", "pre-pr", "--base", "HEAD~1", "--head", "HEAD", "--only", "__none__")
    out = capsys.readouterr().out.lower()
    assert "not final pr readiness" in out
    assert rc != workflow.EXIT_OK


def test_full_check_no_recovery_does_not_print_recovery_banner(
    git_repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from scistudio.qa.governance.gate_record import checks
    from scistudio.qa.governance.gate_record.ledger import CheckEvent

    # Stub check execution so this exercises the full (non-recovery) path without
    # running heavy real tools; every required check is "run" -> no unrun gap.
    def _pass(repo_root: Path, name: str, **_kw: object) -> CheckEvent:
        return CheckEvent(name=name, command="x", covered_surface="python", exit_code=0, status="pass", summary="clean")

    monkeypatch.setattr(checks, "run_check", _pass)
    _init(git_repo, task_kind="docs", persona="adr_author")
    _run(git_repo, "plan", "--include", "docs/**", "--issue", "1509", "--test-na", "implementation:docs only")
    _commit(git_repo, "docs/notes.md")
    # A full docs-tier check (no --only/--skip-execution) should not emit the
    # recovery banner.
    _run(git_repo, "check", "--base", "HEAD~1", "--head", "HEAD")
    out = capsys.readouterr().out.lower()
    assert "not final pr readiness" not in out


# ---------------------------------------------------------------------------
# Fix D: default base = merge-base(origin/main, HEAD), not raw origin/main.
# ---------------------------------------------------------------------------


def test_resolve_default_base_uses_merge_base(git_repo: Path) -> None:
    # Build: base commit -> branch off -> add divergent commits on both sides.
    _git(git_repo, "branch", "feature")
    _commit(git_repo, "main_only.py", "m\n")  # advances track/x past the fork point
    main_head = io.resolve_sha(git_repo, "HEAD")
    _git(git_repo, "checkout", "-q", "feature")
    _commit(git_repo, "feature_only.py", "f\n")
    fork_point = subprocess.run(
        ["git", "merge-base", "track/x", "HEAD"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    resolved = io.resolve_default_base(git_repo, upstream="track/x", head="HEAD")
    # The default base is the fork point (merge-base), NOT the advanced track/x tip.
    assert resolved == fork_point
    assert resolved != main_head


def test_resolve_default_base_falls_back_when_no_merge_base(git_repo: Path) -> None:
    # An unresolvable upstream ref cannot produce a merge-base -> fall back.
    resolved = io.resolve_default_base(git_repo, upstream="origin/main", head="HEAD")
    assert resolved == "origin/main"


def test_explicit_base_is_honored_verbatim(git_repo: Path) -> None:
    base = workflow._resolve_base(git_repo, "HEAD~0", "HEAD")
    assert base == "HEAD~0"


# ---------------------------------------------------------------------------
# pre-push vs pre-pr: WIP push is not blocked as if opening a PR (§3.4).
# ---------------------------------------------------------------------------


def test_pre_push_does_not_enforce_pr_readiness_but_pre_pr_does(git_repo: Path) -> None:
    ledger = GateLedger.model_validate(
        {
            "record_id": "1509-x",
            "runtime": "claude-code",
            "task_kind": "bugfix",
            "persona": "implementer",
            "branch": "track/x",
            "owner_directive": "fix",
            "declared_scope": {"include": ["src/scistudio/**"]},
        }
    )
    _commit(git_repo, "src/scistudio/x.py")
    push = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="pre-push", run_checks=False
    )
    # No docs/test/issue PR-readiness gaps block a WIP push.
    assert "issue.required" not in push.unsatisfied
    assert "tests.changed_test_required" not in push.unsatisfied
    assert "docs.docs_required_or_na" not in push.unsatisfied
    assert "guard.docs_landing" not in push.unsatisfied
    assert "guard.issue_link" not in push.unsatisfied

    pre_pr = evaluator.reconcile(
        ledger=GateLedger.model_validate(ledger.model_dump(mode="json")),
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="pre-pr",
        run_checks=False,
    )
    # pre-pr stays strict: missing issue + test evidence are gaps.
    assert "issue.required" in pre_pr.unsatisfied
    assert "tests.changed_test_required" in pre_pr.unsatisfied


def test_pre_push_still_blocks_out_of_scope_change(git_repo: Path) -> None:
    ledger = GateLedger.model_validate(
        {
            "record_id": "1509-x",
            "runtime": "claude-code",
            "task_kind": "bugfix",
            "persona": "implementer",
            "branch": "track/x",
            "owner_directive": "fix",
            "declared_scope": {"include": ["src/scistudio/api/**"]},
        }
    )
    _commit(git_repo, "src/scistudio/core/secret.py")
    push = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="pre-push", run_checks=False
    )
    # Scope/diff coherence IS validated on pre-push.
    assert any(f.rule_id == "scope.out-of-scope" for f in push.report.findings)


# ---------------------------------------------------------------------------
# local == ci: the same evaluator path / tier for the same diff (§10.3).
# ---------------------------------------------------------------------------


def test_local_and_ci_use_same_evaluator_path(git_repo: Path) -> None:
    _commit(git_repo, "src/scistudio/qa/governance/x.py")

    def _fresh() -> GateLedger:
        return GateLedger.model_validate(
            {
                "record_id": "1509-x",
                "runtime": "claude-code",
                "task_kind": "maintenance",
                "persona": "implementer",
                "branch": "track/x",
                "owner_directive": "fix",
                "declared_scope": {"include": ["src/scistudio/**"]},
            }
        )

    local = evaluator.reconcile(
        ledger=_fresh(), repo_root=git_repo, base="HEAD~1", head="HEAD", mode="local", run_checks=False
    )
    ci = evaluator.reconcile(
        ledger=_fresh(), repo_root=git_repo, base="HEAD~1", head="HEAD", mode="ci", run_checks=False
    )
    # One reconciliation code path, one tier-selection input: same tier and the
    # SAME pre-role-split tier-selected check set for the same diff.
    assert local.strictness_tier == ci.strictness_tier == 1  # qa/governance escalates.
    # §7.5 role split (#1509): the workflow-gate ``ci`` mode validates GOVERNANCE
    # + guards, so the ci.yml-owned quality matrix is dropped from ci-mode
    # required obligations (ci.yml jobs are authoritative for it on the same PR).
    # local keeps the full matrix as the CI-equivalent preflight.
    assert set(local.required_obligations.checks) & evaluator._CI_OWNED_QUALITY_CHECKS
    assert not (set(ci.required_obligations.checks) & evaluator._CI_OWNED_QUALITY_CHECKS)


# ---------------------------------------------------------------------------
# Per-task-kind obligation inference for all eight kinds (§7.7).
# ---------------------------------------------------------------------------


_ALL_TASK_KINDS = ("hotfix", "bugfix", "feature", "refactor", "docs", "maintenance", "manager", "guided")


@pytest.mark.parametrize("task_kind", _ALL_TASK_KINDS)
def test_obligation_inference_per_task_kind(task_kind: str, git_repo: Path) -> None:
    _commit(git_repo, "src/scistudio/x.py")
    persona = "adr_author" if task_kind == "docs" else ("manager" if task_kind == "manager" else "implementer")
    ledger = GateLedger.model_validate(
        {
            "record_id": "1509-x",
            "runtime": "claude-code",
            "task_kind": task_kind,
            "persona": persona,
            "branch": "track/x",
            "owner_directive": "work",
            "declared_scope": {"include": ["src/scistudio/**"]},
        }
    )
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="local", run_checks=False
    )
    obligations = result.required_obligations
    # Every kind always runs every guard once and infers >=1 required check.
    assert obligations.guards == sorted(evaluator.GUARD_REGISTRY.keys())
    assert obligations.checks
    # An implementation change requires test evidence for code-bearing kinds, but
    # docs/manager kinds do not (§3.3.5).
    if task_kind in ("docs", "manager"):
        assert "changed_test_required" not in obligations.tests
    else:
        assert "changed_test_required" in obligations.tests


# ---------------------------------------------------------------------------
# guided scope expansion via directive/scope events (§9 / §10.3).
# ---------------------------------------------------------------------------


def test_guided_scope_expands_without_bypassing_final_checks(git_repo: Path) -> None:
    from scistudio.qa.governance.gate_record.ledger import ScopeEvent

    _commit(git_repo, "src/scistudio/newly/asked.py")
    ledger = GateLedger.model_validate(
        {
            "record_id": "1509-guided",
            "runtime": "claude-code",
            "task_kind": "guided",
            "persona": "live_implementer",
            "branch": "track/x",
            "owner_directive": "live session",
            "declared_scope": {"include": ["src/scistudio/initial/**"]},
            "issues": [{"number": 1509, "url": "https://github.com/o/r/issues/1509"}],
        }
    )
    # Without the directive the new file is out of scope.
    before = evaluator.reconcile(
        ledger=GateLedger.model_validate(ledger.model_dump(mode="json")),
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="local",
        run_checks=False,
    )
    assert any(f.rule_id == "scope.out-of-scope" for f in before.report.findings)

    # Owner directive expands scope (append-only). Now in scope...
    ledger.scope_events.append(ScopeEvent(action="add-include", pattern="src/scistudio/newly/**", reason="owner"))
    after = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="pre-pr", run_checks=False
    )
    assert not any(f.rule_id == "scope.out-of-scope" for f in after.report.findings)
    # ...but the final tier-selected check obligations are NOT bypassed: a guided
    # implementation change still owes test evidence.
    assert "tests.changed_test_required" in after.unsatisfied


# ---------------------------------------------------------------------------
# Incremental check validity (§7.2 / §10.3).
# ---------------------------------------------------------------------------


def test_incremental_check_validity_by_covered_surface() -> None:
    py = CheckEvent(
        name="lint_format",
        command="ruff check .",
        covered_surface="python",
        status="pass",
        exit_code=0,
        input_fingerprint=io.fingerprint_paths(["src/scistudio/x.py"]),
    )
    # An UNRELATED edit (different surface fingerprint) does not invalidate it.
    same_surface_fp = io.fingerprint_paths(["src/scistudio/x.py"])
    assert event_is_valid_for(py, input_fingerprint=same_surface_fp)
    # A later edit to the SAME covered surface changes the fingerprint and
    # invalidates only that surface's evidence.
    changed_fp = io.fingerprint_paths(["src/scistudio/x.py", "src/scistudio/y.py"])
    assert not event_is_valid_for(py, input_fingerprint=changed_fp)


# ---------------------------------------------------------------------------
# Parity fails closed when the environment cannot be reproduced (§7.10).
# ---------------------------------------------------------------------------


def test_parity_fails_closed_for_pr_readiness(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scistudio.qa.governance.gate_record import parity

    _commit(git_repo, "src/scistudio/x.py")
    ledger = GateLedger.model_validate(
        {
            "record_id": "1509-x",
            "runtime": "claude-code",
            "task_kind": "bugfix",
            "persona": "implementer",
            "branch": "track/x",
            "owner_directive": "fix",
            "declared_scope": {"include": ["src/scistudio/**"]},
            "issues": [{"number": 1509, "url": "https://github.com/o/r/issues/1509"}],
        }
    )
    # Simulate an unreproducible CI-equivalent environment WITHOUT creating a
    # real venv or hitting the network: monkeypatch the provisioning seam to
    # return a fail-closed report (§7.10). assess_parity delegates to
    # provision_venv in local/pre-pr modes.
    monkeypatch.setattr(
        parity,
        "provision_venv",
        lambda _repo, **_k: parity.ParityReport(
            importable=False, gaps=["cannot create isolated per-worktree venv: simulated"]
        ),
    )
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="pre-pr", run_checks=True, only=["__none__"]
    )
    # Fail closed: a parity gap is an unsatisfied obligation in PR-readiness mode.
    assert result.parity_gaps
    assert any(item.startswith("parity.") for item in result.unsatisfied)


# ---------------------------------------------------------------------------
# Sanitization (§8): no absolute local paths in committed events.
# ---------------------------------------------------------------------------


def test_check_sanitization_violation_returns_exit_5(git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    record = _init(git_repo)
    ledger = io.load_ledger(record)
    ledger.test_events.append(TestEvent(kind="path", path="tests/test_x.py"))
    # Inject a forbidden absolute path into a committed event via a check_event.
    ledger.check_events.append(
        CheckEvent(
            name="lint",
            command="ruff check .",
            covered_surface="python",
            status="fail",
            exit_code=1,
            summary=r"error in C:\Users\someone\repo\x.py",
        )
    )
    sanitize_path = git_repo / RECORDS_DIR / record.name
    save_err = workflow._save(git_repo, sanitize_path, ledger)
    assert save_err is not None
    assert save_err.exit_code == workflow.EXIT_SANITIZE


# ---------------------------------------------------------------------------
# finalize: pre-PR (no --pr) vs post-PR (--pr), no chicken-egg deadlock (§10.2).
# ---------------------------------------------------------------------------


def test_finalize_pre_pr_requires_body_file_not_pr(git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _init(git_repo)
    # Pre-PR finalize without --pr-body-file is a usage error (not a PR-URL req).
    rc = _run(git_repo, "finalize", "--commit", "abc123")
    out = capsys.readouterr().out
    assert rc == workflow.EXIT_USAGE
    assert "pr-body-file" in out.lower()


def test_finalize_pre_pr_records_commit_and_closes(git_repo: Path, tmp_path: Path) -> None:
    record = _init(git_repo)
    _run(git_repo, "plan", "--include", "src/scistudio/**", "--issue", "1509")
    _commit(git_repo, "src/scistudio/x.py")
    _run(git_repo, "plan", "--test-path", "src/scistudio/x.py", "--docs-na", "implementation:internal")
    body = git_repo / "body.md"
    body.write_text("Closes #1509\n", encoding="utf-8")
    rc = _run(
        git_repo,
        "finalize",
        "--base",
        "HEAD~1",
        "--head",
        "HEAD",
        "--commit",
        "abc123",
        "--pr-body-file",
        str(body),
        "--closes",
        "1509",
    )
    ledger = io.load_ledger(record)
    assert ledger.commit is not None and ledger.commit.sha == "abc123"
    assert ledger.pull_request is not None and 1509 in ledger.pull_request.closes
    # rc may be 0 or non-zero depending on check execution; the recording is the
    # contract under test here. Assert it is a defined workflow exit code.
    assert rc in (workflow.EXIT_OK, workflow.EXIT_FAIL, workflow.EXIT_TOOL)


# ---------------------------------------------------------------------------
# --no-record: the git-hook form gates without persisting the ledger (#1609).
# ---------------------------------------------------------------------------


def _init_for_no_record(repo: Path) -> Path:
    _run(
        repo,
        "init",
        "--task-kind",
        "bugfix",
        "--persona",
        "implementer",
        "--runtime",
        "claude-code",
        "--branch",
        "track/x",
        "--owner-directive",
        "fix the thing",
        "--print-instructions",
        "false",
    )
    return next((repo / RECORDS_DIR).glob("*.json"))


def test_no_record_flag_parses_on_check_and_commit_msg() -> None:
    parser = cli.build_parser()
    assert parser.parse_args(["check", "--mode", "pre-commit", "--no-record"]).no_record is True
    assert parser.parse_args(["commit-msg", "MSG", "--no-record"]).no_record is True


def test_check_no_record_does_not_modify_the_ledger(git_repo: Path) -> None:
    record = _init_for_no_record(git_repo)
    # A normal check persists evidence/obligations -> establish a baseline.
    _run(git_repo, "check", "--mode", "pre-commit", "--skip-execution")
    baseline = record.read_bytes()
    # The git-hook form (--no-record) must NOT touch the ledger. Under the
    # pre-commit framework a hook that modifies a tracked file fails the commit,
    # and the gate's always-append evidence never converges (#1609 deadlock).
    rc = _run(git_repo, "check", "--mode", "pre-commit", "--no-record", "--skip-execution")
    assert record.read_bytes() == baseline
    assert rc in (workflow.EXIT_OK, workflow.EXIT_FAIL, workflow.EXIT_TOOL)


def test_commit_msg_check_discovers_finalized_ledger(git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # After post-PR finalize records the PR URL the ledger is "finalized"; the
    # commit-msg git hook still runs on the provenance commit and must discover
    # it, not fail "no gate ledger found" (#1609).
    record = _init_for_no_record(git_repo)
    data = json.loads(record.read_text(encoding="utf-8"))
    data["pull_request"] = {
        "url": "https://example.com/pr/1",
        "number": 1,
        "closes": [],
        "body_closes_issues": [],
    }
    record.write_text(json.dumps(data), encoding="utf-8")
    assert io.load_ledger(record).pull_request is not None  # valid + finalized

    msg = git_repo / "COMMIT_EDITMSG"
    msg.write_text("chore: follow-up\n", encoding="utf-8")
    capsys.readouterr()
    _run(git_repo, "commit-msg", str(msg), "--no-record")
    out = capsys.readouterr()
    assert "no gate ledger found" not in (out.out + out.err)


# ---------------------------------------------------------------------------
# #1628: pre-commit drops the two slowest checks; failed checks inline findings.
# ---------------------------------------------------------------------------


def test_pre_commit_mode_skips_python_tests_and_semantic_dup(
    git_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(git_repo)
    # A python-src change selects both python_tests (has_python_src) and
    # semantic_dup (sentrux-applicable).
    _commit(git_repo, "src/scistudio/x.py", "y = 1\n")
    capsys.readouterr()
    _run(git_repo, "check", "--base", "HEAD~1", "--mode", "pre-commit", "--skip-execution")
    pre_commit = capsys.readouterr().out
    _run(git_repo, "check", "--base", "HEAD~1", "--mode", "pre-pr", "--skip-execution")
    pre_pr = capsys.readouterr().out
    # pre-commit drops the two slow checks; pre-pr keeps the full selection.
    assert "python_tests" not in pre_commit
    assert "semantic_dup" not in pre_commit
    assert "python_tests" in pre_pr
    assert "semantic_dup" in pre_pr


def test_failed_check_excerpt_surfaces_log_tail(tmp_path: Path) -> None:
    log = tmp_path / ".workflow" / "local" / "logs" / "full_audit.log"
    log.parent.mkdir(parents=True)
    log.write_text("noise line\nERROR: thing A\nFAILED test_b\n", encoding="utf-8")
    event = CheckEvent(
        name="full_audit",
        command="cmd",
        covered_surface="governance",
        status="fail",
        raw_log_ref=".workflow/local/logs/full_audit.log",
    )
    out = evaluator._failed_check_excerpt(tmp_path, event)
    assert "ERROR: thing A" in out
    assert "FAILED test_b" in out
    assert out.lstrip().startswith("|")  # indented excerpt lines


def test_failed_check_excerpt_empty_without_log(tmp_path: Path) -> None:
    no_ref = CheckEvent(name="x", command="c", covered_surface="python", status="fail", raw_log_ref=None)
    missing = CheckEvent(name="x", command="c", covered_surface="python", status="fail", raw_log_ref="nope.log")
    assert evaluator._failed_check_excerpt(tmp_path, no_ref) == ""
    assert evaluator._failed_check_excerpt(tmp_path, missing) == ""
