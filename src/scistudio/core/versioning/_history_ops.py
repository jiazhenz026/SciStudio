"""Private sibling for ``GitEngine`` history, diff, and restore operations.

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

import logging
from typing import TYPE_CHECKING, Any

from scistudio.core.versioning.errors import GitError

if TYPE_CHECKING:
    from scistudio.core.versioning.git_engine import GitEngine

logger = logging.getLogger(__name__)


def _log(
    engine: GitEngine,
    *,
    branch: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return commit history. See ADR-039 §3.5 line 218."""
    US = "\x1f"  # noqa: N806 — unit separator
    RS = "\x1e"  # noqa: N806 — record separator
    template = f"%H{US}%h{US}%P{US}%an{US}%ae{US}%aI{US}%s{US}%b{RS}"

    args = ["log", f"--format={template}"]
    if branch is None:
        args.append("--all")
    else:
        args.append(branch)
    if limit is not None:
        args.extend(["-n", str(limit)])

    proc = engine._run(args, check=False)
    if proc.returncode != 0:
        stderr_lower = (proc.stderr or "").lower()
        if (
            "does not have any commits" in stderr_lower
            or "bad default revision" in stderr_lower
            or ("unknown revision" in stderr_lower and branch is None)
        ):
            return []
        raise GitError(proc.returncode, proc.stderr or "", args)

    # Build ref-tip map. Hotfix #1011: include remote-tracking refs
    # (refs/remotes/) and tags (refs/tags/) in addition to local
    # branches (refs/heads/). Pre-fix, commits that were tips of a
    # remote ref or a tag but had no children in the local history
    # rendered with `branches: []` — the frontend graph then had no
    # label to render next to the dot, producing the "断头" look
    # (orphan merge dot with no incoming line and no name attached).
    # Including all three scan paths gives the frontend a label set
    # to anchor every orphan tip with a chip the way vscode-git-graph
    # / GitLens do.
    ref_proc = engine._run(
        [
            "for-each-ref",
            "--format=%(refname:short)\t%(objectname)",
            "refs/heads/",
            "refs/remotes/",
            "refs/tags/",
        ],
        check=False,
    )
    sha_to_branches: dict[str, list[str]] = {}
    if ref_proc.returncode == 0:
        for line in (ref_proc.stdout or "").splitlines():
            if "\t" not in line:
                continue
            name, sha = line.split("\t", 1)
            # Skip the synthetic "origin/HEAD" symbolic ref which just
            # mirrors the default branch — would render as a duplicate
            # chip with no extra info.
            if name.endswith("/HEAD"):
                continue
            sha_to_branches.setdefault(sha, []).append(name)

    records = (proc.stdout or "").split(RS)
    out: list[dict[str, Any]] = []
    for rec in records:
        rec = rec.lstrip("\n")
        if not rec:
            continue
        fields = rec.split(US)
        if len(fields) < 8:
            continue
        sha, short_sha, parents_raw, an, ae, ai, subject, body = fields[:8]
        parents = parents_raw.split() if parents_raw else []
        out.append(
            {
                "sha": sha,
                "short_sha": short_sha,
                "parents": parents,
                "author_name": an,
                "author_email": ae,
                "author_date": ai,
                "subject": subject,
                "body": body,
                "branches": sha_to_branches.get(sha, []),
            }
        )
    return out


def _diff(
    engine: GitEngine,
    from_sha: str,
    to_sha: str | None = None,
    *,
    files: list[str] | None = None,
) -> str:
    """Return a unified diff string. See ADR-039 §3.5 line 219."""
    args = ["diff", "--unified=3"]
    if to_sha is None or to_sha == "WORKING":
        args.append(from_sha)
    elif to_sha == "HEAD":
        args.extend([from_sha, "HEAD"])
    else:
        args.extend([from_sha, to_sha])
    if files:
        args.append("--")
        args.extend(files)
    proc = engine._run(args)
    return proc.stdout or ""


def _restore(engine: GitEngine, commit_sha: str, *, files: list[str] | None = None) -> None:
    """Soft restore (no HEAD move). See ADR-039 §3.6.

    ADR-039 Addendum 1 (#1354): this engine method is now a pure
    soft restore — the caller is responsible for auto-committing a
    dirty working tree first (see ``routes/git.py::restore`` for
    the route-layer auto-commit). Pre-addendum the engine itself
    auto-stashed dirty state; that behavior was moved up so the
    route layer can return ``auto_commit_sha`` in the response
    and the frontend can surface a "committed as <sha>" hint
    instead of stash drawer language.

    Hotfix #997: when every target file's content at ``commit_sha``
    is byte-identical to its current working-tree content, restore
    is a no-op — skip the actual ``git checkout``. Pre-fix, clicking
    "Restore this run's workflow" on a run whose recorded commit
    happened to match the current working tree still triggered an
    auto-handler against a tree that was dirty in *any* file (even
    unrelated ones). The no-op short-circuit eliminates that
    false-dirty cascade for the specific-files variant (the most
    common Lineage tab path: ``files=['workflows/<id>.yaml']``).
    """
    # Skip-if-unchanged short-circuit (files variant only).
    if files:
        try:
            all_unchanged = _files_unchanged_vs_commit(engine, commit_sha, files)
        except GitError:
            # If we can't compare (commit doesn't exist, etc.) let
            # the subsequent checkout produce the real error message.
            all_unchanged = False
        if all_unchanged:
            logger.debug(
                "restore: %s @ %s already matches working tree; skipping checkout",
                files,
                commit_sha[:7],
            )
            return

    args = ["checkout", commit_sha, "--"]
    if files:
        args.extend(files)
    else:
        args.append(".")
    engine._run(args)


def _files_unchanged_vs_commit(engine: GitEngine, commit_sha: str, files: list[str]) -> bool:
    """Return True iff every file's worktree content equals its
    content at *commit_sha*.

    Uses ``git diff --quiet <commit> -- <files>``: rc 0 means no
    diff, rc 1 means diff, rc other means error.

    Helper for the hotfix #997 skip-if-unchanged short-circuit in
    :meth:`GitEngine.restore`.
    """
    diff_args = ["diff", "--quiet", commit_sha, "--", *files]
    proc = engine._run(diff_args, check=False)
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    # Any other return code: treat as unable-to-determine; let the
    # caller fall through to the normal checkout path.
    raise GitError(proc.returncode, proc.stderr or "", diff_args)
