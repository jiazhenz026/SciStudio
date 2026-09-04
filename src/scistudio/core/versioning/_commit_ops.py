"""Private sibling for ``GitEngine`` commit operations.

This module is **package-private** per ADR-028 Addendum 1 §C9 +
ADR-046 Addendum 1 ("private functions, not helper classes"): every
public symbol is prefixed with an underscore, the module name itself
starts with an underscore, and it contains zero ``class`` definitions.
External callers must import :class:`GitEngine` from
:mod:`scistudio.core.versioning.git_engine`; importing helpers
directly is unsupported and the names may change without notice.

The function here was extracted from
:mod:`scistudio.core.versioning.git_engine` in issue #1472 (Phase 3
of the backend god-file refactor umbrella #1427) per ADR-046
Addendum 1. The bound method body is byte-identical to the original;
only ``self.`` was rewritten to ``engine.``.

ADR-054 spec 3 (issue #2240) added the *plumbing* commit path below
:func:`_commit`. It is strictly additive: :func:`_commit` and every
symbol that existed before are untouched, so the porcelain commit
behaviour the rest of SciStudio depends on is unchanged. The new
functions never run ``git add``, ``git commit``, ``git checkout`` or
any other command that reads or writes the working tree or the
repository's real index — see :func:`_commit_entries_to_ref`.

Every new function follows the sibling convention: module-level,
underscore-prefixed, ``GitEngine`` as the first positional argument,
so :mod:`scistudio.core.versioning.git_engine` can bind it onto the
class exactly like :func:`_commit`.

**No ADR-052 §5 stability decorator appears here, deliberately.** The
markers live on the *public* surface, and this module has none — the
public symbols are the :class:`GitEngine` methods bound in
``git_engine.py``, which is where a tier is declared. Importing
:mod:`scistudio.stability` from inside ``core.versioning`` is also not
available: every module in this package imports stdlib and its own
siblings and nothing else, which is what lets ``git_binary`` and
``git_engine`` be loaded in either order (the #1337 / PR #1344
no-cycle contract, guarded by ``test_no_circular_import``). A
first-party import here breaks that guard.
"""

from __future__ import annotations

import logging
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from scistudio.core.versioning.errors import GitError

if TYPE_CHECKING:
    from scistudio.core.versioning.git_engine import GitEngine

logger = logging.getLogger(__name__)

# Identity constants (duplicated from git_engine to avoid a cycle at
# import-time; values must stay in sync with the canonical definitions
# in ``scistudio.core.versioning.git_engine``).
_DEFAULT_AUTHOR_NAME = "SciStudio User"
_DEFAULT_AUTHOR_EMAIL = "noreply@scistudio.local"


def _commit(
    engine: GitEngine,
    message: str,
    *,
    files: list[str] | None = None,
    author: str | None = None,
    prefix: str | None = None,
) -> str:
    """Create a new commit and return the new HEAD commit SHA.

    Args:
        message: The commit message; must be non-empty.
        files: Specific files to stage and commit; ``None`` stages all changes.
        author: Optional ``Name <email>`` author override.
        prefix: Optional message prefix, either ``"auto"`` or ``"agent"``,
            prepended as ``"<prefix>: <message>"``.

    Returns:
        The SHA of the newly created commit.

    Raises:
        ValueError: When *message* is empty, or *prefix* is not ``"auto"`` or
            ``"agent"``.
        GitError: When there is nothing staged to commit.
    """
    if not message or not message.strip():
        raise ValueError("Commit message must not be empty.")

    if prefix is not None:
        if prefix not in ("auto", "agent"):
            raise ValueError(f"Invalid commit prefix {prefix!r} — only 'auto' or 'agent' allowed.")
        final_message = f"{prefix}: {message}"
    else:
        final_message = message

    # Stage.
    if files is None:
        engine._run(["add", "-A"])
    else:
        engine._run(["add", "--", *files])

    # D39-3.2 (#968) P2-C: empty-repo edge case.
    #
    # ``git diff --cached --quiet`` against a missing HEAD (a freshly
    # ``git init``-ed repo with no commits) historically returned 0
    # even when the index was non-empty — making the empty-tree guard
    # below raise ``nothing to commit`` for what is actually the
    # repo's initial commit. Detect the no-HEAD case first via
    # ``git rev-parse --verify HEAD`` (rc != 0). When HEAD is missing,
    # fall back to ``git diff --cached --quiet HEAD`` against the
    # empty-tree object so the staged-files check is correct.
    head_check = engine._run(["rev-parse", "--verify", "-q", "HEAD"], check=False)
    has_head = head_check.returncode == 0
    if has_head:
        proc = engine._run(["diff", "--cached", "--quiet"], check=False)
        tree_is_empty = proc.returncode == 0
    else:
        # No HEAD: ask git directly whether the index has anything
        # staged. ``ls-files --cached`` prints one line per staged
        # entry; empty stdout means the index is empty.
        ls_proc = engine._run(["ls-files", "--cached"], check=False)
        tree_is_empty = not (ls_proc.stdout or "").strip()
    if tree_is_empty:
        raise GitError(1, "nothing to commit, working tree clean", ["commit"])

    # Build commit invocation with config-injected identity so
    # commits succeed even when the user has no global user.name.
    commit_args = [
        "-c",
        f"user.name={_DEFAULT_AUTHOR_NAME}",
        "-c",
        f"user.email={_DEFAULT_AUTHOR_EMAIL}",
        "commit",
        "-m",
        final_message,
        "--cleanup=strip",
    ]
    if author:
        commit_args.extend(["--author", author])
    engine._run(commit_args)
    return engine._rev_parse_head(engine.project_path)


# ---------------------------------------------------------------------------
# ADR-054 spec 3 (#2240): commits written with plumbing, off the working tree
# ---------------------------------------------------------------------------
#
# An Explore session commits the notebook after **every** cell run — ADR-054
# §6.6 measured roughly thirty commits an hour during ordinary use. Doing that
# through ``git add`` + ``git commit`` would stage into the repository's real
# index and move the branch, so a person editing files in the same project
# would watch their staged work and their branch head change under them.
#
# The plumbing sequence below produces the same objects without any of that:
#
#   1. ``git hash-object -w --no-filters`` writes each blob straight into the
#      object database. ``--no-filters`` is load-bearing: it stops
#      ``core.autocrlf`` and any clean filter from rewriting notebook bytes,
#      so what the caller passed is exactly what the commit records.
#   2. ``git update-index --add --cacheinfo`` populates a **temporary** index
#      selected with ``GIT_INDEX_FILE``. The repository's real index file is
#      never opened.
#   3. ``git write-tree`` turns that temporary index into a tree.
#   4. ``git commit-tree`` builds the commit object.
#   5. ``git update-ref`` moves the target ref, with the previous value passed
#      as the compare-and-swap old value so two concurrent writers cannot
#      silently lose a commit.
#
# No step in that list reads or writes the working tree, HEAD, or the real
# index (FR-029).

#: Ref namespace dedicated to Explore sessions (FR-028). Deliberately **not**
#: under ``refs/heads/``: a commit written here is invisible to ``git log``,
#: ``git branch`` and ``git status`` for any branch, so a session's history
#: never appears on the branch until someone commits explicitly (FR-030,
#: FR-036).
_EXPLORE_REF_PREFIX = "refs/scistudio/explore/"

#: Force packing after this many commits on one session ref (FR-031).
#:
#: git's own automatic threshold is ``gc.auto = 6700`` loose objects. At the
#: ~30 commits an hour ADR-054 §6.6 measured — two or three loose objects each
#: — that threshold is about a week of heavy use away, which is far too late
#: for a repository whose git is the one SciStudio ships. 256 commits is
#: roughly a heavy day, so packing happens about daily instead of about
#: weekly.
_EXPLORE_PACK_INTERVAL = 256

#: Regular file mode used for every entry written through this path. Explore
#: writes notebooks; nothing here needs an executable bit or a symlink.
_BLOB_MODE = "100644"

#: A session id may become one ref path component, so it is restricted to
#: characters ``git check-ref-format`` accepts unconditionally. FR-001 makes
#: the session service derive ids that satisfy this; the check here is the
#: backstop that keeps a hand-built id from reaching ``update-ref``.
_SESSION_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")

#: Path components refused in an entry path, whatever their case. ``.git``
#: would let a caller write into the repository's own administrative tree.
_REFUSED_PATH_COMPONENTS = frozenset({"", ".", "..", ".git"})


def _explore_session_ref(session_id: str) -> str:
    """Return the dedicated ref for *session_id* (FR-028).

    Args:
        session_id: The Explore session identifier. Must be a single ref path
            component: it starts with a letter or digit, continues with
            letters, digits, ``.``, ``_`` or ``-``, contains no ``..``, and
            ends in neither ``.`` nor ``.lock``.

    Returns:
        The full ref name, ``refs/scistudio/explore/<session-id>``.

    Raises:
        ValueError: When *session_id* is empty or would not survive
            ``git check-ref-format``.
    """
    if not session_id or not _SESSION_ID_RE.match(session_id):
        raise ValueError(
            f"Invalid explore session id {session_id!r}: must match {_SESSION_ID_RE.pattern} "
            f"so it can be used as a single git ref component."
        )
    if ".." in session_id or session_id.endswith((".", ".lock")):
        raise ValueError(
            f"Invalid explore session id {session_id!r}: git refuses a ref component "
            f"containing '..' or ending in '.' or '.lock'."
        )
    return f"{_EXPLORE_REF_PREFIX}{session_id}"


def _validate_entry_path(path: str) -> str:
    """Return *path* normalised to a repo-relative POSIX path, or raise.

    Args:
        path: A repository-relative path such as ``"explore/analysis.ipynb"``.

    Returns:
        The same path, with any backslashes rejected rather than translated so
        a caller never silently commits a differently-named file.

    Raises:
        ValueError: When the path is empty, absolute, contains a backslash, a
            NUL or other control character, or has a ``.``, ``..`` or ``.git``
            component.
    """
    if not path or not path.strip():
        raise ValueError("Entry path must not be empty.")
    if "\\" in path:
        raise ValueError(f"Entry path {path!r} must use '/' separators, not '\\'.")
    if path.startswith("/"):
        raise ValueError(f"Entry path {path!r} must be repository-relative, not absolute.")
    if re.search(r"[\x00-\x1f\x7f]", path):
        raise ValueError(f"Entry path {path!r} contains a control character.")
    if len(path) > 1 and path[1] == ":":
        raise ValueError(f"Entry path {path!r} must be repository-relative, not a drive path.")
    for component in path.split("/"):
        if component.lower() in _REFUSED_PATH_COMPONENTS:
            raise ValueError(f"Entry path {path!r} contains a refused component {component!r}.")
    return path


def _identity_env() -> dict[str, str]:
    """Author and committer identity for a plumbing commit.

    ``git commit-tree`` refuses to run without an identity, and a SciStudio
    user is not required to have configured one. Mirrors
    :meth:`GitEngine._author_env` and the config injection :func:`_commit`
    uses, so plumbing commits carry the same identity as porcelain ones.
    """
    return {
        "GIT_AUTHOR_NAME": _DEFAULT_AUTHOR_NAME,
        "GIT_AUTHOR_EMAIL": _DEFAULT_AUTHOR_EMAIL,
        "GIT_COMMITTER_NAME": _DEFAULT_AUTHOR_NAME,
        "GIT_COMMITTER_EMAIL": _DEFAULT_AUTHOR_EMAIL,
    }


def _hash_entries(engine: GitEngine, entries: Mapping[str, bytes], scratch: Path) -> dict[str, str]:
    """Write every entry's bytes into the object database; return path to blob SHA.

    Each payload is spilled to a scratch file outside the repository, because
    :meth:`GitBinary.run` cannot feed a subprocess on stdin. ``--no-filters``
    is what makes the bytes exact: it stops ``core.autocrlf`` and any
    configured clean filter from rewriting them. Hashing from a location
    outside the repository keeps ``.gitattributes`` out of the decision too.
    """
    ordered_paths = sorted(entries)
    blob_files: list[str] = []
    for position, path in enumerate(ordered_paths):
        blob_file = scratch / f"blob-{position}"
        blob_file.write_bytes(entries[path])
        blob_files.append(str(blob_file))

    proc = engine._git.run(
        ["hash-object", "-w", "--no-filters", "--", *blob_files],
        cwd=engine.project_path,
    )
    shas = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    if len(shas) != len(ordered_paths):
        raise GitError(
            1,
            f"git hash-object returned {len(shas)} object ids for {len(ordered_paths)} inputs.",
            ["hash-object"],
        )
    return dict(zip(ordered_paths, shas, strict=True))


def _cacheinfo_args(blobs: Mapping[str, str]) -> list[str]:
    """Return the ``--cacheinfo`` arguments that add *blobs* to an index."""
    args: list[str] = []
    for path in sorted(blobs):
        args.extend(["--cacheinfo", f"{_BLOB_MODE},{blobs[path]},{path}"])
    return args


def _write_tree(
    engine: GitEngine,
    blobs: Mapping[str, str],
    *,
    base_commit: str | None,
    index_file: Path,
) -> str:
    """Build a tree from *blobs* against a temporary index and return its SHA.

    Args:
        engine: The engine whose repository receives the objects.
        blobs: Repository-relative POSIX path to the blob SHA recorded there.
        base_commit: When given, the tree of this commit is read into the
            temporary index first, so the result is that tree with *blobs*
            applied on top. ``None`` builds a tree containing *only* *blobs*.
        index_file: Path of the temporary index, selected with
            ``GIT_INDEX_FILE``. Must sit outside the repository's ``.git`` so
            the real index is never a candidate.

    Returns:
        The SHA of the written tree.
    """
    index_env = {"GIT_INDEX_FILE": str(index_file)}

    if base_commit is not None:
        engine._git.run(["read-tree", base_commit], cwd=engine.project_path, env=index_env)

    engine._git.run(
        ["update-index", "--add", *_cacheinfo_args(blobs)],
        cwd=engine.project_path,
        env=index_env,
    )

    proc = engine._git.run(["write-tree"], cwd=engine.project_path, env=index_env)
    tree_sha = (proc.stdout or "").strip()
    if not tree_sha:
        raise GitError(1, "git write-tree produced no tree id.", ["write-tree"])
    return tree_sha


def _commit_tree(
    engine: GitEngine,
    tree_sha: str,
    message: str,
    *,
    parent: str | None,
) -> str:
    """Create a commit object over *tree_sha* and return its SHA."""
    args = [
        "-c",
        f"user.name={_DEFAULT_AUTHOR_NAME}",
        "-c",
        f"user.email={_DEFAULT_AUTHOR_EMAIL}",
        "commit-tree",
        tree_sha,
    ]
    if parent:
        args.extend(["-p", parent])
    args.extend(["-m", message])

    proc = engine._git.run(args, cwd=engine.project_path, env=_identity_env())
    commit_sha = (proc.stdout or "").strip()
    if not commit_sha:
        raise GitError(1, "git commit-tree produced no commit id.", ["commit-tree"])
    return commit_sha


def _resolve_ref(engine: GitEngine, ref: str) -> str | None:
    """Return the commit *ref* points at, or ``None`` when it does not exist."""
    proc = engine._run(["rev-parse", "--verify", "-q", ref], check=False)
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


def _pack_explore_objects(engine: GitEngine) -> bool:
    """Force the repository to pack its loose objects (FR-031).

    Runs ``git repack -d`` rather than ``git gc``: repacking gathers the loose
    objects an Explore session leaves behind and drops the packs that become
    redundant, without pruning anything a concurrent operation might still be
    holding a reference to.

    A packing failure must never take a session down (FR-030), so the failure
    is logged and reported rather than raised — the objects stay loose and the
    next attempt tries again.

    Args:
        engine: The engine whose repository is packed.

    Returns:
        ``True`` when git packed successfully, ``False`` when it failed.
    """
    proc = engine._run(["repack", "-d", "-q"], check=False)
    if proc.returncode != 0:
        logger.warning(
            "git repack failed in %s (rc=%s): %s",
            engine.project_path,
            proc.returncode,
            (proc.stderr or "").strip(),
        )
        return False
    return True


def _commit_entries_to_ref(
    engine: GitEngine,
    ref: str,
    entries: Mapping[str, bytes],
    message: str,
    *,
    pack_every: int | None = _EXPLORE_PACK_INTERVAL,
) -> str:
    """Commit *entries* onto *ref* with plumbing and return the commit SHA.

    Writes one commit whose tree contains exactly *entries* and nothing else,
    parented on whatever *ref* pointed at before (or rootless when the ref is
    new). The repository's working tree, its real index, and ``HEAD`` are all
    untouched, and because *ref* lives outside ``refs/heads/`` the commit never
    appears in ``git log <branch>`` (FR-028, FR-029).

    The ref is moved with a compare-and-swap against its previous value, so a
    second writer that raced this one fails loudly instead of overwriting a
    commit. A caller retrying off the execution path (FR-030) can therefore
    call this again safely: the retry either lands or reports.

    Args:
        engine: The engine whose repository receives the commit.
        ref: Full ref name to move, e.g. the value
            :func:`_explore_session_ref` returns. Must be under
            ``refs/scistudio/`` — this path is not a way to move a branch.
        entries: Repository-relative POSIX path to exact file content. The
            bytes are committed verbatim; no filter and no line-ending
            conversion is applied.
        message: Commit message; must be non-empty.
        pack_every: Force a pack once the ref carries a positive multiple of
            this many commits (FR-031). ``None`` or ``0`` disables packing,
            which is for tests and for a caller that packs on its own schedule.

    Returns:
        The SHA of the newly created commit.

    Raises:
        ValueError: When *ref* is not under ``refs/scistudio/``, *entries* is
            empty, an entry path is not a safe repository-relative path, or
            *message* is empty.
        GitError: When a git plumbing command fails, including when another
            writer moved *ref* first.
    """
    if not ref.startswith("refs/scistudio/"):
        raise ValueError(
            f"Refusing to write {ref!r}: the plumbing commit path only writes refs under "
            f"'refs/scistudio/', never a branch."
        )
    if not entries:
        raise ValueError("Refusing to write an empty commit: entries must contain at least one path.")
    if not message or not message.strip():
        raise ValueError("Commit message must not be empty.")

    validated = {_validate_entry_path(path): content for path, content in entries.items()}

    previous = _resolve_ref(engine, ref)
    with tempfile.TemporaryDirectory(prefix="scistudio-explore-commit-") as tmp:
        scratch = Path(tmp)
        blobs = _hash_entries(engine, validated, scratch)
        tree_sha = _write_tree(engine, blobs, base_commit=None, index_file=scratch / "index")
        commit_sha = _commit_tree(engine, tree_sha, message, parent=previous)

    # Compare-and-swap. An empty old value means "the ref must not exist".
    engine._run(["update-ref", ref, commit_sha, previous or ""])

    if pack_every:
        _pack_if_due(engine, ref, pack_every)

    return commit_sha


def _pack_if_due(engine: GitEngine, ref: str, pack_every: int) -> bool:
    """Pack when *ref* has just reached a positive multiple of *pack_every*.

    Counting the ref itself rather than keeping a counter in memory means the
    bound survives a restart and cannot drift: a session reopened tomorrow
    packs at commit 512, not at commit 256 again.

    Returns:
        ``True`` when a pack was attempted and succeeded, else ``False``.
    """
    proc = engine._run(["rev-list", "--count", ref], check=False)
    if proc.returncode != 0:
        return False
    try:
        depth = int((proc.stdout or "").strip())
    except ValueError:  # pragma: no cover — git always prints an integer here
        return False
    if depth <= 0 or depth % pack_every != 0:
        return False
    return _pack_explore_objects(engine)


def _commit_entries_to_branch(
    engine: GitEngine,
    entries: Mapping[str, bytes],
    message: str,
) -> str:
    """Commit *entries* onto the current branch with plumbing (FR-036).

    Unlike :func:`_commit_entries_to_ref` this one *does* move the branch —
    that is the point: it is how a session's notebook reaches the branch when
    the person asks for it, or on close.

    It still never writes the working tree, because the content committed is
    the caller's bytes (the notebook with its outputs stripped) and not the
    file sitting on disk (which keeps its outputs, FR-027). ``git add`` would
    commit the wrong content, and ``git commit`` would sweep up whatever else
    the person had staged.

    The new commit's tree is ``HEAD``'s tree with *entries* applied on top, so
    nothing else in the branch is disturbed, and the person's staged work
    survives untouched.

    One thing this *does* write is the repository's real index, for the
    committed paths only. It has to: the index is a cache of ``HEAD`` plus
    what is staged, so a branch that moved while the index stayed behind would
    make ``git status`` report the notebook as a **staged deletion**, and the
    person's next ``git commit`` would silently revert this one. The index
    entry is written before the ref moves, so the failure mode of a lost
    compare-and-swap is a harmless staged *addition* of the notebook rather
    than that staged deletion.

    Afterwards ``git status`` shows the on-disk notebook as modified, because
    the file really does still carry its outputs while the branch records it
    without them. That is the honest state, and the same one any
    strip-on-commit workflow produces.

    Args:
        engine: The engine whose repository receives the commit.
        entries: Repository-relative POSIX path to exact file content.
        message: Commit message; must be non-empty.

    Returns:
        The SHA of the newly created commit.

    Raises:
        ValueError: When *entries* is empty, an entry path is not a safe
            repository-relative path, or *message* is empty.
        GitError: When ``HEAD`` is detached, when a git plumbing command
            fails, or when another writer moved the branch first.
    """
    if not entries:
        raise ValueError("Refusing to write an empty commit: entries must contain at least one path.")
    if not message or not message.strip():
        raise ValueError("Commit message must not be empty.")

    validated = {_validate_entry_path(path): content for path, content in entries.items()}

    head_ref_proc = engine._run(["symbolic-ref", "-q", "HEAD"], check=False)
    branch_ref = (head_ref_proc.stdout or "").strip()
    if head_ref_proc.returncode != 0 or not branch_ref:
        raise GitError(
            1,
            "HEAD is detached; refusing to write a branch commit that no branch would keep.",
            ["symbolic-ref"],
        )

    parent = _resolve_ref(engine, "HEAD")
    with tempfile.TemporaryDirectory(prefix="scistudio-explore-branch-") as tmp:
        scratch = Path(tmp)
        blobs = _hash_entries(engine, validated, scratch)
        tree_sha = _write_tree(engine, blobs, base_commit=parent, index_file=scratch / "index")
        commit_sha = _commit_tree(engine, tree_sha, message, parent=parent)

    # Keep the real index in step with the branch, for these paths only. See
    # the docstring: skipping this would leave a staged deletion behind.
    engine._run(["update-index", "--add", *_cacheinfo_args(blobs)])
    engine._run(["update-ref", branch_ref, commit_sha, parent or ""])
    return commit_sha
