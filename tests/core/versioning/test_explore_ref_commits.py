"""Explore-session commits written with git plumbing (ADR-054 spec 3, #2240).

Covers FR-028 to FR-031 and FR-036 of ``docs/specs/adr-054-explore-session.md``.

Almost every assertion here is about something that did **not** happen. An
Explore session commits after every cell run — roughly thirty commits an hour
— into a repository whose working tree a person is editing at the same time.
So the interesting properties are negative ones: the working tree does not
change, the real index does not change, staged work survives, ``HEAD`` does
not move, and ``git log <branch>`` never shows a single one of these commits.

Every test builds its own throwaway repository under ``tmp_path``. Nothing
here commits into the SciStudio repository itself.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from scistudio.core.versioning import _commit_ops
from scistudio.core.versioning.errors import GitError
from scistudio.core.versioning.git_engine import GitEngine

_NOTEBOOK = "explore/analysis.ipynb"


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def engine(tmp_path: Path) -> GitEngine:
    """A fresh throwaway repository with one commit and one tracked file."""
    repo = tmp_path / "project"
    repo.mkdir()
    (repo / "workflow.json").write_text('{"blocks": []}\n', encoding="utf-8")
    git_engine = GitEngine(repo)
    git_engine.init_repository(repo)
    return git_engine


def _git(engine: GitEngine, *args: str) -> str:
    """Run a read-only git command in *engine*'s repository and return stdout."""
    return str(engine._run(list(args)).stdout).strip()


def _blob_bytes(engine: GitEngine, rev: str, path: str) -> bytes:
    """Return the exact bytes recorded at *path* in *rev*."""
    proc = engine._git.run(
        ["cat-file", "blob", f"{rev}:{path}"],
        cwd=engine.project_path,
        text=False,
    )
    return bytes(proc.stdout)


def _tree_paths(engine: GitEngine, rev: str) -> list[str]:
    """Return every path recorded in *rev*'s tree, recursively."""
    listing = _git(engine, "ls-tree", "-r", "--name-only", rev)
    return sorted(line for line in listing.splitlines() if line)


def _index_bytes(engine: GitEngine) -> bytes:
    """Return the raw bytes of the repository's real index file."""
    return (engine.project_path / ".git" / "index").read_bytes()


def _worktree_snapshot(engine: GitEngine) -> dict[str, bytes]:
    """Return every non-``.git`` file in the working tree with its content."""
    snapshot: dict[str, bytes] = {}
    for path in sorted(engine.project_path.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(engine.project_path).as_posix()
        if relative.startswith(".git/"):
            continue
        snapshot[relative] = path.read_bytes()
    return snapshot


def _spy_on_git(engine: GitEngine, monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record every git argv the engine runs, and keep running them for real."""
    binary = engine._git
    real_run = binary.run
    recorded: list[list[str]] = []

    def spy(args: list[str], **kwargs: object) -> object:
        recorded.append(list(args))
        return real_run(args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(binary, "run", spy)
    return recorded


def _subcommands(recorded: list[list[str]]) -> list[str]:
    """Return the git subcommand of each recorded argv, skipping ``-c`` pairs."""
    names: list[str] = []
    for argv in recorded:
        index = 0
        while index < len(argv) and argv[index] == "-c":
            index += 2
        if index < len(argv):
            names.append(argv[index])
    return names


# ---------------------------------------------------------------------------
# The ref namespace (FR-028)
# ---------------------------------------------------------------------------


def test_session_ref_sits_under_the_dedicated_namespace() -> None:
    """A session's ref is ``refs/scistudio/explore/<id>`` — never a branch."""
    ref = _commit_ops._explore_session_ref("s-2026-09-04-abc123")
    assert ref == "refs/scistudio/explore/s-2026-09-04-abc123"
    assert not ref.startswith("refs/heads/")


@pytest.mark.parametrize(
    "session_id",
    [
        "",
        "-leading-dash",
        ".leading-dot",
        "has space",
        "has/slash",
        "has..dots",
        "trailing.",
        "session.lock",
        "tilde~1",
        "caret^1",
        "colon:name",
        "question?",
        "star*",
        "open[bracket",
        "back\\slash",
        "at{brace",
    ],
)
def test_session_ref_refuses_ids_git_would_refuse(session_id: str) -> None:
    """FR-001's id rule is enforced here too, so no bad id reaches ``update-ref``."""
    with pytest.raises(ValueError):
        _commit_ops._explore_session_ref(session_id)


# ---------------------------------------------------------------------------
# The commit itself (FR-028, FR-029)
# ---------------------------------------------------------------------------


def test_commit_lands_on_the_ref_with_the_exact_content(engine: GitEngine) -> None:
    """One call writes one commit whose tree carries exactly the bytes given."""
    ref = _commit_ops._explore_session_ref("s1")
    content = b'{"cells": [], "nbformat": 4}\n'

    sha = _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: content}, "cell run 1")

    assert _git(engine, "rev-parse", ref) == sha
    assert _blob_bytes(engine, sha, _NOTEBOOK) == content
    assert _git(engine, "log", "-1", "--format=%s", sha) == "cell run 1"


def test_commit_tree_holds_only_the_entries_given(engine: GitEngine) -> None:
    """The session ref carries the notebook, not a copy of the whole project."""
    ref = _commit_ops._explore_session_ref("s1")

    sha = _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: b"one"}, "cell run 1")

    assert _tree_paths(engine, sha) == [_NOTEBOOK]
    # The branch still has the project files the session never mentioned.
    assert "workflow.json" in _tree_paths(engine, "HEAD")


def test_each_call_is_exactly_one_commit_carrying_its_own_content(engine: GitEngine) -> None:
    """Five runs produce five commits, each with the content of that run."""
    ref = _commit_ops._explore_session_ref("s1")
    shas = [
        _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: f"run {n}".encode()}, f"cell run {n}")
        for n in range(5)
    ]

    assert len(set(shas)) == 5
    assert _git(engine, "rev-list", "--count", ref) == "5"
    assert _git(engine, "rev-parse", ref) == shas[-1]
    for n, sha in enumerate(shas):
        assert _blob_bytes(engine, sha, _NOTEBOOK) == f"run {n}".encode()


def test_commits_chain_onto_the_previous_ref_tip(engine: GitEngine) -> None:
    """The second commit is parented on the first, so the ref is a history."""
    ref = _commit_ops._explore_session_ref("s1")
    first = _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: b"one"}, "cell run 1")
    second = _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: b"two"}, "cell run 2")

    assert _git(engine, "rev-list", "--parents", "-1", second).split() == [second, first]
    assert _git(engine, "rev-list", "--parents", "-1", first).split() == [first]


def test_content_is_committed_verbatim_under_autocrlf(engine: GitEngine) -> None:
    """``--no-filters`` keeps line endings out of git's hands.

    With ``core.autocrlf=true`` a normal ``git add`` would rewrite CRLF to LF
    on the way in. A notebook is JSON whose bytes the session hashes and
    replays, so any rewrite corrupts it.
    """
    engine._run(["config", "core.autocrlf", "true"])
    ref = _commit_ops._explore_session_ref("s1")
    crlf = b'{"cells": [],\r\n "nbformat": 4}\r\n'

    sha = _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: crlf}, "cell run 1")

    assert _blob_bytes(engine, sha, _NOTEBOOK) == crlf


def test_binary_content_survives_the_round_trip(engine: GitEngine) -> None:
    """Bytes that are not valid UTF-8 are stored unchanged."""
    ref = _commit_ops._explore_session_ref("s1")
    payload = bytes(range(256))

    sha = _commit_ops._commit_entries_to_ref(engine, ref, {"explore/out.bin": payload}, "cell run 1")

    assert _blob_bytes(engine, sha, "explore/out.bin") == payload


def test_multiple_entries_land_in_one_commit(engine: GitEngine) -> None:
    """A caller passing several paths gets one commit containing all of them."""
    ref = _commit_ops._explore_session_ref("s1")
    entries = {_NOTEBOOK: b"nb", "explore/env.json": b"env", "explore/nested/deep.txt": b"deep"}

    sha = _commit_ops._commit_entries_to_ref(engine, ref, entries, "cell run 1")

    assert _tree_paths(engine, sha) == sorted(entries)
    assert _git(engine, "rev-list", "--count", ref) == "1"


# ---------------------------------------------------------------------------
# What did NOT happen (FR-029)
# ---------------------------------------------------------------------------


def test_thirty_commits_leave_the_working_tree_and_index_untouched(engine: GitEngine) -> None:
    """The load-bearing test: an hour of session commits disturbs nothing.

    Captures the real index, the working tree, ``HEAD``, and the branch log
    before a burst of commits and asserts every one of them is byte-identical
    afterwards. The index is read directly rather than through ``git status``,
    because ``git status`` itself refreshes the index's stat cache and would
    mask a real write.
    """
    ref = _commit_ops._explore_session_ref("s1")

    index_before = _index_bytes(engine)
    worktree_before = _worktree_snapshot(engine)
    head_before = _git(engine, "rev-parse", "HEAD")
    branch_log_before = _git(engine, "log", "--format=%H", "main")

    shas = [
        _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: f"run {n}".encode()}, f"cell run {n}")
        for n in range(30)
    ]

    assert _index_bytes(engine) == index_before
    assert _worktree_snapshot(engine) == worktree_before
    assert _git(engine, "rev-parse", "HEAD") == head_before
    assert _git(engine, "log", "--format=%H", "main") == branch_log_before
    assert _git(engine, "status", "--porcelain") == ""
    assert _git(engine, "rev-list", "--count", ref) == "30"
    assert len(set(shas)) == 30


def test_staged_work_survives_the_session_commits(engine: GitEngine) -> None:
    """A person's staged changes are still staged after the session commits.

    This is what a shared index would destroy. ``git add`` on the session's
    behalf would fold the person's staged edit into the session's commit and
    then clear it.
    """
    (engine.project_path / "notes.md").write_text("staged edit\n", encoding="utf-8")
    engine._run(["add", "notes.md"])
    staged_before = _git(engine, "diff", "--cached", "--name-only")
    assert staged_before == "notes.md"

    ref = _commit_ops._explore_session_ref("s1")
    for n in range(3):
        _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: f"run {n}".encode()}, f"cell run {n}")

    assert _git(engine, "diff", "--cached", "--name-only") == "notes.md"
    assert (engine.project_path / "notes.md").read_text(encoding="utf-8") == "staged edit\n"


def test_the_notebook_never_appears_in_the_working_tree(engine: GitEngine) -> None:
    """Committing a path does not create that path on disk."""
    ref = _commit_ops._explore_session_ref("s1")
    _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: b"one"}, "cell run 1")

    assert not (engine.project_path / "explore").exists()
    assert _git(engine, "status", "--porcelain") == ""


def test_the_branch_log_never_sees_the_session_commits(engine: GitEngine) -> None:
    """FR-030's promise: the branch stays clean until someone commits explicitly."""
    ref = _commit_ops._explore_session_ref("s1")
    shas = [
        _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: f"run {n}".encode()}, f"cell run {n}")
        for n in range(3)
    ]

    branch_log = _git(engine, "log", "--format=%H", "main").splitlines()
    for sha in shas:
        assert sha not in branch_log
        assert _git(engine, "branch", "--contains", sha) == ""
    assert _git(engine, "branch", "--list", "--format=%(refname)") == "refs/heads/main"


def test_the_plumbing_path_never_runs_a_working_tree_command(
    engine: GitEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Structural guard: no ``add``, ``commit``, ``checkout``, ``reset`` or ``stash``.

    A future edit that reached for porcelain would pass the behavioural tests
    on a quiet repository and fail on a busy one. This catches it at the
    invocation.
    """
    ref = _commit_ops._explore_session_ref("s1")
    recorded = _spy_on_git(engine, monkeypatch)

    _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: b"one"}, "cell run 1")

    used = _subcommands(recorded)
    assert not ({"add", "commit", "checkout", "reset", "stash", "restore", "switch"} & set(used))
    assert used == [
        "rev-parse",
        "hash-object",
        "update-index",
        "write-tree",
        "commit-tree",
        "update-ref",
        "rev-list",
    ]


def test_the_temporary_index_is_used_and_removed(engine: GitEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """``update-index`` and ``write-tree`` run against ``GIT_INDEX_FILE``.

    And the file it names is gone once the call returns, so a burst of runs
    does not leave a temporary index per commit behind.
    """
    ref = _commit_ops._explore_session_ref("s1")
    binary = engine._git
    real_run = binary.run
    index_files: list[str] = []

    def spy(args: list[str], **kwargs: object) -> object:
        env = kwargs.get("env") or {}
        assert isinstance(env, dict)
        subcommand = args[0]
        if subcommand in {"update-index", "write-tree"}:
            assert "GIT_INDEX_FILE" in env, f"{subcommand} ran against the repository's real index"
            index_files.append(env["GIT_INDEX_FILE"])
        return real_run(args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(binary, "run", spy)
    _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: b"one"}, "cell run 1")

    assert len(index_files) == 2
    assert len(set(index_files)) == 1
    used_index = Path(index_files[0])
    assert used_index.resolve() != (engine.project_path / ".git" / "index").resolve()
    assert not used_index.exists()


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_refuses_to_write_a_branch_ref(engine: GitEngine) -> None:
    """The plumbing path is not a back door onto ``refs/heads/``."""
    with pytest.raises(ValueError, match="refs/scistudio/"):
        _commit_ops._commit_entries_to_ref(engine, "refs/heads/main", {_NOTEBOOK: b"x"}, "nope")
    assert _git(engine, "log", "--format=%s", "main") == "Initial commit (auto-generated by SciStudio)"


@pytest.mark.parametrize(
    "ref",
    ["refs/tags/v1", "HEAD", "refs/remotes/origin/main", "main", "refs/scistudioX/explore/s1"],
)
def test_refuses_every_ref_outside_the_namespace(engine: GitEngine, ref: str) -> None:
    """Only ``refs/scistudio/`` is writable through this path."""
    with pytest.raises(ValueError, match="refs/scistudio/"):
        _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: b"x"}, "nope")


def test_refuses_an_empty_commit(engine: GitEngine) -> None:
    """No entries means there is nothing to record."""
    ref = _commit_ops._explore_session_ref("s1")
    with pytest.raises(ValueError, match="at least one path"):
        _commit_ops._commit_entries_to_ref(engine, ref, {}, "nope")


@pytest.mark.parametrize("message", ["", "   ", "\n"])
def test_refuses_an_empty_message(engine: GitEngine, message: str) -> None:
    """Matches :func:`_commit`'s rule so both commit paths behave alike."""
    ref = _commit_ops._explore_session_ref("s1")
    with pytest.raises(ValueError, match="must not be empty"):
        _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: b"x"}, message)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "   ",
        "/absolute/path.ipynb",
        "../escape.ipynb",
        "explore/../../escape.ipynb",
        "./relative.ipynb",
        ".git/config",
        "explore/.git/config",
        ".GIT/hooks/pre-commit",
        "explore\\windows.ipynb",
        "C:/absolute.ipynb",
        "explore//double.ipynb",
        "explore/null\x00.ipynb",
        "explore/tab\t.ipynb",
    ],
)
def test_refuses_unsafe_entry_paths(engine: GitEngine, path: str) -> None:
    """A path that escapes the repository, or reaches into ``.git``, is refused."""
    ref = _commit_ops._explore_session_ref("s1")
    with pytest.raises(ValueError):
        _commit_ops._commit_entries_to_ref(engine, ref, {path: b"x"}, "cell run 1")
    assert _commit_ops._resolve_ref(engine, ref) is None


def test_a_racing_writer_loses_the_compare_and_swap(engine: GitEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """``update-ref`` is given the old value, so a lost update is impossible.

    Simulated by handing the call a stale view of the ref: the swap must fail
    rather than overwrite the commit the other writer landed.
    """
    ref = _commit_ops._explore_session_ref("s1")
    first = _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: b"one"}, "cell run 1")
    second = _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: b"two"}, "cell run 2")

    monkeypatch.setattr(_commit_ops, "_resolve_ref", lambda _engine, _ref: first)
    with pytest.raises(GitError):
        _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: b"three"}, "cell run 3")

    assert _git(engine, "rev-parse", ref) == second


# ---------------------------------------------------------------------------
# Packing (FR-031)
# ---------------------------------------------------------------------------


def _pack_files(engine: GitEngine) -> list[Path]:
    return sorted((engine.project_path / ".git" / "objects" / "pack").glob("*.pack"))


def test_packing_fires_at_the_bound_and_not_before(engine: GitEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """With a bound of three, commits one and two pack nothing; the third packs."""
    ref = _commit_ops._explore_session_ref("s1")
    recorded = _spy_on_git(engine, monkeypatch)

    for n in range(2):
        _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: f"run {n}".encode()}, "run", pack_every=3)
    assert "repack" not in _subcommands(recorded)
    assert _pack_files(engine) == []

    _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: b"run 2"}, "run", pack_every=3)
    assert _subcommands(recorded).count("repack") == 1
    assert len(_pack_files(engine)) == 1


def test_packing_fires_again_at_the_next_multiple(engine: GitEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """The bound is periodic, not a one-shot."""
    ref = _commit_ops._explore_session_ref("s1")
    recorded = _spy_on_git(engine, monkeypatch)

    for n in range(6):
        _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: f"run {n}".encode()}, "run", pack_every=3)

    assert _subcommands(recorded).count("repack") == 2


def test_packing_counts_the_ref_not_the_process(engine: GitEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """A restarted session packs at the next multiple, not three commits later.

    The count comes from ``git rev-list --count <ref>``, so it survives the
    process that wrote the earlier commits.
    """
    ref = _commit_ops._explore_session_ref("s1")
    for n in range(2):
        _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: f"run {n}".encode()}, "run", pack_every=3)

    # A "new process": a fresh engine over the same repository.
    reopened = GitEngine(engine.project_path)
    recorded = _spy_on_git(reopened, monkeypatch)
    _commit_ops._commit_entries_to_ref(reopened, ref, {_NOTEBOOK: b"run 2"}, "run", pack_every=3)

    assert _subcommands(recorded).count("repack") == 1


@pytest.mark.parametrize("pack_every", [None, 0])
def test_packing_can_be_disabled(engine: GitEngine, monkeypatch: pytest.MonkeyPatch, pack_every: int | None) -> None:
    """A caller that packs on its own schedule can turn the trigger off."""
    ref = _commit_ops._explore_session_ref("s1")
    recorded = _spy_on_git(engine, monkeypatch)

    for n in range(4):
        _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: f"run {n}".encode()}, "run", pack_every=pack_every)

    assert "repack" not in _subcommands(recorded)
    assert "rev-list" not in _subcommands(recorded)


def test_the_default_bound_is_explicit_and_far_below_gits_own(engine: GitEngine) -> None:
    """The default exists because git's automatic threshold is too far away."""
    assert _commit_ops._EXPLORE_PACK_INTERVAL == 256
    # git's gc.auto default is 6700 loose objects; ours must fire well before.
    assert _commit_ops._EXPLORE_PACK_INTERVAL < 6700


def test_forced_packing_packs_loose_objects(engine: GitEngine) -> None:
    """The explicit trigger is callable on its own and reports success."""
    ref = _commit_ops._explore_session_ref("s1")
    _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: b"one"}, "run", pack_every=None)
    assert _pack_files(engine) == []

    assert _commit_ops._pack_explore_objects(engine) is True

    assert len(_pack_files(engine)) == 1
    # Packing must not lose the commit it just packed.
    assert _blob_bytes(engine, ref, _NOTEBOOK) == b"one"


def test_a_failed_pack_is_reported_not_raised(
    engine: GitEngine, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """FR-030: nothing in this path may take a session down. Packing included."""
    failure = subprocess.CompletedProcess(args=["git", "repack"], returncode=1, stdout="", stderr="disk full")
    monkeypatch.setattr(engine, "_run", lambda *_a, **_k: failure)

    with caplog.at_level("WARNING"):
        assert _commit_ops._pack_explore_objects(engine) is False

    assert "repack failed" in caplog.text


def test_a_failed_pack_does_not_fail_the_commit(engine: GitEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """The commit is already written when packing runs; a pack failure is not its problem."""
    ref = _commit_ops._explore_session_ref("s1")
    monkeypatch.setattr(_commit_ops, "_pack_explore_objects", lambda _engine: False)

    sha = _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: b"one"}, "run", pack_every=1)

    assert _git(engine, "rev-parse", ref) == sha


# ---------------------------------------------------------------------------
# The explicit branch commit (FR-036)
# ---------------------------------------------------------------------------


def test_branch_commit_moves_the_branch_and_keeps_the_rest_of_the_tree(engine: GitEngine) -> None:
    """The notebook joins the branch without disturbing the project's files."""
    head_before = _git(engine, "rev-parse", "HEAD")

    sha = _commit_ops._commit_entries_to_branch(engine, {_NOTEBOOK: b"stripped"}, "Save notebook")

    assert _git(engine, "rev-parse", "HEAD") == sha
    assert _git(engine, "rev-parse", "refs/heads/main") == sha
    assert _git(engine, "rev-list", "--parents", "-1", sha).split() == [sha, head_before]
    assert _tree_paths(engine, sha) == sorted([".gitignore", _NOTEBOOK, "workflow.json"])
    assert _blob_bytes(engine, sha, _NOTEBOOK) == b"stripped"
    assert _blob_bytes(engine, sha, "workflow.json") == b'{"blocks": []}\n'


def test_branch_commit_leaves_the_working_tree_and_staged_work_alone(engine: GitEngine) -> None:
    """The branch advances; the person's files and staged work do not move.

    The bytes committed are the caller's stripped notebook, not the file on
    disk, which keeps its outputs (FR-027). Staging the on-disk file would
    commit the wrong content, and ``git commit`` would sweep up the person's
    unrelated staged edit.
    """
    (engine.project_path / "notes.md").write_text("staged edit\n", encoding="utf-8")
    engine._run(["add", "notes.md"])
    worktree_before = _worktree_snapshot(engine)

    _commit_ops._commit_entries_to_branch(engine, {_NOTEBOOK: b"stripped"}, "Save notebook")

    assert _worktree_snapshot(engine) == worktree_before
    # notes.md is still staged, and nothing else joined it.
    assert _git(engine, "diff", "--cached", "--name-only") == "notes.md"


def test_branch_commit_does_not_leave_a_staged_deletion_behind(engine: GitEngine) -> None:
    """The real index follows the branch, or the person's next commit reverts this one.

    **Do not "simplify" the real-index write out of**
    :func:`_commit_ops._commit_entries_to_branch`. **This test is what stands
    between that edit and data loss**, and it caught the bug in the first
    draft of that function.

    The index is a cache of ``HEAD`` plus what is staged. Every other function
    in this file is careful *not* to touch it, so removing the one write that
    does looks like a tidy-up. It is not. Move ``HEAD`` forward while the
    index still describes the old commit and git reads the difference as a
    staged deletion of the notebook: ``git status`` shows ``deleted:
    explore/analysis.ipynb`` in the "changes to be committed" section, and the
    person's next ``git commit`` — for something else entirely — silently
    removes from the branch the notebook this call just saved.
    """
    _commit_ops._commit_entries_to_branch(engine, {_NOTEBOOK: b"stripped"}, "Save notebook")

    staged = _git(engine, "diff", "--cached", "--name-status")
    assert staged == "", f"branch commit left staged changes behind: {staged!r}"
    assert _git(engine, "ls-files", "-s", "--", _NOTEBOOK).split()[1] == _git(engine, "rev-parse", f"HEAD:{_NOTEBOOK}")


def test_branch_commit_touches_the_index_only_for_its_own_paths(engine: GitEngine) -> None:
    """Every other index entry — staged or not — is left exactly as it was."""
    (engine.project_path / "notes.md").write_text("staged edit\n", encoding="utf-8")
    engine._run(["add", "notes.md"])
    entries_before = {
        line.split("\t", 1)[1]: line.split("\t", 1)[0] for line in _git(engine, "ls-files", "-s").splitlines() if line
    }

    _commit_ops._commit_entries_to_branch(engine, {_NOTEBOOK: b"stripped"}, "Save notebook")

    entries_after = {
        line.split("\t", 1)[1]: line.split("\t", 1)[0] for line in _git(engine, "ls-files", "-s").splitlines() if line
    }
    assert set(entries_after) - set(entries_before) == {_NOTEBOOK}
    for path, stage_line in entries_before.items():
        assert entries_after[path] == stage_line


def test_branch_commit_uses_plumbing_only(engine: GitEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-036 goes through the same plumbing, so no porcelain touches the tree."""
    recorded = _spy_on_git(engine, monkeypatch)

    _commit_ops._commit_entries_to_branch(engine, {_NOTEBOOK: b"stripped"}, "Save notebook")

    used = _subcommands(recorded)
    assert not ({"add", "commit", "checkout", "reset", "stash"} & set(used))
    assert used == [
        "symbolic-ref",
        "rev-parse",
        "hash-object",
        "read-tree",
        "update-index",
        "write-tree",
        "commit-tree",
        "update-index",
        "update-ref",
    ]


def test_branch_commit_refuses_a_detached_head(engine: GitEngine) -> None:
    """A commit no branch would keep is a lost commit, so it is refused."""
    head = _git(engine, "rev-parse", "HEAD")
    engine._run(["checkout", "--detach", head])

    with pytest.raises(GitError, match="detached"):
        _commit_ops._commit_entries_to_branch(engine, {_NOTEBOOK: b"stripped"}, "Save notebook")


def test_branch_commit_refuses_empty_input(engine: GitEngine) -> None:
    """Same refusals as the ref path, so callers learn one rule."""
    with pytest.raises(ValueError, match="at least one path"):
        _commit_ops._commit_entries_to_branch(engine, {}, "Save notebook")
    with pytest.raises(ValueError, match="must not be empty"):
        _commit_ops._commit_entries_to_branch(engine, {_NOTEBOOK: b"x"}, "  ")


def test_branch_commit_refuses_unsafe_paths(engine: GitEngine) -> None:
    """The path rules are the ref path's rules."""
    head_before = _git(engine, "rev-parse", "HEAD")
    with pytest.raises(ValueError):
        _commit_ops._commit_entries_to_branch(engine, {".git/config": b"x"}, "Save notebook")
    assert _git(engine, "rev-parse", "HEAD") == head_before


def test_ref_commits_and_the_branch_commit_coexist(engine: GitEngine) -> None:
    """A session commits to its ref all along and lands one commit on the branch."""
    ref = _commit_ops._explore_session_ref("s1")
    ref_shas = [
        _commit_ops._commit_entries_to_ref(engine, ref, {_NOTEBOOK: f"run {n}".encode()}, f"cell run {n}")
        for n in range(4)
    ]

    branch_sha = _commit_ops._commit_entries_to_branch(engine, {_NOTEBOOK: b"stripped"}, "Save notebook")

    branch_log = _git(engine, "log", "--format=%H", "main").splitlines()
    assert branch_sha in branch_log
    for sha in ref_shas:
        assert sha not in branch_log
    assert _git(engine, "rev-list", "--count", ref) == "4"


# ---------------------------------------------------------------------------
# The additive guarantee on a protected path
# ---------------------------------------------------------------------------


def test_the_existing_porcelain_commit_still_works(engine: GitEngine) -> None:
    """``GitEngine.commit`` is untouched: same staging, same result.

    ``_commit_ops.py`` is protected core. This change is additive, and this is
    the check that says so.
    """
    (engine.project_path / "new.txt").write_text("hello\n", encoding="utf-8")

    sha = engine.commit("Add new.txt")

    assert _git(engine, "rev-parse", "HEAD") == sha
    assert _git(engine, "log", "-1", "--format=%s", sha) == "Add new.txt"
    assert _git(engine, "status", "--porcelain") == ""


def test_the_existing_porcelain_commit_still_refuses_an_empty_commit(engine: GitEngine) -> None:
    """The pre-existing ``nothing to commit`` guard is unchanged."""
    with pytest.raises(GitError, match="nothing to commit"):
        engine.commit("Nothing changed")


@pytest.mark.parametrize(
    "symbol_name",
    ["_explore_session_ref", "_commit_entries_to_ref", "_commit_entries_to_branch", "_pack_explore_objects"],
)
def test_new_symbols_follow_the_sibling_convention(symbol_name: str) -> None:
    """ADR-046 Addendum 1: private module-level functions, engine first.

    The public surface — and therefore the ADR-052 §5 stability tier — is the
    :class:`GitEngine` method bound in ``git_engine.py``, not the name here.
    """
    symbol: Callable[..., object] = getattr(_commit_ops, symbol_name)
    assert symbol_name.startswith("_")
    assert callable(symbol)
    parameters = list(inspect.signature(symbol).parameters)
    if symbol_name != "_explore_session_ref":
        assert parameters[0] == "engine", f"{symbol_name} must take the GitEngine first"


def test_the_module_imports_nothing_first_party_beyond_its_own_package() -> None:
    """The no-cycle contract (#1337, PR #1344) forbids a wider first-party import.

    ``test_no_circular_import`` loads ``git_binary`` and ``git_engine`` in
    either order under a stub ``scistudio`` package with an empty ``__path__``.
    Any ``import scistudio.<anything-else>`` in this module makes that load
    fail — which is why the new functions carry no ``scistudio.stability``
    decorator. Assert it here so the reason is visible at the point of change
    rather than only in a distant test's traceback.
    """
    source = (Path(_commit_ops.__file__)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    first_party = {name for name in imported if name.split(".")[0] == "scistudio"}
    assert first_party <= {
        "scistudio.core.versioning.errors",
        "scistudio.core.versioning.git_engine",  # TYPE_CHECKING only
    }, f"unexpected first-party imports: {sorted(first_party)}"


# ---------------------------------------------------------------------------
# The public surface: the GitEngine bindings
# ---------------------------------------------------------------------------
#
# ``_commit_ops`` is package-private. What callers actually use is the method
# bound onto ``GitEngine`` in ``git_engine.py``, so the binding is a surface in
# its own right and needs its own coverage: a missing or misspelled binding, or
# one that forgets ``staticmethod``, would leave every test above passing while
# the Explore session cannot reach any of this.

_BOUND_METHODS = {
    "commit_entries_to_ref": "_commit_entries_to_ref",
    "commit_entries_to_branch": "_commit_entries_to_branch",
    "pack_explore_objects": "_pack_explore_objects",
    "explore_session_ref": "_explore_session_ref",
}


@pytest.mark.parametrize(("method_name", "function_name"), sorted(_BOUND_METHODS.items()))
def test_every_plumbing_function_is_bound_onto_the_engine(method_name: str, function_name: str) -> None:
    """The method exists and is the very same function, so behaviour cannot diverge."""
    bound = inspect.getattr_static(GitEngine, method_name)
    expected = getattr(_commit_ops, function_name)
    underlying = bound.__func__ if isinstance(bound, staticmethod) else bound
    assert underlying is expected


def test_no_plumbing_function_is_left_unbound() -> None:
    """A function added to the plumbing path without a binding is unreachable.

    Catches the half-finished change: a fifth operation lands in
    ``_commit_ops`` and nothing in ``git_engine.py`` exposes it.
    """
    plumbing = {
        name
        for name in vars(_commit_ops)
        if name.startswith(("_commit_entries", "_pack_explore", "_explore_session"))
        and callable(getattr(_commit_ops, name))
    }
    assert plumbing == set(_BOUND_METHODS.values()), (
        "a plumbing function has no GitEngine binding (or _BOUND_METHODS is stale)"
    )


def test_the_engine_method_commits_to_the_ref(engine: GitEngine) -> None:
    """The bound method behaves exactly as the private function does."""
    ref = engine.explore_session_ref("s1")
    assert ref == "refs/scistudio/explore/s1"

    index_before = _index_bytes(engine)
    worktree_before = _worktree_snapshot(engine)
    head_before = _git(engine, "rev-parse", "HEAD")

    sha = engine.commit_entries_to_ref(ref, {_NOTEBOOK: b"through the engine"}, "cell run 1")

    assert _index_bytes(engine) == index_before
    assert _worktree_snapshot(engine) == worktree_before
    assert _git(engine, "rev-parse", "HEAD") == head_before
    assert _git(engine, "rev-parse", ref) == sha
    assert _blob_bytes(engine, sha, _NOTEBOOK) == b"through the engine"
    assert sha not in _git(engine, "log", "--format=%H", "main").splitlines()


def test_the_engine_static_method_does_not_receive_the_engine(engine: GitEngine) -> None:
    """``explore_session_ref`` is a ``staticmethod``.

    Bound plainly it would take ``self`` as the session id, and every id would
    be refused — on the class it would silently format the repr of an engine
    into a ref name.
    """
    assert engine.explore_session_ref("s1") == GitEngine.explore_session_ref("s1")
    with pytest.raises(ValueError):
        engine.explore_session_ref("has space")


def test_the_engine_method_commits_to_the_branch(engine: GitEngine) -> None:
    """FR-036 reaches callers through the engine too."""
    head_before = _git(engine, "rev-parse", "HEAD")

    sha = engine.commit_entries_to_branch({_NOTEBOOK: b"stripped"}, "Save notebook")

    assert _git(engine, "rev-parse", "HEAD") == sha
    assert _git(engine, "rev-list", "--parents", "-1", sha).split() == [sha, head_before]
    assert _git(engine, "diff", "--cached", "--name-status") == ""


def test_the_engine_method_packs(engine: GitEngine) -> None:
    """The packing trigger is callable from the engine and reports success."""
    ref = engine.explore_session_ref("s1")
    engine.commit_entries_to_ref(ref, {_NOTEBOOK: b"one"}, "cell run 1", pack_every=None)
    assert _pack_files(engine) == []

    assert engine.pack_explore_objects() is True

    assert len(_pack_files(engine)) == 1


def test_the_engine_method_refuses_a_branch_ref(engine: GitEngine) -> None:
    """The refusals are the same refusals through the public surface."""
    with pytest.raises(ValueError, match="refs/scistudio/"):
        engine.commit_entries_to_ref("refs/heads/main", {_NOTEBOOK: b"x"}, "nope")
    with pytest.raises(ValueError):
        engine.commit_entries_to_ref(engine.explore_session_ref("s1"), {".git/config": b"x"}, "nope")
