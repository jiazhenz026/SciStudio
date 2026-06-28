"""Private sibling for ``GitEngine`` branch / tag operations.

This module is **package-private** per ADR-028 Addendum 1 §C9 +
ADR-046 Addendum 1 ("private functions, not helper classes"): every
public symbol is prefixed with an underscore, the module name itself
starts with an underscore, and it contains zero ``class`` definitions.
External callers must import :class:`GitEngine` from
:mod:`scistudio.core.versioning.git_engine`; importing helpers
directly is unsupported and the names may change without notice.

The functions here were extracted from
:mod:`scistudio.core.versioning.git_engine` in issue #1472 (Phase 3
of the backend god-file refactor umbrella #1427) per ADR-046
Addendum 1. Bound-method bodies are byte-identical to the originals;
only ``self.`` was rewritten to ``engine.``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scistudio.core.versioning.errors import GitError

if TYPE_CHECKING:
    from scistudio.core.versioning.git_engine import GitEngine

# Shared prefix used by both ``_branches`` and ``_current_branch`` when
# stripping the ``refs/heads/`` namespace to obtain clean short names.
# Using the fully-qualified ref form and stripping client-side avoids the
# ``heads/<name>`` disambiguation prefix that both ``%(refname:short)``
# and ``git rev-parse --abbrev-ref`` / ``symbolic-ref --short`` produce
# when a tag shares the same short name as a branch (#1390).
_HEADS_PREFIX = "refs/heads/"


def _branches(engine: GitEngine) -> list[dict[str, Any]]:
    """List the local branches.

    Returns:
        One dict per branch with ``name``, ``head_sha``, and ``is_current``,
        sorted with the current branch first, then alphabetically.
    """
    current = engine.current_branch()
    proc = engine._run(
        [
            "for-each-ref",
            "--format=%(refname)\t%(objectname)",
            "refs/heads/",
        ]
    )
    out: list[dict[str, Any]] = []
    for line in (proc.stdout or "").splitlines():
        if "\t" not in line:
            continue
        refname, sha = line.split("\t", 1)
        # Always strip the known prefix; result is the clean short name.
        name = refname[len(_HEADS_PREFIX) :] if refname.startswith(_HEADS_PREFIX) else refname
        out.append(
            {
                "name": name,
                "head_sha": sha,
                "is_current": (name == current),
            }
        )
    # Sort: current first, then alphabetical.
    out.sort(key=lambda x: (not x["is_current"], x["name"]))
    return out


def _current_branch(engine: GitEngine) -> str | None:
    """Return the short name of the checked-out branch, or ``None``.

    Returns:
        The current branch name, or ``None`` when HEAD is detached.
    """
    proc = engine._run(["symbolic-ref", "HEAD"], check=False)
    if proc.returncode != 0:
        return None
    ref = (proc.stdout or "").strip()
    if not ref:
        return None
    if ref.startswith(_HEADS_PREFIX):
        return ref[len(_HEADS_PREFIX) :]
    # Unexpected ref namespace (should not happen for a normal checkout).
    return ref


def _branch_create(engine: GitEngine, name: str, base: str | None = None) -> None:
    """Create a new branch.

    Args:
        name: Name of the branch to create.
        base: Commit or branch to start from; ``None`` uses the current HEAD.
    """
    args = ["branch", name]
    if base:
        args.append(base)
    engine._run(args)


def _branch_switch(engine: GitEngine, name: str) -> None:
    """Switch to an existing branch.

    The caller must resolve a dirty working tree before calling this.

    Args:
        name: Name of the branch to check out.
    """
    engine._run(["checkout", name])


def _branch_delete(engine: GitEngine, name: str, *, force: bool = False) -> None:
    """Delete a local branch.

    Args:
        name: Name of the branch to delete.
        force: When ``True``, delete even if the branch is not fully merged.

    Raises:
        GitError: When *name* is the currently checked-out branch.
    """
    if engine.current_branch() == name:
        raise GitError(
            1,
            f"Cannot delete the currently checked-out branch '{name}'.",
            ["branch", "-d", name],
        )
    flag = "-D" if force else "-d"
    engine._run(["branch", flag, name])


def _commits_reachable_only_from(engine: GitEngine, branch: str) -> list[str]:
    """Return the commits reachable from ``branch`` but from no other ref.

    This is git's "what would become unreachable if this branch were deleted"
    query — the same check ``git branch -d`` uses to refuse deleting an unmerged
    branch.

    Args:
        branch: The branch to check.

    Returns:
        Full 40-character SHAs reachable only from ``branch``. Empty when every
        commit on the branch is also reachable from another ref, or when the
        branch does not exist.
    """
    # Use the fully-qualified ref form on BOTH the include (target)
    # side and the exclude side so name resolution cannot collide
    # with a tag or remote-tracking ref of the same short name.
    target_ref = f"refs/heads/{branch}"
    ref_proc = engine._run(
        ["for-each-ref", "--format=%(refname)"],
        check=False,
    )
    if ref_proc.returncode != 0:
        return []
    other_refs = [
        line.strip() for line in (ref_proc.stdout or "").splitlines() if line.strip() and line.strip() != target_ref
    ]
    if not other_refs:
        # No other refs exist (single-branch repo); every commit on
        # ``branch`` is technically only reachable from it. Return
        # empty list rather than rev-list-ing without ``--not`` —
        # the safety net is meaningful only in multi-ref repos.
        return []
    proc = engine._run(
        ["rev-list", target_ref, "--not", *other_refs],
        check=False,
    )
    if proc.returncode != 0:
        # rev-list on a missing branch returns non-zero. Treat as
        # "no orphan candidates" — branch_delete will surface the
        # real error.
        return []
    return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]


def _tag(engine: GitEngine, name: str, target_sha: str, *, force: bool = True) -> None:
    """Point a ref at a commit.

    Despite the name, this writes an arbitrary ref via ``git update-ref`` (not
    ``git tag``), so the ref can live in whatever namespace the caller chooses.

    Args:
        name: Fully-qualified ref name (must start with ``refs/``).
        target_sha: The commit SHA the ref should point to.
        force: When ``True`` (the default), overwrite any existing ref at
            ``name`` (idempotent). When ``False``, refuse to overwrite an
            existing ref ("create only if absent").
    """
    if force:
        engine._run(["update-ref", name, target_sha])
    else:
        # ``git update-ref <name> <new-sha> ""`` succeeds only when the
        # ref does not yet exist (empty string means "expect no old
        # value"). If the ref already exists git exits non-zero and
        # ``_run`` raises ``GitError``.
        engine._run(["update-ref", name, target_sha, ""])
