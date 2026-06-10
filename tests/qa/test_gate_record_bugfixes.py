"""Regression tests for the C5 governance gate-record bug-fix session.

Covers issues #1547, #1463, #1464, #1345, #1283. Several of these issues were
filed against the pre-Addendum-6 CLI and are already fixed by the ledger rewrite;
the tests here LOCK IN the correct behaviour so the issues can be closed as
fixed-with-coverage, and exercise the genuine defects fixed in this session
(first-parent scope set, integration-record scope downgrade, main-side rename
tolerance, CLI scope blocking, and the stacked-PR hook base resolution).

These tests must never weaken governance: each "should pass" assertion is paired
with a "still blocks" assertion proving enforcement is intact.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scistudio.qa.governance.gate_record import cli, evaluator, io, workflow
from scistudio.qa.governance.gate_record.ledger import DeclaredScope, DocsEvent, GateLedger, IssueRef
from scistudio.qa.schemas.report import Severity

# ---------------------------------------------------------------------------
# Git fixture (self-contained: disables commit signing so it runs anywhere).
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _commit(repo: Path, *, message: str) -> None:
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", message)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "test")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "root.txt").write_text("r\n", encoding="utf-8")
    _git(repo, "add", "root.txt")
    _commit(repo, message="root")
    return repo


def _add_commit(repo: Path, rel: str, content: str = "x\n", *, message: str | None = None) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", rel)
    _commit(repo, message=message or f"add {rel}")


def _ledger(**overrides: object) -> GateLedger:
    base: dict[str, object] = {
        "record_id": "rec",
        "runtime": "claude-code",
        "task_kind": "bugfix",
        "persona": "implementer",
        "branch": "feat/x",
        "owner_directive": "do the thing",
    }
    base.update(overrides)
    return GateLedger.model_validate(base)


# ---------------------------------------------------------------------------
# #1547 — plan mutator must validate-before-persist; no IMPLEMENT-via-amend.
# ---------------------------------------------------------------------------


def test_1547_plan_invalid_test_na_does_not_brick_record(git_repo: Path) -> None:
    """A bad ``plan --test-na`` is rejected (exit 2) and never persisted.

    The pre-Addendum-6 CLI persisted ``na:`` into ``changed_test_paths`` without
    write-time validation, bricking every subsequent load. The ledger model now
    validates at construction time (before save), so the record stays loadable.
    """

    assert (
        cli.main(
            [
                "--repo-root",
                str(git_repo),
                "init",
                "--task-kind",
                "bugfix",
                "--persona",
                "implementer",
                "--runtime",
                "claude",
                "--branch",
                "main",
                "--owner-directive",
                "fix",
                "--issue",
                "100",
                "--print-instructions",
                "false",
            ]
        )
        == workflow.EXIT_OK
    )
    record = next((git_repo / ".workflow/records").glob("*.json"))

    # Bad N/A (empty rationale) -> rejected, not persisted.
    rc = cli.main(["--repo-root", str(git_repo), "plan", "--record", str(record), "--test-na", "na:"])
    assert rc == workflow.EXIT_USAGE

    # The record is NOT bricked: a subsequent valid plan still loads & succeeds.
    rc2 = cli.main(["--repo-root", str(git_repo), "plan", "--record", str(record), "--include", "src/**"])
    assert rc2 == workflow.EXIT_OK
    reloaded = io.load_ledger(record)
    assert reloaded.test_events == []  # the bad event never landed
    assert "src/**" in reloaded.effective_include()


def test_1547_plan_invalid_issue_token_does_not_brick_record(git_repo: Path) -> None:
    cli.main(
        [
            "--repo-root",
            str(git_repo),
            "init",
            "--task-kind",
            "bugfix",
            "--persona",
            "implementer",
            "--runtime",
            "claude",
            "--branch",
            "main",
            "--owner-directive",
            "fix",
            "--print-instructions",
            "false",
        ]
    )
    record = next((git_repo / ".workflow/records").glob("*.json"))
    assert cli.main(["--repo-root", str(git_repo), "plan", "--record", str(record), "--issue", "notanum"]) == (
        workflow.EXIT_USAGE
    )
    # Still operable afterwards.
    assert cli.main(["--repo-root", str(git_repo), "plan", "--record", str(record), "--issue", "5"]) == workflow.EXIT_OK
    assert [ref.number for ref in io.load_ledger(record).issues] == [5]


def test_1547_legacy_v1_record_reports_schema_error_not_crash(git_repo: Path) -> None:
    """A pre-rewrite v1 record yields a clean EXIT_SCHEMA, not a traceback.

    This is the "ledger schema/migration error: N errors" robustness the issue
    flagged: a stale-format record must fail safely (exit 3), never crash the CLI.
    """

    records = git_repo / ".workflow/records"
    records.mkdir(parents=True, exist_ok=True)
    legacy = records / "legacy.json"
    legacy.write_text(
        '{"schema_version": 1, "record_id": "legacy", "stages": {"IMPLEMENT": "done"}}',
        encoding="utf-8",
    )
    rc = cli.main(["--repo-root", str(git_repo), "plan", "--record", str(legacy), "--include", "src/**"])
    assert rc == workflow.EXIT_SCHEMA


def test_1547_no_amend_needed_for_implement_progression(git_repo: Path) -> None:
    """A task with no scope change reconciles via ``check`` alone (no no-op amend).

    The legacy CLI marked the IMPLEMENT stage done only via ``amend``; the ledger
    model has no stage machine, so a normal ``check`` lifecycle never requires a
    no-op amendment as a workaround.
    """

    _add_commit(git_repo, "docs/notes.md", message="docs only")
    ledger = _ledger(
        task_kind="docs",
        persona="implementer",
        branch="main",
        issues=[IssueRef(number=1)],
        declared_scope=DeclaredScope(include=["docs/**"]),
    )
    # docs N/A so the docs obligation is satisfied without an amend.
    ledger.docs_events.append(DocsEvent.model_validate({"kind": "na", "class": "docs", "rationale": "trivial"}))
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="local", run_checks=False
    )
    # No scope violation, no IMPLEMENT-stage gymnastics required.
    assert "scope.out-of-scope" not in result.unsatisfied


# ---------------------------------------------------------------------------
# #1463 — pre-push merge tolerance + main-side rename tolerance.
# ---------------------------------------------------------------------------


def _merge(repo: Path, branch: str) -> None:
    subprocess.run(
        ["git", "merge", "--no-gpg-sign", "-q", "-m", f"merge {branch}", branch],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def test_1463_scope_set_excludes_merge_only_files(git_repo: Path) -> None:
    """``scope_changed_files`` returns only PR-authored (first-parent) files.

    A file that entered the branch via ``git merge origin/main`` (or a merge
    commit's conflict resolution) is NOT attributed to the PR for scope checking.
    """

    _git(git_repo, "checkout", "-q", "-b", "pr/x")
    _add_commit(git_repo, "feature.py", message="pr: feature")
    # main advances with its own file.
    _git(git_repo, "checkout", "-q", "main")
    _add_commit(git_repo, "main_only.py", message="main: main_only")
    _git(git_repo, "checkout", "-q", "pr/x")
    _merge(git_repo, "main")
    # Add an extra file IN the merge commit (simulates conflict-resolution touch).
    (git_repo / "merge_artifact.py").write_text("m\n", encoding="utf-8")
    _git(git_repo, "add", "merge_artifact.py")
    _git(git_repo, "commit", "-q", "--no-gpg-sign", "--amend", "--no-edit")

    full = io.changed_files(git_repo, "main", "HEAD")
    scope = io.scope_changed_files(git_repo, "main", "HEAD")
    assert "merge_artifact.py" in full  # full diff sees the merge artifact
    assert "main_only.py" not in scope  # but the PR-authored set does not
    assert "merge_artifact.py" not in scope
    assert scope == ["feature.py"]


def test_1463_pre_push_does_not_false_fail_on_merge_only_file(git_repo: Path) -> None:
    """A pre-push after merging main must not flag main-side files out-of-scope."""

    _git(git_repo, "checkout", "-q", "-b", "pr/x")
    _add_commit(git_repo, "src/scistudio/api/feature.py", message="pr: api feature")
    _git(git_repo, "checkout", "-q", "main")
    _add_commit(git_repo, "src/scistudio/other/thing.py", message="main: other thing")
    _git(git_repo, "checkout", "-q", "pr/x")
    _merge(git_repo, "main")

    ledger = _ledger(branch="pr/x", declared_scope=DeclaredScope(include=["src/scistudio/api/**"]))
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="main", head="HEAD", mode="pre-push", run_checks=False
    )
    assert "scope.out-of-scope" not in result.unsatisfied
    assert not any(f.rule_id == "scope.out-of-scope" for f in result.report.findings)


def test_1463_main_side_rename_downgrades_to_warning(git_repo: Path) -> None:
    """A scoped path renamed/split on main is tolerated (warning, not block).

    The record scopes the old god-file path; main split it into a package while
    the PR was in review. Continuation work on the new path is a WARNING with a
    remap hint, not a hard block.
    """

    # Record scopes the OLD path that no longer exists.
    _git(git_repo, "checkout", "-q", "-b", "pr/x")
    # PR authors the new (post-split) location.
    _add_commit(git_repo, "src/scistudio/api/runtime/_projects.py", message="pr: continue on new path")

    ledger = _ledger(
        branch="pr/x",
        declared_scope=DeclaredScope(include=["src/scistudio/api/runtime.py"]),  # stale literal path
    )
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="main", head="HEAD", mode="pre-push", run_checks=False
    )
    scope_findings = [f for f in result.report.findings if f.rule_id == "scope.out-of-scope"]
    assert scope_findings, "expected an advisory scope finding for the new path"
    assert all(f.severity == Severity.WARNING for f in scope_findings)
    assert "scope.out-of-scope" not in result.unsatisfied  # does NOT block


def test_1463_regular_out_of_scope_still_blocks(git_repo: Path) -> None:
    """Enforcement intact: a genuinely out-of-scope PR-authored file still blocks.

    (No merge, no rename, no integration record -> hard ERROR + unsatisfied.)
    """

    _git(git_repo, "checkout", "-q", "-b", "pr/x")
    _add_commit(git_repo, "src/scistudio/api/a.py", message="in scope")
    _add_commit(git_repo, "src/scistudio/secret/b.py", message="out of scope")
    ledger = _ledger(branch="pr/x", declared_scope=DeclaredScope(include=["src/scistudio/api/**"]))
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="main", head="HEAD", mode="pre-push", run_checks=False
    )
    blocking = [f for f in result.report.findings if f.rule_id == "scope.out-of-scope" and f.severity == Severity.ERROR]
    assert any(f.file == "src/scistudio/secret/b.py" for f in blocking)
    assert "scope.out-of-scope" in result.unsatisfied


# ---------------------------------------------------------------------------
# #1464 — local `ci` mode == CI "Verify Workflow Compliance" for issue_link
# + docs_landing (both call the same evaluator entry point post-Addendum-6).
# ---------------------------------------------------------------------------


def test_1464_ci_mode_fails_missing_issue(git_repo: Path) -> None:
    """ci mode fires issue_link.missing + issue.required when no issue is linked.

    (The old false-pass — local ``ci`` accepting a null/absent issue — is gone.)
    """

    _add_commit(git_repo, "src/scistudio/mod.py", message="change")
    ledger = _ledger(branch="main", declared_scope=DeclaredScope(include=["src/**"]))
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="ci",
        pr_body="no closing keyword",
        run_checks=False,
    )
    assert "issue.required" in result.unsatisfied
    assert "guard.issue_link" in result.unsatisfied


def test_1464_ci_mode_null_issue_url_is_valid(git_repo: Path) -> None:
    """A linked issue with ``url=None`` is VALID in ci mode (no invalid-record).

    CI used to fire "issue URL must be a string" on a null url; the guard now
    validates the URL shape only when a url is present, so a number-linked issue
    with no url is accepted.
    """

    _add_commit(git_repo, "src/scistudio/mod.py", message="change")
    ledger = _ledger(
        branch="main",
        issues=[IssueRef(number=200, url=None)],
        declared_scope=DeclaredScope(include=["src/**"]),
    )
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="ci",
        pr_body="Closes #200",
        run_checks=False,
    )
    assert "guard.issue_link" not in result.unsatisfied
    assert "issue.required" not in result.unsatisfied


def test_1464_ci_mode_fails_missing_docs_landing(git_repo: Path) -> None:
    """ci mode fires the docs_landing guard for a governed change with no docs/NA."""

    _add_commit(git_repo, "src/scistudio/mod.py", message="impl change, no docs")
    ledger = _ledger(
        branch="main",
        issues=[IssueRef(number=200)],
        declared_scope=DeclaredScope(include=["src/**"]),
    )
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="ci",
        pr_body="Closes #200",
        run_checks=False,
    )
    assert "guard.docs_landing" in result.unsatisfied


def test_1464_ci_mode_docs_satisfied_from_observed_diff(git_repo: Path) -> None:
    """ci mode accepts docs that LANDED in the diff without a declared docs_event.

    The workflow-gate validates docs from the observed diff (git is the evidence),
    so a changed docs file satisfies docs_landing in ci mode.
    """

    path = git_repo / "src/scistudio/mod.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("y\n", encoding="utf-8")
    (git_repo / "docs").mkdir(parents=True, exist_ok=True)
    (git_repo / "docs/change.md").write_text("doc\n", encoding="utf-8")
    test_dir = git_repo / "tests"
    test_dir.mkdir(parents=True, exist_ok=True)
    (test_dir / "test_mod.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _git(git_repo, "add", "-A")
    _commit(git_repo, message="impl + docs + test")
    ledger = _ledger(
        branch="main",
        issues=[IssueRef(number=200)],
        declared_scope=DeclaredScope(include=["src/**", "docs/**", "tests/**"]),
    )
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="ci",
        pr_body="Closes #200",
        run_checks=False,
    )
    assert "guard.docs_landing" not in result.unsatisfied
    assert "docs.docs_required_or_na" not in result.unsatisfied
    assert "tests.changed_test_required" not in result.unsatisfied


# ---------------------------------------------------------------------------
# #1345 — stacked-PR discovery (branch-scoped) + hook base resolution.
# ---------------------------------------------------------------------------


def test_1345_stacked_discovery_picks_child_record_not_umbrella(git_repo: Path) -> None:
    """With an umbrella + child record both in the diff, discovery picks the child.

    The pre-Addendum-6 ``_discover_gate_record`` returned None when >1 record was
    in the diff (the stacked-PR case). Branch-scoped discovery resolves the child
    branch's own record unambiguously.
    """

    _git(git_repo, "checkout", "-q", "-b", "umbrella/x")
    cli.main(
        [
            "--repo-root",
            str(git_repo),
            "init",
            "--task-kind",
            "manager",
            "--persona",
            "manager",
            "--runtime",
            "claude",
            "--branch",
            "umbrella/x",
            "--owner-directive",
            "umbrella",
            "--issue",
            "500",
            "--print-instructions",
            "false",
        ]
    )
    _git(git_repo, "add", "-A")
    _commit(git_repo, message="umbrella record")
    _git(git_repo, "checkout", "-q", "-b", "child/y")
    cli.main(
        [
            "--repo-root",
            str(git_repo),
            "init",
            "--task-kind",
            "bugfix",
            "--persona",
            "implementer",
            "--runtime",
            "claude",
            "--branch",
            "child/y",
            "--owner-directive",
            "child",
            "--issue",
            "501",
            "--print-instructions",
            "false",
        ]
    )
    _git(git_repo, "add", "-A")
    _commit(git_repo, message="child record")

    discovery = io.discover_ledger(git_repo)
    assert discovery.found
    assert discovery.path is not None
    assert discovery.path.name == "501-child-y.json"


HOOK_BASE_SNIPPET = r"""
import os
import re
import shlex

cmd = os.environ.get("SCISTUDIO_CMD", "")
try:
    tokens = shlex.split(cmd)
except ValueError:
    tokens = []

base = None
index = 0
while index < len(tokens):
    token = tokens[index]
    if token in {"--base", "-B"} and index + 1 < len(tokens):
        base = tokens[index + 1]
        break
    if token.startswith("--base="):
        base = token.split("=", 1)[1]
        break
    if token.startswith("-B="):
        base = token.split("=", 1)[1]
        break
    index += 1

if base is None:
    match = re.search(r"SCISTUDIO_GATE_BASE=([^\s#]+)", cmd)
    if match:
        base = match.group(1)

if base is None:
    base = os.environ.get("SCISTUDIO_ENV_BASE") or "origin/main"

base = base.strip()
if base and "/" not in base:
    base = f"origin/{base}"
elif base.startswith("origin/") or base.startswith("refs/"):
    pass
elif "/" in base and not base.startswith(("origin/", "upstream/", "refs/")):
    base = f"origin/{base}"
print(base)
"""


def _resolve_hook_base(cmd: str, env_base: str = "") -> str:
    """Mirror the check-gate-before-pr.sh base-resolution python block.

    Keeps a behavioural lock on the shell hook's base parsing (#1345) without
    requiring a full shell + git harness in unit tests. The snippet is byte-for-
    byte the logic embedded in the hook.
    """

    proc = subprocess.run(
        ["python", "-"],
        input=HOOK_BASE_SNIPPET,
        capture_output=True,
        text=True,
        env={**os.environ, "SCISTUDIO_CMD": cmd, "SCISTUDIO_ENV_BASE": env_base},
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_1345_hook_base_defaults_to_origin_main() -> None:
    assert _resolve_hook_base("gh pr create --title x --body y") == "origin/main"


def test_1345_hook_base_parses_stacked_target() -> None:
    assert _resolve_hook_base("gh pr create --base umbrella/x --title x") == "origin/umbrella/x"
    assert _resolve_hook_base("gh pr create --base=feature/z") == "origin/feature/z"
    assert _resolve_hook_base("gh pr create -B dev") == "origin/dev"


def test_1345_hook_base_command_token_override() -> None:
    # Env var does NOT propagate into the hook subprocess; the command-token
    # comment is the agent-side escape hatch.
    assert _resolve_hook_base("gh pr create --title x # SCISTUDIO_GATE_BASE=origin/foo") == "origin/foo"


def test_1345_hook_base_env_var_when_set() -> None:
    assert _resolve_hook_base("gh pr create --title x", env_base="origin/dev") == "origin/dev"


def test_1345_hook_base_explicit_remote_untouched() -> None:
    assert _resolve_hook_base("gh pr create --base origin/main") == "origin/main"


# ---------------------------------------------------------------------------
# #1283 — integration/umbrella (manager) records: no worker-scope false fail.
# ---------------------------------------------------------------------------


def test_1283_manager_record_downgrades_out_of_scope_to_warning(git_repo: Path) -> None:
    """A manager (integration) record does not hard-fail on files outside its
    declared worker scope: the integration PR spans every merged worker scope."""

    _git(git_repo, "checkout", "-q", "-b", "track/integration")
    _add_commit(git_repo, "src/scistudio/a.py", message="a")
    _add_commit(git_repo, "src/scistudio/b.py", message="b")
    ledger = _ledger(
        task_kind="manager",
        persona="manager",
        branch="track/integration",
        issues=[IssueRef(number=600)],
        declared_scope=DeclaredScope(include=["src/scistudio/a.py"]),  # narrow
    )
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=git_repo,
        base="main",
        head="HEAD",
        mode="ci",
        pr_body="Closes #600",
        run_checks=False,
    )
    scope_findings = [f for f in result.report.findings if f.rule_id == "scope.out-of-scope"]
    assert any(f.file == "src/scistudio/b.py" for f in scope_findings)
    assert all(f.severity == Severity.WARNING for f in scope_findings)
    assert "scope.out-of-scope" not in result.unsatisfied  # does NOT block


def test_1283_worker_record_still_enforces_scope(git_repo: Path) -> None:
    """A worker (non-manager) record on the SAME diff still hard-fails out-of-scope.

    Proves the downgrade is integration-specific and does not weaken worker PRs.
    """

    _git(git_repo, "checkout", "-q", "-b", "worker/y")
    _add_commit(git_repo, "src/scistudio/a.py", message="a")
    _add_commit(git_repo, "src/scistudio/b.py", message="b")
    ledger = _ledger(
        task_kind="bugfix",
        persona="implementer",
        branch="worker/y",
        issues=[IssueRef(number=601)],
        declared_scope=DeclaredScope(include=["src/scistudio/a.py"]),
    )
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=git_repo,
        base="main",
        head="HEAD",
        mode="ci",
        pr_body="Closes #601",
        run_checks=False,
    )
    blocking = [f for f in result.report.findings if f.rule_id == "scope.out-of-scope" and f.severity == Severity.ERROR]
    assert any(f.file == "src/scistudio/b.py" for f in blocking)
    assert "scope.out-of-scope" in result.unsatisfied
