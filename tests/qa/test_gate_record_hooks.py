"""Structural wiring tests for ADR-042 Addendum 6 hooks / CI / wrapper (spec §6).

Every enforcement surface collapses to one evaluator call: hooks, pre-commit,
and CI invoke ``gate_record check --mode <m>`` and forward the exit code. No hook
keeps a bypass vocabulary, a protected-path list, an issue-closing regex, or a
receipt-validate step. These tests assert the wiring shape (not behaviour, which
lives in the evaluator/guard tests): the new command names are used, the legacy
entry points are gone, the migrated label vocabulary is in place, the minimal
worktree-guard surface is wired, and ``.audit/`` is gitignored.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WRITE_GUARD_HOOK = REPO_ROOT / "scripts" / "hooks" / "check-worktree-write-guard.sh"


def _text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Single evaluator entry point + new command/mode names.
# ---------------------------------------------------------------------------


def test_push_hook_calls_evaluator_pre_push_mode() -> None:
    hook = _text("scripts/hooks/check-gate-before-push.sh")
    assert "scistudio.qa.governance.gate_record check" in hook
    assert "--mode pre-push" in hook
    # No legacy bypass vocabulary / receipt step / protected-path list inline.
    assert "admin-approved:ai-override" not in hook
    assert "SCISTUDIO_GATE_BYPASS_LABELS" not in hook
    assert "gate_receipt" not in hook
    assert "validate" not in hook.lower().replace("validate the adr-042", "")


def test_pr_hook_calls_evaluator_pre_pr_mode_with_body_file() -> None:
    hook = _text("scripts/hooks/check-gate-before-pr.sh")
    assert "scistudio.qa.governance.gate_record check" in hook
    assert "--mode pre-pr" in hook
    assert "--pr-body-file" in hook
    # The evaluator's pre-pr mode owns closing-keyword / label / bypass logic.
    assert "admin-approved:ai-override" not in hook
    assert "gate_receipt" not in hook


def test_pre_commit_config_exposes_thin_evaluator_hooks() -> None:
    config = yaml.safe_load(_text(".pre-commit-config.yaml"))
    local_repo = next(repo for repo in config["repos"] if repo["repo"] == "local")
    hooks = {hook["id"]: hook for hook in local_repo["hooks"]}

    assert hooks["scistudio-gate-record-pre-commit"]["entry"] == (
        "python scripts/hooks/run_python_module.py scistudio.qa.governance.gate_record check --mode pre-commit"
    )
    assert hooks["scistudio-gate-record-commit-msg"]["entry"] == (
        "python scripts/hooks/run_python_module.py scistudio.qa.governance.gate_record check --mode commit-msg"
    )
    assert hooks["scistudio-gate-record-commit-msg"]["stages"] == ["commit-msg"]


def test_pre_commit_local_hooks_use_src_layout_launcher() -> None:
    config = yaml.safe_load(_text(".pre-commit-config.yaml"))
    local_repo = next(repo for repo in config["repos"] if repo["repo"] == "local")
    for hook in local_repo["hooks"]:
        assert hook["entry"].startswith("python scripts/hooks/run_python_module.py ")


def test_git_pre_commit_wrapper_routes_through_gate_record() -> None:
    hook = _text(".workflow/hooks/pre-commit")
    assert 'scripts" / "hooks" / "run_python_module.py' in hook
    assert "scistudio.qa.governance.gate_record" in hook


def test_workflow_gate_ci_is_single_evaluator_ci_invocation() -> None:
    workflow = _text(".github/workflows/workflow-gate.yml")
    assert "scistudio.qa.governance.gate_record check" in workflow
    assert "--mode ci" in workflow
    assert "--pr-body-file" in workflow
    # The two legacy steps collapse into one evaluator call; no per-guard
    # orchestration code runs inline in the workflow YAML.
    assert "human_bypass_guard.check" not in workflow
    assert "core_change_guard.check" not in workflow
    assert "pr_merge_guard.check" not in workflow
    assert "mod_guard.PROTECTED_PATTERNS" not in workflow
    # The migrated label vocabulary (§4.2): the active label is admin-approved:bypass.
    # (The YAML may mention the old ai-override name only in a migration comment.)
    assert "admin-approved:bypass" in workflow


# ---------------------------------------------------------------------------
# Legacy entry points and state are gone.
# ---------------------------------------------------------------------------


def test_legacy_gate_py_removed() -> None:
    assert not (REPO_ROOT / ".workflow" / "gate.py").exists()


def test_legacy_active_workflow_state_removed() -> None:
    assert not (REPO_ROOT / ".workflow" / "active").exists()


def test_legacy_gate_receipt_module_removed() -> None:
    # Receipt behaviour folds into ledger check/reconcile events (ADR §3 step 8).
    assert not (REPO_ROOT / "src" / "scistudio" / "qa" / "governance" / "gate_receipt.py").exists()
    assert not (REPO_ROOT / "src" / "scistudio" / "qa" / "governance" / "workflow_gate.py").exists()


def test_no_hook_references_legacy_gate_py_or_active_state() -> None:
    for path in (
        "scripts/hooks/check-gate-before-push.sh",
        "scripts/hooks/check-gate-before-pr.sh",
        ".workflow/hooks/pre-commit",
        ".pre-commit-config.yaml",
        ".github/workflows/workflow-gate.yml",
    ):
        text = _text(path)
        assert ".workflow/gate.py" not in text
        assert ".workflow/active" not in text


# ---------------------------------------------------------------------------
# Minimal worktree write guard surface + repository hygiene.
# ---------------------------------------------------------------------------


def test_worktree_write_guard_uses_migrated_bypass_label() -> None:
    from scistudio.qa.governance import worktree_write_guard

    # §6.1: BROAD_OVERRIDE_LABELS migrated to admin-approved:bypass.
    assert "admin-approved:bypass" in worktree_write_guard.BROAD_OVERRIDE_LABELS
    assert "admin-approved:ai-override" not in worktree_write_guard.BROAD_OVERRIDE_LABELS


def test_audit_scratch_dir_is_gitignored() -> None:
    gitignore = _text(".gitignore")
    assert ".audit/" in gitignore
    # Raw transcripts live under .workflow/local/ and are never committed (§8).
    assert ".workflow/local/" in gitignore


# ---------------------------------------------------------------------------
# Behavioural execution of the worktree write guard hook script (#1523).
#
# The structural tests above only grep hook *text*. These tests actually run
# ``scripts/hooks/check-worktree-write-guard.sh`` with fabricated PreToolUse
# payloads against a real temp git repo + linked worktree, and assert BOTH the
# allow and deny paths including exit codes. A quoting/exit-code bug in the
# wrapper, or a payload parser that returned ``[]`` for every input (blocking
# nothing) or blocked everything, would be caught here — the previous suite let
# all of those pass silently.
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    # Disable commit signing / GPG and any user hooks so the fixture works in a
    # CI/dev environment that globally forces signed commits.
    subprocess.run(
        [
            "git",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _run_write_guard_hook(payload: dict, *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Execute the hook shell script with a JSON PreToolUse payload on stdin."""
    env = dict(os.environ)
    # Ensure the guard's ``python -m scistudio...`` import resolves regardless
    # of how the test runner set PYTHONPATH.
    src = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(
        ["sh", str(WRITE_GUARD_HOOK)],
        input=json.dumps(payload),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.fixture
def main_and_linked_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """Create a real git repo (main working tree) plus one linked worktree."""
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-b", "main")
    _git(main, "config", "user.email", "test@example.com")
    _git(main, "config", "user.name", "Test")
    (main / "README.md").write_text("seed\n", encoding="utf-8")
    _git(main, "add", "README.md")
    _git(main, "commit", "-m", "seed")

    linked = tmp_path / "linked"
    _git(main, "worktree", "add", "-b", "feature", str(linked))
    return main.resolve(), linked.resolve()


def test_write_guard_hook_allows_write_inside_linked_worktree(
    main_and_linked_worktree: tuple[Path, Path],
) -> None:
    """Positive control: an in-scope write into a linked worktree -> exit 0."""
    _main, linked = main_and_linked_worktree
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(linked / "src" / "new_module.py")},
        "cwd": str(linked),
    }
    result = _run_write_guard_hook(payload, cwd=linked)
    assert result.returncode == 0, (
        f"expected ALLOW (exit 0) for linked-worktree write; "
        f"got {result.returncode}\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
    )


def test_write_guard_hook_blocks_write_targeting_main_checkout(
    main_and_linked_worktree: tuple[Path, Path],
) -> None:
    """Negative control: a write targeting the MAIN working tree -> exit 2."""
    main, linked = main_and_linked_worktree
    payload = {
        "tool_name": "Edit",
        # Agent forgot to create a worktree: target resolves into the main tree.
        "tool_input": {"file_path": str(main / "src" / "leak.py")},
        # cwd is the linked worktree to prove the decision is path-based, not cwd-based.
        "cwd": str(linked),
    }
    result = _run_write_guard_hook(payload, cwd=linked)
    assert result.returncode == 2, (
        f"expected BLOCK (exit 2) for main-checkout write; "
        f"got {result.returncode}\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert "dedicated worktree" in result.stderr


def test_write_guard_hook_allows_bypass_label_for_main_checkout(
    main_and_linked_worktree: tuple[Path, Path],
) -> None:
    """A broad override label suppresses the block even for a main-tree write."""
    main, _linked = main_and_linked_worktree
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(main / "src" / "leak.py")},
        "cwd": str(main),
        "labels": ["admin-approved:bypass"],
    }
    result = _run_write_guard_hook(payload, cwd=main)
    assert result.returncode == 0, (
        f"expected ALLOW (exit 0) when bypass label present; "
        f"got {result.returncode}\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
