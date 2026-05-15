"""Skeleton tests for ``scieasy.core.versioning.git_engine`` (ADR-039).

Phase D39-2.2a contributes these as xfail tests with detailed test-plan
docstrings. D39-2.2b flips them to passing once :class:`GitEngine` bodies
are implemented.

Each test exercises a happy path documented in the engine method's own
comment block; additional negative-path tests are listed under
"Test plan" in each docstring and should be added by D39-2.2b alongside
the implementation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Repository lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_init_creates_git_dir(tmp_path: Path) -> None:
    """init_repository creates a ``.git/`` directory.

    Steps:
    1. Construct ``GitEngine(tmp_path)``.
    2. Call ``engine.init_repository(tmp_path)``.
    3. Assert ``(tmp_path / ".git").is_dir()`` is True.
    """
    from scieasy.core.versioning.git_engine import GitEngine

    engine = GitEngine(tmp_path)
    engine.init_repository(tmp_path)
    assert (tmp_path / ".git").is_dir()


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_init_writes_default_gitignore(tmp_path: Path) -> None:
    """init_repository writes the default .gitignore per ADR §3.3.

    Verifies content matches DEFAULT_GITIGNORE constant exactly (line-by-line).
    """
    from scieasy.core.versioning.git_engine import GitEngine
    from scieasy.core.versioning.gitignore_template import DEFAULT_GITIGNORE

    GitEngine(tmp_path).init_repository(tmp_path)
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert content == DEFAULT_GITIGNORE


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_init_creates_initial_commit(tmp_path: Path) -> None:
    """init_repository produces a single initial commit with the canonical message."""
    from scieasy.core.versioning.git_engine import GitEngine

    engine = GitEngine(tmp_path)
    engine.init_repository(tmp_path)
    commits = engine.log()
    assert len(commits) == 1
    assert "Initial commit" in commits[0]["subject"]


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_is_repository_after_init(tmp_path: Path) -> None:
    """is_repository returns True after init."""
    from scieasy.core.versioning.git_engine import GitEngine

    engine = GitEngine(tmp_path)
    assert engine.is_repository(tmp_path) is False
    engine.init_repository(tmp_path)
    assert engine.is_repository(tmp_path) is True


# ---------------------------------------------------------------------------
# Commit / restore round-trip
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_commit_creates_new_sha(tmp_path: Path) -> None:
    """commit() produces a new SHA visible in log().

    Steps:
    1. init_repository.
    2. Write a new file ``workflows/main.yaml`` with content "foo".
    3. ``engine.commit("first edit")``.
    4. Assert returned SHA differs from initial commit's SHA.
    5. Assert ``engine.log()[0]["subject"] == "first edit"``.
    """
    raise NotImplementedError("D39-2.2b — see docstring for test plan")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_commit_with_auto_prefix(tmp_path: Path) -> None:
    """commit(prefix="auto") prepends "auto: " to the message."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_restore_round_trip(tmp_path: Path) -> None:
    """restore() returns a file to a prior commit's content.

    Steps:
    1. init + commit version A of file.
    2. Modify file to version B + commit.
    3. ``engine.restore(sha_of_A, files=["file.yaml"])``.
    4. Assert file content == A AND HEAD still points to commit B
       (soft restore default per §3.6).
    """
    raise NotImplementedError("D39-2.2b — see docstring")


# ---------------------------------------------------------------------------
# Branch ops
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_branch_create_switch_delete_cycle(tmp_path: Path) -> None:
    """Full branch CRUD: create, switch, delete.

    Steps:
    1. init + commit.
    2. ``engine.branch_create("feature")``.
    3. ``engine.branch_switch("feature")``.
    4. Assert ``engine.current_branch() == "feature"``.
    5. ``engine.branch_switch("main")``.
    6. ``engine.branch_delete("feature")``.
    7. Assert ``engine.branches()`` does not contain "feature".
    """
    raise NotImplementedError("D39-2.2b — see docstring")


# ---------------------------------------------------------------------------
# Status / head_state
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_status_clean_after_init(tmp_path: Path) -> None:
    """status() reports clean tree immediately after init."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_status_detects_modified_file(tmp_path: Path) -> None:
    """status() lists modified files."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_head_state_returns_sha_and_dirty(tmp_path: Path) -> None:
    """head_state() returns (commit_sha, dirty)."""
    raise NotImplementedError("D39-2.2b — see docstring")


# ---------------------------------------------------------------------------
# Merge / cherry-pick
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_merge_fast_forward(tmp_path: Path) -> None:
    """merge() returns result="fast-forward" when source is ahead."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_merge_clean_three_way(tmp_path: Path) -> None:
    """merge() returns result="clean" for divergent edits in different files."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_merge_conflict_path(tmp_path: Path) -> None:
    """merge() returns result="conflict" + conflicted_files when edits collide.

    Steps:
    1. init + commit baseline.
    2. Branch ``feature``, edit line 3 of file → commit.
    3. Switch to ``main``, edit same line 3 differently → commit.
    4. ``result = engine.merge("feature")``.
    5. Assert ``result == {"result": "conflict", "conflicted_files": [...]}``
       and the file is in ``status()["conflicted"]``.
    """
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_cherry_pick_clean(tmp_path: Path) -> None:
    """cherry_pick() onto non-conflicting target returns clean."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_cherry_pick_conflict_same_shape_as_merge(tmp_path: Path) -> None:
    """cherry_pick() conflict return shape matches merge() conflict."""
    raise NotImplementedError("D39-2.2b — see docstring")


# ---------------------------------------------------------------------------
# Stash CRUD
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_stash_save_apply_drop_cycle(tmp_path: Path) -> None:
    """Stash CRUD: save → list → apply → drop.

    Steps:
    1. init + commit, modify file.
    2. ``stash_id = engine.stash_save("WIP")``.
    3. Assert ``engine.status()["dirty"] is False``.
    4. ``engine.stash_apply(stash_id)``.
    5. Assert dirty again.
    6. ``engine.stash_drop(stash_id)``.
    7. Assert ``engine.stash_list() == []``.
    """
    raise NotImplementedError("D39-2.2b — see docstring")


# ---------------------------------------------------------------------------
# Conflict-resolution finalization
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_merge_stage_complete_round_trip(tmp_path: Path) -> None:
    """Full conflict path: merge → resolve → stage → complete.

    Steps:
    1. Set up conflict (as in test_merge_conflict_path).
    2. Manually rewrite conflicted file to a clean state.
    3. ``engine.merge_stage_file("file.yaml")``.
    4. ``sha = engine.merge_complete()``.
    5. Assert ``engine.log()[0]`` has two parents.
    """
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_merge_abort_restores_state(tmp_path: Path) -> None:
    """merge_abort() returns the working tree to pre-merge state."""
    raise NotImplementedError("D39-2.2b — see docstring")


# ---------------------------------------------------------------------------
# .gitignore template helper
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_write_default_gitignore_writes_template(tmp_path: Path) -> None:
    """write_default_gitignore writes DEFAULT_GITIGNORE when no file present."""
    from scieasy.core.versioning.gitignore_template import (
        DEFAULT_GITIGNORE,
        write_default_gitignore,
    )

    assert write_default_gitignore(tmp_path) is True
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == DEFAULT_GITIGNORE


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_write_default_gitignore_preserves_existing(tmp_path: Path) -> None:
    """write_default_gitignore is a no-op when a user .gitignore already exists."""
    from scieasy.core.versioning.gitignore_template import write_default_gitignore

    (tmp_path / ".gitignore").write_text("custom\n", encoding="utf-8")
    assert write_default_gitignore(tmp_path) is False
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "custom\n"
