"""Tests for ``scistudio.core.versioning.git_engine`` (ADR-039).

Phase D39-2.2b — bodies filled, xfail flipped to passing.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scistudio.core.versioning.git_engine import GitEngine, GitError


def _init_engine(tmp_path: Path) -> GitEngine:
    engine = GitEngine(tmp_path)
    engine.init_repository(tmp_path)
    return engine


# ---------------------------------------------------------------------------
# Regression: pair-cycle is gone (#1337)
# ---------------------------------------------------------------------------


def test_no_circular_import() -> None:
    """git_binary ↔ git_engine no longer have a circular dependency.

    Regression for #1337 (PR #1344): the pair previously relied on a lazy
    ``from scistudio.core.versioning.git_engine import GitError`` inside
    ``GitBinary.run`` AND a lazy ``from .git_binary import GitBinary``
    inside ``GitEngine._git``. The fix extracts ``GitError`` into
    ``scistudio.core.versioning.errors`` so both modules can use
    module-top imports.

    The test spawns a fresh interpreter and pre-registers a no-op shim
    in ``sys.modules`` for ``scistudio.core.versioning`` (with a real
    ``__path__`` so sibling submodules still resolve via the normal
    import system) BEFORE importing either cycle-pair submodule. This
    guarantees that the chosen "first" submodule really is the first one
    Python parses — otherwise a plain
    ``importlib.import_module("scistudio.core.versioning.<sub>")`` would
    trigger the real ``__init__.py`` first, which itself imports
    ``git_binary`` then ``git_engine`` in a fixed order and would
    collapse both branches into the same effective test (Codex P2 audit
    on PR #1348).
    """
    script = textwrap.dedent(
        """
        import importlib
        import sys
        import types
        from pathlib import Path

        order = sys.argv[1]
        package_dir = Path(sys.argv[2])

        # Pre-register a NO-OP package shim for scistudio.core.versioning
        # so that loading a submodule from its .py file does NOT trigger
        # the real scistudio/core/versioning/__init__.py (which imports
        # git_binary BEFORE git_engine and would defeat the order test).
        # We give the shim a __path__ pointing at the package dir so
        # Python's import machinery can still resolve sibling submodules
        # via the normal ``from .sibling import ...`` syntax inside each
        # module body.
        for parent_name, parent_path in [
            ("scistudio", None),
            ("scistudio.core", None),
            ("scistudio.core.versioning", str(package_dir)),
        ]:
            if parent_name not in sys.modules:
                shim = types.ModuleType(parent_name)
                if parent_path:
                    shim.__path__ = [parent_path]
                else:
                    shim.__path__ = []
                sys.modules[parent_name] = shim

        # errors.py is the shared shim. Pre-load it so the two cycle-pair
        # modules have an explicit dependency they can resolve via the
        # normal import system before we touch them.
        importlib.import_module("scistudio.core.versioning.errors")

        # The TRUE test of "no cycle" is whether git_binary can be loaded
        # without git_engine AND vice versa.  We load them in the order
        # requested directly from their .py files, BEFORE Python would
        # otherwise consult the package __init__ ordering.
        if order == "binary-first":
            importlib.import_module("scistudio.core.versioning.git_binary")
            importlib.import_module("scistudio.core.versioning.git_engine")
        else:
            importlib.import_module("scistudio.core.versioning.git_engine")
            importlib.import_module("scistudio.core.versioning.git_binary")

        # Smoke test the re-export contract: ``GitError`` must still resolve
        # via ``git_engine`` (the public surface used by api.routes.git).
        _E = sys.modules["scistudio.core.versioning.git_engine"].GitError
        assert _E.__module__ == "scistudio.core.versioning.errors", _E.__module__
        print("OK")
        """
    )
    # Locate the source files for the submodule .py paths.
    import scistudio.core.versioning as _versioning_pkg

    package_dir = Path(_versioning_pkg.__file__).parent
    for order in ("binary-first", "engine-first"):
        proc = subprocess.run(
            [sys.executable, "-c", script, order, str(package_dir)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, f"order={order} stderr={proc.stderr!r} stdout={proc.stdout!r}"
        assert "OK" in proc.stdout


# ---------------------------------------------------------------------------
# Repository lifecycle
# ---------------------------------------------------------------------------


def test_init_creates_git_dir(tmp_path: Path) -> None:
    engine = GitEngine(tmp_path)
    engine.init_repository(tmp_path)
    assert (tmp_path / ".git").is_dir()


def test_init_writes_default_gitignore(tmp_path: Path) -> None:
    from scistudio.core.versioning.gitignore_template import DEFAULT_GITIGNORE

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


# ---------------------------------------------------------------------------
# D39-3.2 (#968) P2-C: empty-repo edge case for ``commit()``.
#
# When a repo has no HEAD (freshly ``git init``-ed, never committed), the
# previous implementation used ``git diff --cached --quiet`` to detect an
# empty tree. Against a missing HEAD this plumbing returns 0 (no diff
# possible) even when the index has staged files — raising the
# misleading "nothing to commit" GitError for what is actually a valid
# initial commit. The fix branches on ``git rev-parse --verify HEAD`` and
# falls back to ``ls-files --cached`` when HEAD is absent.
# ---------------------------------------------------------------------------


def test_commit_first_commit_against_no_head(tmp_path: Path) -> None:
    """Initial commit on a freshly init'd repo (no HEAD yet) succeeds.

    Simulates the path where some external tool ran ``git init`` but the
    user clicks Run before SciStudio's auto-init has had a chance to seed
    the initial commit.
    """
    from scistudio.core.versioning.git_binary import GitBinary

    # Bare ``git init`` (no auto-gitignore, no initial commit). We can't
    # use ``GitEngine.init_repository`` here because it already makes the
    # initial commit.
    binary = GitBinary.locate()
    binary.run(["init", "--initial-branch=main", str(tmp_path)], cwd=tmp_path.parent)

    engine = GitEngine(tmp_path)
    # Stage a file so the index is non-empty.
    (tmp_path / "first.txt").write_text("hello", encoding="utf-8")

    # Pre-condition: there is no HEAD yet.
    head_check = engine._run(["rev-parse", "--verify", "-q", "HEAD"], check=False)
    assert head_check.returncode != 0, "expected no HEAD on fresh init"

    # The initial commit must succeed (no false-positive "nothing to commit").
    sha = engine.commit("first commit", prefix=None)
    assert sha
    log = engine.log()
    assert len(log) == 1
    assert log[0]["subject"] == "first commit"


def test_commit_no_head_with_empty_index_still_raises(tmp_path: Path) -> None:
    """No HEAD AND empty index → still raises ``nothing to commit``.

    The empty-repo fix must not turn into a false negative on a truly
    empty tree.
    """
    from scistudio.core.versioning.git_binary import GitBinary

    binary = GitBinary.locate()
    binary.run(["init", "--initial-branch=main", str(tmp_path)], cwd=tmp_path.parent)

    engine = GitEngine(tmp_path)
    # Don't write anything — index is empty.
    with pytest.raises(GitError):
        engine.commit("nothing here")


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


def test_restore_does_not_auto_handle_dirty_tree(tmp_path: Path) -> None:
    """ADR-039 Addendum 1 (#1354): the engine.restore method is now a
    pure soft restore — it does NOT auto-stash or auto-commit a dirty
    tree. The auto-commit responsibility lives at the route layer
    (``scistudio.api.routes.git::restore``). This test pins the engine
    contract: ``restore`` against a dirty tree either succeeds without
    creating a new commit (if git allows the checkout) or raises the
    raw ``GitError`` (which the route layer catches AFTER it has
    already auto-committed).
    """
    engine = _init_engine(tmp_path)
    target = tmp_path / "file.yaml"
    target.write_text("A", encoding="utf-8")
    sha_a = engine.commit("version A")
    target.write_text("B", encoding="utf-8")
    sha_b = engine.commit("version B")

    head_count_before = len(engine.log(limit=100))

    # Dirty an unrelated file. The hotfix #997 short-circuit applies
    # because the target file ('file.yaml') already matches sha_b on
    # disk, so engine.restore short-circuits to a no-op even though
    # `other.txt` is dirty.
    (tmp_path / "other.txt").write_text("dirty unrelated", encoding="utf-8")

    engine.restore(sha_b, files=["file.yaml"])

    # No new commits were created by engine.restore itself — confirms
    # the auto-handler is at the route layer, not the engine.
    head_count_after = len(engine.log(limit=100))
    assert head_count_after == head_count_before, (
        "engine.restore must not create commits — that responsibility "
        "moved to the route layer in ADR-039 Addendum 1 (#1354)."
    )
    # HEAD still at sha_b.
    assert engine.head_state().commit_sha == sha_b
    # The unrelated dirty file is still dirty (engine didn't stash it).
    assert engine.status()["dirty"] is True
    # Suppress unused-binding warning for the original sha.
    _ = sha_a


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
# commits_reachable_only_from / tag — ADR-039 Addendum 1 #1356
# ---------------------------------------------------------------------------


def _commit_file(engine: GitEngine, tmp_path: Path, name: str, content: str, message: str) -> str:
    """Write *name* with *content*, stage, and commit. Returns commit SHA."""
    (tmp_path / name).write_text(content, encoding="utf-8")
    engine._run(["add", "--", name])
    engine._run(
        [
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            message,
        ]
    )
    return engine.head_state().commit_sha


def test_commits_reachable_only_from_returns_branch_only_shas(tmp_path: Path) -> None:
    """A-B-C on main, A-B-D on feature → feature-only delete candidate = [D]."""
    engine = _init_engine(tmp_path)
    # _init_engine already creates an initial commit on main → that's A.
    sha_b = _commit_file(engine, tmp_path, "shared.txt", "shared", "B shared")
    # Create feature off B and add D.
    engine.branch_create("feature", base=sha_b)
    # Add C on main.
    _commit_file(engine, tmp_path, "main_only.txt", "C content", "C main")
    # Switch to feature and add D.
    engine.branch_switch("feature")
    sha_d = _commit_file(engine, tmp_path, "feature_only.txt", "D content", "D feature")
    # Switch back to main so feature can be deleted.
    engine.branch_switch("main")

    orphans = engine.commits_reachable_only_from("feature")

    assert orphans == [sha_d], "Only D is reachable only from feature; A, B, C are reachable via main."


def test_commits_reachable_only_from_merged_branch_returns_empty(tmp_path: Path) -> None:
    """A fully merged branch has no orphan candidates."""
    engine = _init_engine(tmp_path)
    engine.branch_create("temp")
    # No new commits on temp; HEAD is the same as main.
    orphans = engine.commits_reachable_only_from("temp")
    assert orphans == []


def test_commits_reachable_only_from_unknown_branch_returns_empty(tmp_path: Path) -> None:
    """A non-existent branch returns ``[]`` (caller handles delete error)."""
    engine = _init_engine(tmp_path)
    assert engine.commits_reachable_only_from("does-not-exist") == []


def test_tag_creates_ref_under_specified_namespace(tmp_path: Path) -> None:
    """``tag`` creates a ref under the caller-specified namespace via update-ref."""
    engine = _init_engine(tmp_path)
    sha = engine.head_state().commit_sha
    ref_name = f"refs/scistudio/lineage/{sha}"

    engine.tag(ref_name, sha)

    # Verify the ref exists and points at the SHA.
    proc = engine._run(["rev-parse", ref_name], check=False)
    assert proc.returncode == 0
    assert (proc.stdout or "").strip() == sha


def test_tag_is_idempotent(tmp_path: Path) -> None:
    """Re-running ``tag`` with the same name+SHA is a silent no-op."""
    engine = _init_engine(tmp_path)
    sha = engine.head_state().commit_sha
    ref_name = f"refs/scistudio/lineage/{sha}"

    engine.tag(ref_name, sha)
    engine.tag(ref_name, sha)  # Must not raise.

    proc = engine._run(["rev-parse", ref_name], check=False)
    assert proc.returncode == 0
    assert (proc.stdout or "").strip() == sha


def test_tag_stays_out_of_refs_tags(tmp_path: Path) -> None:
    """The ref namespace is hidden from ``refs/tags/`` so log chips don't show it."""
    engine = _init_engine(tmp_path)
    sha = engine.head_state().commit_sha
    engine.tag(f"refs/scistudio/lineage/{sha}", sha)

    # for-each-ref refs/tags/ must return nothing for the lineage ref.
    proc = engine._run(["for-each-ref", "--format=%(refname)", "refs/tags/"], check=False)
    tag_lines = (proc.stdout or "").strip().splitlines()
    assert all("scistudio" not in line for line in tag_lines), (
        f"refs/scistudio/lineage/* leaked into refs/tags/: {tag_lines}"
    )


def test_commits_reachable_only_from_disambiguates_branch_vs_tag(tmp_path: Path) -> None:
    """Codex P1 on PR #1381 — fully-qualified ref form on rev-list target.

    When a tag and a branch share the same short name, ``git rev-list
    <short>`` can resolve to either ref. The implementation passes
    ``refs/heads/<branch>`` explicitly to remove the ambiguity.
    Without the fix, the orphan-candidate set computed against the tag
    (which is reachable from main) would be empty, and the safety net
    would silently skip pinning the real branch-only commits.
    """
    engine = _init_engine(tmp_path)
    sha_b = _commit_file(engine, tmp_path, "shared.txt", "shared", "B shared")

    # Create a tag at B (the shared commit), THEN create a branch with the
    # same short name and add a unique commit on it.
    engine._run(["tag", "collision", sha_b])
    engine.branch_create("collision", base=sha_b)
    engine.branch_switch("collision")
    sha_d = _commit_file(engine, tmp_path, "branch_only.txt", "D", "D branch tip")
    engine.branch_switch("main")

    # The orphan set must be [sha_d] — the unique branch tip.
    # Without the fully-qualified-ref fix, rev-list would resolve
    # ``collision`` as the tag (at sha_b) and return [] because sha_b
    # is also reachable via main.
    orphans = engine.commits_reachable_only_from("collision")
    assert orphans == [sha_d], (
        f"Codex P1 regression: collision-named branch+tag returned {orphans!r}; "
        f"expected [{sha_d!r}]. rev-list likely resolved 'collision' as the tag."
    )


def test_commits_reachable_only_from_lineage_ref_excludes_pinned_sha(tmp_path: Path) -> None:
    """After ``tag`` pins a SHA, ``commits_reachable_only_from`` no longer reports it.

    This guarantees the safety net is idempotent: re-running on a branch
    whose orphans were already pinned returns ``[]`` so no duplicate
    ``update-ref`` calls happen (also harmless if they did — `update-ref`
    is overwrite-by-default).
    """
    engine = _init_engine(tmp_path)
    sha_b = _commit_file(engine, tmp_path, "shared.txt", "shared", "B shared")
    engine.branch_create("feature", base=sha_b)
    engine.branch_switch("feature")
    sha_d = _commit_file(engine, tmp_path, "feature_only.txt", "D", "D feature")
    engine.branch_switch("main")

    # First call — D is reported as orphan.
    assert engine.commits_reachable_only_from("feature") == [sha_d]

    # Pin D under the lineage ref namespace.
    engine.tag(f"refs/scistudio/lineage/{sha_d}", sha_d)

    # Second call — D is now reachable via the lineage ref, no longer reported.
    assert engine.commits_reachable_only_from("feature") == []


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


def test_merge_invalid_source_raises(tmp_path: Path) -> None:
    """merge() against a non-existent branch raises GitError, not conflict.

    Regression test for Codex P1 on PR #927: previously any exit-1 was
    misclassified as a conflict result.
    """
    engine = _init_engine(tmp_path)
    with pytest.raises(GitError):
        engine.merge("does-not-exist")


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
    from scistudio.core.versioning.gitignore_template import (
        DEFAULT_GITIGNORE,
        write_default_gitignore,
    )

    assert write_default_gitignore(tmp_path) is True
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == DEFAULT_GITIGNORE


def test_write_default_gitignore_preserves_existing(tmp_path: Path) -> None:
    from scistudio.core.versioning.gitignore_template import write_default_gitignore

    (tmp_path / ".gitignore").write_text("custom\n", encoding="utf-8")
    assert write_default_gitignore(tmp_path) is False
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "custom\n"


def test_write_default_gitignore_missing_path(tmp_path: Path) -> None:
    from scistudio.core.versioning.gitignore_template import write_default_gitignore

    with pytest.raises(FileNotFoundError):
        write_default_gitignore(tmp_path / "does-not-exist")


# ---------------------------------------------------------------------------
# status helpers
# ---------------------------------------------------------------------------


def test_is_dirty_status_helper(tmp_path: Path) -> None:
    from scistudio.core.versioning.status import is_dirty

    engine = _init_engine(tmp_path)
    assert is_dirty(tmp_path) is False
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    assert is_dirty(tmp_path) is True
    # Use engine to silence unused
    _ = engine.status()


def test_modified_files_status_helper(tmp_path: Path) -> None:
    from scistudio.core.versioning.status import modified_files

    _init_engine(tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    files = modified_files(tmp_path)
    assert "a.txt" in files
    assert "b.txt" in files


# ---------------------------------------------------------------------------
# Hotfix #983: subprocess UTF-8 decode regression
# ---------------------------------------------------------------------------


def test_git_binary_run_pins_utf8_decode() -> None:
    """Hotfix #983: ``GitBinary.run`` must pin ``encoding="utf-8"`` +
    ``errors="replace"`` on every text-mode ``subprocess.run`` call so git's
    UTF-8 stdout/stderr never gets decoded via the system locale (GBK on
    Chinese Windows, etc.). Pre-fix, a single em dash / Chinese char / emoji
    in a commit message crashed the subprocess reader thread with
    ``UnicodeDecodeError`` and the History panel rendered "No commits yet"
    on healthy repos.

    Source-level regression check — reads ``git_binary.py`` from disk
    directly. Mock-of-subprocess tests are unreliable under editable-install
    pollution where the imported module may not match the worktree's source.
    The contract being protected is "the kwargs we pass to ``subprocess.run``
    pin UTF-8", and that contract lives in the source file regardless of
    runtime import path.
    """
    # Read the source file from the worktree directly (not via import) so
    # this test is deterministic under editable-install pollution where the
    # imported module may not match the worktree's source on disk.
    repo_root = Path(__file__).resolve().parents[2]
    src_path = repo_root / "src" / "scistudio" / "core" / "versioning" / "git_binary.py"
    src = src_path.read_text(encoding="utf-8")
    assert 'encoding="utf-8" if text else None' in src, (
        "GitBinary.run must pin encoding='utf-8' for text-mode subprocess "
        "calls so non-GBK bytes in git output do not crash the reader "
        "thread on Chinese Windows (hotfix #983)."
    )
    assert '"replace" if text else None' in src, (
        "GitBinary.run must use errors='replace' as a defensive fallback "
        "for any unexpected non-UTF-8 byte (hotfix #983)."
    )
