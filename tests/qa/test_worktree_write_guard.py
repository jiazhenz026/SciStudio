"""Tests for the minimal worktree write guard (ADR-042 Addendum 6 §6.1).

The guard has exactly one job: block an AI write whose target resolves into the
MAIN (primary) git working tree — the "forgot to create a worktree" case. It
allows writes inside any linked worktree, writes outside any git repo, and never
requires a gate record to make the block decision. The decision must not depend
on the agent's cwd, only on whether the target resolves into the main checkout,
selecting the longest-matching registered worktree root.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scistudio.qa.governance.worktree_write_guard import (
    check_hook_payload,
    check_target,
    check_targets,
)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()


@pytest.fixture
def main_and_linked(tmp_path: Path) -> tuple[Path, Path]:
    """Create a main checkout plus one nested linked worktree.

    Layout::

        <tmp>/main                  (primary working tree, branch ``main``)
        <tmp>/main/.wt/feature      (linked worktree, branch ``feature``)

    The linked worktree is nested under the main checkout so the longest-match
    rule is exercised: a path under ``.wt/feature`` must resolve to the linked
    worktree, not the main checkout.
    """
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-b", "main")
    _git(main, "config", "user.email", "test@example.com")
    _git(main, "config", "user.name", "Test")
    (main / "README.md").write_text("seed\n", encoding="utf-8")
    _git(main, "add", "README.md")
    _git(main, "commit", "-m", "seed")

    linked = main / ".wt" / "feature"
    linked.parent.mkdir(parents=True, exist_ok=True)
    _git(main, "worktree", "add", "-b", "feature", str(linked))
    return main.resolve(), linked.resolve()


def test_blocks_write_into_main_working_tree(main_and_linked: tuple[Path, Path]) -> None:
    main, _linked = main_and_linked
    errors = check_target(main / "src" / "app.py")
    assert errors, "a write into the main working tree must be blocked"
    assert any("dedicated worktree" in error for error in errors)


def test_allows_write_into_linked_worktree(main_and_linked: tuple[Path, Path]) -> None:
    _main, linked = main_and_linked
    errors = check_target(linked / "src" / "app.py")
    assert errors == [], "a write inside a linked worktree must be allowed"


def test_longest_match_resolves_nested_linked_worktree(main_and_linked: tuple[Path, Path]) -> None:
    """A path under the nested linked worktree matches that worktree, not main."""
    _main, linked = main_and_linked
    # The linked worktree lives under the main checkout's tree; without
    # longest-match it would wrongly resolve to the main root and block.
    errors = check_target(linked / "deep" / "nested" / "file.py")
    assert errors == [], "longest-match must pick the nested linked worktree root"


def test_allows_path_outside_any_repo(tmp_path: Path) -> None:
    outside = tmp_path / "not-a-repo" / "memory.md"
    errors = check_target(outside)
    assert errors == [], "writes outside any git repo have no jurisdiction and are allowed"


def test_decision_independent_of_cwd(main_and_linked: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    """Blocking a main-tree write does not depend on the agent's cwd."""
    main, linked = main_and_linked
    # Even while "cwd" is the linked worktree, a target in the main tree blocks.
    monkeypatch.chdir(linked)
    errors = check_target(main / "src" / "app.py")
    assert errors, "main-tree target must block regardless of cwd"


def test_check_targets_aggregates_and_skips_blank(main_and_linked: tuple[Path, Path]) -> None:
    main, linked = main_and_linked
    errors = check_targets([str(main / "a.py"), "", str(linked / "b.py")])
    # Only the main-tree path contributes a finding; the linked + blank do not.
    assert len(errors) == 1


def test_hook_payload_blocks_main_tree(main_and_linked: tuple[Path, Path]) -> None:
    main, _linked = main_and_linked
    errors = check_hook_payload({"tool_input": {"file_path": str(main / "src" / "x.py")}})
    assert errors, "hook payload targeting the main tree must block"


def test_hook_payload_allows_linked_tree(main_and_linked: tuple[Path, Path]) -> None:
    _main, linked = main_and_linked
    errors = check_hook_payload({"tool_input": {"file_path": str(linked / "src" / "x.py")}})
    assert errors == []


def test_broad_override_label_suppresses_block(main_and_linked: tuple[Path, Path]) -> None:
    main, _linked = main_and_linked
    payload = {
        "tool_input": {"file_path": str(main / "src" / "x.py")},
        "labels": ["admin-approved:bypass"],
    }
    assert check_hook_payload(payload) == [], "broad override label suppresses the block (CI verifies provenance)"


def test_hook_payload_extracts_multiedit_paths(main_and_linked: tuple[Path, Path]) -> None:
    main, linked = main_and_linked
    payload = {
        "tool_input": {
            "edits": [
                {"file_path": str(linked / "ok.py")},
                {"file_path": str(main / "blocked.py")},
            ]
        }
    }
    errors = check_hook_payload(payload)
    assert len(errors) == 1, "only the main-tree edit target should block"
