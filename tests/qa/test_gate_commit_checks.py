"""Tests for the #2150 pre-PR replacements of the removed commit-time hooks.

`git commit` runs nothing anymore; the checks the commit hooks used to enforce
moved to the PR-gating evaluator modes:

- ``commit_hygiene`` runs the manual-stage pre-commit hygiene set
  (trailing-whitespace, end-of-file-fixer, check-yaml/json,
  check-added-large-files, check-merge-conflict, detect-private-key) in the
  local / pre-pr / ci modes — never in the (now hookless) commit modes;
- the final commit's Conventional Commits subject (previously the commitizen
  commit-msg hook) is validated natively at pre-pr / ci. Per the owner decision
  on #2150, only the FINAL commit is validated, not the whole branch range.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scistudio.qa.governance.gate_record import checks, evaluator
from scistudio.qa.governance.gate_record.ledger import GateLedger


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A throwaway git repo with one committed baseline."""

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "chore: base")
    return repo


def _commit(repo: Path, rel: str, message: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n", encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", message)


def _ledger() -> GateLedger:
    return GateLedger.model_validate(
        {
            "record_id": "2150-commit-hooks",
            "runtime": "claude-code",
            "task_kind": "maintenance",
            "persona": "implementer",
            "branch": "chore/2150-hooks",
            "owner_directive": "move commit checks to pre-pr",
            "issues": [{"number": 2150}],
        }
    )


def _reconcile(repo: Path, mode: str) -> evaluator.ReconcileResult:
    return evaluator.reconcile(
        ledger=_ledger(),
        repo_root=repo,
        base="HEAD~1",
        head="HEAD",
        mode=mode,  # type: ignore[arg-type]
        run_checks=False,
    )


# ---------------------------------------------------------------------------
# commit_hygiene check selection.
# ---------------------------------------------------------------------------


def test_commit_hygiene_catalog_entry_runs_the_manual_stage_hook_set() -> None:
    spec = checks.CHECK_CATALOG["commit_hygiene"]
    assert spec.command == ("pre-commit", "run", "--all-files", "--hook-stage", "manual")
    assert spec.covered_surface == "hygiene"


@pytest.mark.parametrize("mode", ["local", "pre-pr", "ci"])
def test_commit_hygiene_is_required_in_the_pr_gating_modes(git_repo: Path, mode: str) -> None:
    _commit(git_repo, "a.txt", "chore: add a")
    result = _reconcile(git_repo, mode)
    assert "commit_hygiene" in result.required_obligations.checks


@pytest.mark.parametrize("mode", ["pre-commit", "commit-msg", "pre-push"])
def test_commit_hygiene_never_runs_in_the_commit_modes(git_repo: Path, mode: str) -> None:
    _commit(git_repo, "a.txt", "chore: add a")
    result = _reconcile(git_repo, mode)
    assert "commit_hygiene" not in result.required_obligations.checks


# ---------------------------------------------------------------------------
# Final-commit message validation (commitizen replacement).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subject",
    [
        "feat(#2150): add the thing",
        "fix: plain scope-less subject",
        "chore(core)!: breaking change marker",
        "merge(#2017): combine origin/main into the branch",
        "docs: regenerate the api reference",
    ],
)
def test_commit_message_accepts_conventional_subjects(subject: str) -> None:
    assert evaluator.commit_message_problems(subject + "\n\nbody\n") == []


@pytest.mark.parametrize(
    "subject",
    [
        "",
        "wip",
        "add the thing",
        "Guided(#2150): capitalized type",
        "nonsense(#2150): unknown type",
        "fix(#2150) missing colon",
    ],
)
def test_commit_message_rejects_non_conventional_subjects(subject: str) -> None:
    assert evaluator.commit_message_problems(subject)


def test_pre_pr_flags_a_non_conventional_final_commit(git_repo: Path) -> None:
    _commit(git_repo, "a.txt", "wip: whatever")
    result = _reconcile(git_repo, "pre-pr")
    assert "commit_message.final" in result.unsatisfied


def test_pre_pr_accepts_a_conventional_final_commit(git_repo: Path) -> None:
    _commit(git_repo, "a.txt", "chore(#2150): move commit checks to pre-pr")
    result = _reconcile(git_repo, "pre-pr")
    assert "commit_message.final" not in result.unsatisfied


def test_local_mode_does_not_gate_the_commit_message(git_repo: Path) -> None:
    # `local` is the WIP-friendly preflight: the final commit message can still
    # be amended before the PR, so only the PR-gating modes enforce it.
    _commit(git_repo, "a.txt", "wip: whatever")
    result = _reconcile(git_repo, "local")
    assert "commit_message.final" not in result.unsatisfied
