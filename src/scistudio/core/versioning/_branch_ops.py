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


def _branches(engine: GitEngine) -> list[dict[str, Any]]:
    """List all local branches. See ADR-039 §3.5 line 221."""
    current = engine.current_branch()
    proc = engine._run(
        [
            "for-each-ref",
            "--format=%(refname:short)\t%(objectname)",
            "refs/heads/",
        ]
    )
    out: list[dict[str, Any]] = []
    for line in (proc.stdout or "").splitlines():
        if "\t" not in line:
            continue
        name, sha = line.split("\t", 1)
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
    """Return the name of the currently checked-out branch, or None."""
    proc = engine._run(["rev-parse", "--abbrev-ref", "HEAD"], check=False)
    if proc.returncode != 0:
        return None
    name = (proc.stdout or "").strip()
    if not name or name == "HEAD":
        return None
    return name


def _branch_create(engine: GitEngine, name: str, base: str | None = None) -> None:
    """Create a new branch (at HEAD by default)."""
    args = ["branch", name]
    if base:
        args.append(base)
    engine._run(args)


def _branch_switch(engine: GitEngine, name: str) -> None:
    """Switch to an existing branch. Caller must resolve dirty tree first."""
    engine._run(["checkout", name])


def _branch_delete(engine: GitEngine, name: str, *, force: bool = False) -> None:
    """Delete a local branch (refuses to delete current)."""
    if engine.current_branch() == name:
        raise GitError(
            1,
            f"Cannot delete the currently checked-out branch '{name}'.",
            ["branch", "-d", name],
        )
    flag = "-D" if force else "-d"
    engine._run(["branch", flag, name])


def _commits_reachable_only_from(engine: GitEngine, branch: str) -> list[str]:
    """Return commits reachable from ``branch`` but no other ref.

    ADR-039 Addendum 1 §11.4 row #1356: feeds the branch-delete
    safety net. ``git rev-list refs/heads/<branch> --not <all-other-refs>``
    is git's canonical "what would become unreachable" query — the
    same logic ``git branch -d`` uses internally to refuse a delete
    when the branch is not merged.

    We use the fully-qualified ``refs/heads/<branch>`` form on the
    target side of the rev-list so name resolution is unambiguous
    when a tag and a branch share the same short name (Codex P1 on
    PR #1381). Without this, ``git rev-list foo`` could resolve
    ``foo`` as ``refs/tags/foo`` and compute orphan candidates
    from the tag instead of the branch, causing the safety net to
    skip pinning real branch-only commits.

    We enumerate "all other refs" via ``git for-each-ref`` rather
    than relying on ``--branches --tags --remotes`` shortcuts so the
    result is robust to user-created refs (including the
    ``refs/scistudio/lineage/*`` namespace this safety net writes
    to — these MUST count as "other refs" so calling this method a
    second time after a tag is created returns an empty list).

    Returns
    -------
    list[str]
        Full 40-char SHAs that are reachable only from ``branch``.
        Empty list if every commit on the branch is also reachable
        via at least one other ref. Returns ``[]`` on a non-existent
        branch rather than raising — the caller (route layer) is
        about to delete the branch anyway and will surface a
        structured error from ``branch_delete`` if it really doesn't
        exist.
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


def _tag(engine: GitEngine, name: str, target_sha: str, *, force: bool = False) -> None:
    """Create (or overwrite) a ref ``name`` pointing to ``target_sha``.

    ADR-039 Addendum 1 §11.4 row #1356: used by the branch-delete
    safety net to pin lineage-referenced commits under
    ``refs/scistudio/lineage/<sha>`` before deletion. Despite the
    method name, this uses ``git update-ref`` rather than
    ``git tag`` so the ref lands in the caller-specified namespace
    (``refs/scistudio/lineage/*``) and stays out of the
    ``refs/tags/*`` namespace where the History view's chip
    renderer would otherwise pick it up.

    Idempotent: ``update-ref`` overwrites by default, so re-running
    the safety net on a branch whose orphan-set was already pinned
    is a silent no-op.

    Parameters
    ----------
    name:
        Fully-qualified ref name (e.g. ``refs/scistudio/lineage/<sha>``).
        Must start with ``refs/`` — git update-ref enforces this.
    target_sha:
        The commit SHA the ref should point to.
    force:
        Accepted for API symmetry with ``git tag``; ignored because
        ``update-ref`` is already overwrite-by-default.
    """
    # ``force`` is intentionally unused — see docstring.
    del force
    engine._run(["update-ref", name, target_sha])
