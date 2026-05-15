"""Tests for ``scieasy.core.versioning.git_engine`` (ADR-039).

Phase D39-2.2b — bodies filled, xfail flipped to passing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scieasy.core.versioning.git_engine import GitEngine, GitError


def _init_engine(tmp_path: Path) -> GitEngine:
    engine = GitEngine(tmp_path)
    engine.init_repository(tmp_path)
    return engine


# ---------------------------------------------------------------------------
# Repository lifecycle
# ---------------------------------------------------------------------------


def test_init_creates_git_dir(tmp_path: Path) -> None:
    engine = GitEngine(tmp_path)
    engine.init_repository(tmp_path)
    assert (tmp_path / ".git").is_dir()


def test_init_writes_default_gitignore(tmp_path: Path) -> None:
    from scieasy.core.versioning.gitignore_template import DEFAULT_GITIGNORE

    GitEngine(tmp_path).init_repository(tmp_path)
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert content == DEFAULT_GITIGNORE


def test_init_creates_initial_commit(tmp_path: Path) -> None:
    engine = GitEngine(tmp_path)
    engine.init_repository(tmp_path)
    commits = engine.log()
    assert len(commits) == 1
    assert "Initial commit" in commits[0]["subject"]


def test_init_double_raises(tmp_path: Path) -> None:
    engine = GitEngine(tmp_path)
    engine.init_repository(tmp_path)
    with pytest.raises(FileExistsError):
        engine.init_repository(tmp_path)


def test_is_repository_after_init(tmp_path: Path) -> None:
    engine = GitEngine(tmp_path)
    assert engine.is_repository(tmp_path) is False
    engine.init_repository(tmp_path)
    assert engine.is_repository(tmp_path) is True


def test_is_repository_handles_missing_path(tmp_path: Path) -> None:
    engine = GitEngine(tmp_path)
    assert engine.is_repository(tmp_path / "does-not-exist") is False


# ---------------------------------------------------------------------------
# Commit / restore round-trip
# ---------------------------------------------------------------------------


def test_commit_creates_new_sha(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    initial_sha = engine.log()[0]["sha"]
    (tmp_path / "workflows").mkdir(exist_ok=True)
    (tmp_path / "workflows" / "main.yaml").write_text("foo", encoding="utf-8")
    sha = engine.commit("first edit")
    assert sha != initial_sha
    assert engine.log()[0]["subject"] == "first edit"


def test_commit_with_auto_prefix(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    engine.commit("test", prefix="auto")
    assert engine.log()[0]["subject"] == "auto: test"


def test_commit_with_agent_prefix(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    engine.commit("did stuff", prefix="agent")
    assert engine.log()[0]["subject"] == "agent: did stuff"


def test_commit_empty_message_raises(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        engine.commit("")


def test_commit_clean_tree_raises(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    with pytest.raises(GitError):
        engine.commit("nothing to commit")


def test_commit_invalid_prefix_raises(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        engine.commit("msg", prefix="custom")


def test_restore_round_trip(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    target = tmp_path / "file.yaml"
    target.write_text("A", encoding="utf-8")
    sha_a = engine.commit("version A")
    target.write_text("B", encoding="utf-8")
    sha_b = engine.commit("version B")
    engine.restore(sha_a, files=["file.yaml"])
    assert target.read_text(encoding="utf-8") == "A"
    # HEAD still at B (soft restore).
    head_sha = engine.head_state().commit_sha
    assert head_sha == sha_b


# ---------------------------------------------------------------------------
# Branch ops
# ---------------------------------------------------------------------------


def test_branch_create_switch_delete_cycle(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    engine.branch_create("feature")
    engine.branch_switch("feature")
    assert engine.current_branch() == "feature"
    engine.branch_switch("main")
    engine.branch_delete("feature")
    names = [b["name"] for b in engine.branches()]
    assert "feature" not in names


def test_branch_delete_current_raises(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    with pytest.raises(GitError):
        engine.branch_delete("main")


def test_branches_current_first(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    engine.branch_create("alpha")
    engine.branch_create("zeta")
    branches = engine.branches()
    assert branches[0]["name"] == "main"
    assert branches[0]["is_current"] is True


# ---------------------------------------------------------------------------
# Status / head_state
# ---------------------------------------------------------------------------


def test_status_clean_after_init(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    s = engine.status()
    assert s["dirty"] is False
    assert s["modified"] == []
    assert s["staged"] == []
    assert s["untracked"] == []
    assert s["conflicted"] == []


def test_status_detects_modified_file(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    (tmp_path / ".gitignore").write_text("CHANGED\n", encoding="utf-8")
    s = engine.status()
    assert s["dirty"] is True
    assert ".gitignore" in s["modified"]


def test_status_detects_untracked(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    (tmp_path / "new.txt").write_text("hi", encoding="utf-8")
    s = engine.status()
    assert s["dirty"] is True
    assert "new.txt" in s["untracked"]


def test_head_state_returns_sha_and_dirty(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    state = engine.head_state()
    assert state.dirty is False
    assert len(state.commit_sha) == 40
    (tmp_path / "extra").write_text("x", encoding="utf-8")
    state2 = engine.head_state()
    assert state2.dirty is True


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def test_diff_commit_to_working(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    sha = engine.commit("add a")
    (tmp_path / "a.txt").write_text("two", encoding="utf-8")
    text = engine.diff(sha, "WORKING", files=["a.txt"])
    assert "one" in text or "+two" in text


def test_diff_commit_to_commit(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    sha1 = engine.commit("v1")
    (tmp_path / "a.txt").write_text("two", encoding="utf-8")
    sha2 = engine.commit("v2")
    text = engine.diff(sha1, sha2)
    assert "one" in text or "two" in text


# ---------------------------------------------------------------------------
# Merge / cherry-pick
# ---------------------------------------------------------------------------


def test_merge_fast_forward(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    engine.commit("add a")
    engine.branch_create("feature")
    engine.branch_switch("feature")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    engine.commit("add b")
    engine.branch_switch("main")
    result = engine.merge("feature")
    assert result["result"] == "fast-forward"
    assert result["conflicted_files"] == []


def test_merge_clean_three_way(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    engine.commit("add a")
    engine.branch_create("feature")
    engine.branch_switch("feature")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    engine.commit("add b")
    engine.branch_switch("main")
    (tmp_path / "c.txt").write_text("c", encoding="utf-8")
    engine.commit("add c")
    result = engine.merge("feature")
    assert result["result"] == "clean"
    assert result["conflicted_files"] == []


def test_merge_conflict_path(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    target = tmp_path / "a.txt"
    target.write_text("base", encoding="utf-8")
    engine.commit("baseline")
    engine.branch_create("feature")
    engine.branch_switch("feature")
    target.write_text("FEATURE", encoding="utf-8")
    engine.commit("feat change")
    engine.branch_switch("main")
    target.write_text("MAIN", encoding="utf-8")
    engine.commit("main change")
    result = engine.merge("feature")
    assert result["result"] == "conflict"
    assert "a.txt" in result["conflicted_files"]
    assert "a.txt" in engine.status()["conflicted"]
    engine.merge_abort()


def test_cherry_pick_clean(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    engine.commit("add a")
    engine.branch_create("feature")
    engine.branch_switch("feature")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    feat_sha = engine.commit("add b")
    engine.branch_switch("main")
    result = engine.cherry_pick(feat_sha)
    assert result["result"] == "clean"
    assert (tmp_path / "b.txt").exists()


def test_cherry_pick_conflict_same_shape_as_merge(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    target = tmp_path / "a.txt"
    target.write_text("base", encoding="utf-8")
    engine.commit("baseline")
    engine.branch_create("feature")
    engine.branch_switch("feature")
    target.write_text("FEATURE", encoding="utf-8")
    feat_sha = engine.commit("feat")
    engine.branch_switch("main")
    target.write_text("MAIN", encoding="utf-8")
    engine.commit("main")
    result = engine.cherry_pick(feat_sha)
    assert result["result"] == "conflict"
    assert "a.txt" in result["conflicted_files"]
    engine.merge_abort()


# ---------------------------------------------------------------------------
# Stash CRUD
# ---------------------------------------------------------------------------


def test_stash_save_apply_drop_cycle(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    engine.commit("add a")
    (tmp_path / "a.txt").write_text("dirty", encoding="utf-8")
    stash_id = engine.stash_save("WIP")
    assert engine.status()["dirty"] is False
    engine.stash_apply(stash_id)
    assert engine.status()["dirty"] is True
    engine.stash_drop(stash_id)
    assert engine.stash_list() == []


def test_stash_save_clean_tree_raises(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    with pytest.raises(GitError):
        engine.stash_save("WIP")


# ---------------------------------------------------------------------------
# Conflict-resolution finalization
# ---------------------------------------------------------------------------


def test_merge_stage_complete_round_trip(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    target = tmp_path / "a.txt"
    target.write_text("base\n", encoding="utf-8")
    engine.commit("baseline")
    engine.branch_create("feature")
    engine.branch_switch("feature")
    target.write_text("FEATURE\n", encoding="utf-8")
    engine.commit("feat")
    engine.branch_switch("main")
    target.write_text("MAIN\n", encoding="utf-8")
    engine.commit("main")
    engine.merge("feature")  # conflict
    # Resolve by rewriting cleanly.
    target.write_text("RESOLVED\n", encoding="utf-8")
    engine.merge_stage_file("a.txt")
    sha = engine.merge_complete()
    assert sha
    # log(branch="main") follows the HEAD branch only; the first entry is
    # the merge commit (with 2 parents). log(branch=None) → --all uses
    # date-order and may list ``feat`` first since it's a divergent tip.
    log = engine.log(branch="main")
    assert log[0]["sha"] == sha
    assert len(log[0]["parents"]) == 2


def test_merge_stage_file_with_markers_raises(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    target = tmp_path / "a.txt"
    target.write_text("<<<<<<<\nleft\n=======\nright\n>>>>>>>\n", encoding="utf-8")
    with pytest.raises(GitError):
        engine.merge_stage_file("a.txt")


def test_merge_abort_restores_state(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    target = tmp_path / "a.txt"
    target.write_text("base\n", encoding="utf-8")
    engine.commit("baseline")
    engine.branch_create("feature")
    engine.branch_switch("feature")
    target.write_text("FEATURE\n", encoding="utf-8")
    engine.commit("feat")
    engine.branch_switch("main")
    target.write_text("MAIN\n", encoding="utf-8")
    engine.commit("main")
    engine.merge("feature")
    engine.merge_abort()
    assert engine.status()["dirty"] is False
    assert not (tmp_path / ".git" / "MERGE_HEAD").exists()


def test_merge_abort_no_op_raises(tmp_path: Path) -> None:
    engine = _init_engine(tmp_path)
    with pytest.raises(GitError):
        engine.merge_abort()


# ---------------------------------------------------------------------------
# .gitignore template helper
# ---------------------------------------------------------------------------


def test_write_default_gitignore_writes_template(tmp_path: Path) -> None:
    from scieasy.core.versioning.gitignore_template import (
        DEFAULT_GITIGNORE,
        write_default_gitignore,
    )

    assert write_default_gitignore(tmp_path) is True
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == DEFAULT_GITIGNORE


def test_write_default_gitignore_preserves_existing(tmp_path: Path) -> None:
    from scieasy.core.versioning.gitignore_template import write_default_gitignore

    (tmp_path / ".gitignore").write_text("custom\n", encoding="utf-8")
    assert write_default_gitignore(tmp_path) is False
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "custom\n"


def test_write_default_gitignore_missing_path(tmp_path: Path) -> None:
    from scieasy.core.versioning.gitignore_template import write_default_gitignore

    with pytest.raises(FileNotFoundError):
        write_default_gitignore(tmp_path / "does-not-exist")


# ---------------------------------------------------------------------------
# status helpers
# ---------------------------------------------------------------------------


def test_is_dirty_status_helper(tmp_path: Path) -> None:
    from scieasy.core.versioning.status import is_dirty

    engine = _init_engine(tmp_path)
    assert is_dirty(tmp_path) is False
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    assert is_dirty(tmp_path) is True
    # Use engine to silence unused
    _ = engine.status()


def test_modified_files_status_helper(tmp_path: Path) -> None:
    from scieasy.core.versioning.status import modified_files

    _init_engine(tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    files = modified_files(tmp_path)
    assert "a.txt" in files
    assert "b.txt" in files
