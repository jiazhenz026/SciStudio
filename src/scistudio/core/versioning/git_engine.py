"""Subprocess wrapper around the bundled git CLI (ADR-039 §3.1, §3.5).

The :class:`GitEngine` is the **only** module in SciStudio allowed to shell
out to git. All API routes (`scistudio.api.routes.git`) and runtime hooks
(``ApiRuntime.create_project``, ``ApiRuntime.start_workflow``) call into
this class.

Stable wire format
------------------

Per ADR-039 §3.1 lines 71-72: we use **plumbing commands with stable
machine-readable output** — never porcelain v1.

- ``git status --porcelain=v2``  (NOT plain ``--porcelain``)
- ``git log --format=...``       (custom delimited template)
- ``git diff --raw`` or unified diff text (stable)
- ``git rev-parse HEAD``         (single SHA, no ambiguity)

Decomposition (ADR-046 Addendum 1, #1472)
-----------------------------------------

This file is the thin class-binding shell for ``GitEngine``. The bound
method bodies live in private ``_*_ops.py`` sibling modules per
ADR-046 Addendum 1 (Path D class-binding pattern). The class definition
here only contains ``__init__``, the in-class helpers used by every
sibling (``_run``, ``_author_env``, ``_rev_parse_head``, the ``_git``
property), the repository-lifecycle methods (``init_repository``,
``is_repository``), and the ~14 binding lines that wire the sibling
functions into the public method surface.

:data:`MergeResult` (a ``Literal`` alias) remains defined in this module.
:class:`HeadState` moved to the leaf module
:mod:`scistudio.core.versioning.state` (round-4 no-cycles) so that
``_status_ops`` imports it from a sibling leaf instead of lazy-importing
``git_engine``; it is re-exported here, and ADR-039 governs the canonical
``scistudio.core.versioning.state.HeadState`` definition.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from scistudio.core.versioning import (
    _branch_ops,
    _commit_ops,
    _history_ops,
    _merge_ops,
    _status_ops,
)
from scistudio.core.versioning.errors import GitError
from scistudio.core.versioning.git_binary import GitBinary
from scistudio.core.versioning.state import HeadState

# ---------------------------------------------------------------------------
# Public value types (ADR-039)
# ---------------------------------------------------------------------------
#
# ``HeadState`` is defined in :mod:`scistudio.core.versioning.state` and
# re-exported here so ``scistudio.core.versioning.git_engine.HeadState``
# continues to resolve for existing importers. The extraction lets
# ``_status_ops`` import ``HeadState`` from the leaf ``state`` module at
# module level instead of lazy-importing ``git_engine`` from inside
# ``_head_state`` — that lazy edge previously closed an at-import cycle
# (round-4 no-cycles, mirroring the #1337 ``errors`` extraction). The
# canonical ADR-039 governed contract is now ``state.HeadState``.
#
# ``MergeResult`` stays here: it is a ``Literal`` alias, not part of any
# import cycle.

MergeResult = Literal["fast-forward", "clean", "conflict"]


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------
#
# ``GitError`` is defined in :mod:`scistudio.core.versioning.errors` and
# re-exported here so ``scistudio.core.versioning.git_engine.GitError``
# continues to resolve for every existing importer (REST layer, package
# ``__init__``, downstream tests). The extraction broke the former lazy-
# import pair-cycle with :mod:`scistudio.core.versioning.git_binary` (see
# #1337 / PR #1344).

__all__ = [
    "GitEngine",
    "GitError",
    "HeadState",
    "MergeResult",
]


# Default identity for the seed initial commit (OQ-1 placeholder).
_DEFAULT_AUTHOR_NAME = "SciStudio User"
_DEFAULT_AUTHOR_EMAIL = "noreply@scistudio.local"
_DEFAULT_AUTHOR = f"{_DEFAULT_AUTHOR_NAME} <{_DEFAULT_AUTHOR_EMAIL}>"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class GitEngine:
    """Subprocess wrapper exposing the operations enumerated in ADR-039 §3.5.

    One instance per repository. Lazily resolves the bundled git binary
    on first use via :class:`GitBinary`.

    Method-body decomposition: per ADR-046 Addendum 1, the bound-method
    bodies live in private ``_*_ops.py`` siblings (``_commit_ops``,
    ``_history_ops``, ``_branch_ops``, ``_status_ops``, ``_merge_ops``).
    The bindings at the bottom of this class wire those functions into
    the public method surface; signature, behavior, and the ``self.``
    attribute reads they perform are identical to the pre-decomposition
    inline form.
    """

    def __init__(self, project_path: Path) -> None:
        self.project_path = Path(project_path).resolve()
        # Lazy GitBinary — keeps construction cheap.
        self._binary: Any | None = None

    @property
    def _git(self) -> Any:
        """Lazy-resolved :class:`GitBinary`."""
        if self._binary is None:
            self._binary = GitBinary.locate()
        return self._binary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        check: bool = True,
    ) -> Any:
        """Invoke git with project_path as default cwd."""
        return self._git.run(args, cwd=cwd or self.project_path, check=check)

    def _author_env(self) -> dict[str, str]:
        """Identity env that lets commit succeed on a fresh machine."""
        return {
            "GIT_AUTHOR_NAME": _DEFAULT_AUTHOR_NAME,
            "GIT_AUTHOR_EMAIL": _DEFAULT_AUTHOR_EMAIL,
            "GIT_COMMITTER_NAME": _DEFAULT_AUTHOR_NAME,
            "GIT_COMMITTER_EMAIL": _DEFAULT_AUTHOR_EMAIL,
        }

    # ------------------------------------------------------------------
    # Repository lifecycle (inline — uses module-level identity constants
    # at class-definition time; kept here for clarity)
    # ------------------------------------------------------------------

    def init_repository(self, project_path: Path) -> str:
        """Initialize new git repo + write .gitignore + initial commit.

        Returns the SHA of the initial commit. See ADR-039 §3.2, §3.9.
        """
        from scistudio.core.versioning.gitignore_template import write_default_gitignore

        target = Path(project_path).resolve()
        if not target.exists():
            raise FileNotFoundError(f"Project path does not exist: {target}")
        if not target.is_dir():
            raise NotADirectoryError(f"Project path is not a directory: {target}")
        if (target / ".git").exists():
            raise FileExistsError(f".git already exists at {target}")

        # git init. ``--initial-branch=main`` requires git ≥ 2.28.
        self._git.run(
            ["init", "--initial-branch=main", str(target)],
            cwd=target.parent if target.parent.exists() else None,
        )

        # Write .gitignore so the first commit captures at least one file.
        write_default_gitignore(target)

        # Stage everything.
        self._git.run(["add", "-A"], cwd=target)

        # Commit with config-injected identity so this succeeds even
        # on a fresh machine with no global user.name / user.email.
        self._git.run(
            [
                "-c",
                f"user.name={_DEFAULT_AUTHOR_NAME}",
                "-c",
                f"user.email={_DEFAULT_AUTHOR_EMAIL}",
                "commit",
                "-m",
                "Initial commit (auto-generated by SciStudio)",
                f"--author={_DEFAULT_AUTHOR}",
            ],
            cwd=target,
        )
        return self._rev_parse_head(target)

    def _rev_parse_head(self, cwd: Path) -> str:
        proc = self._git.run(["rev-parse", "HEAD"], cwd=cwd)
        return str(proc.stdout).strip()

    def is_repository(self, path: Path) -> bool:
        """Check whether ``path`` is the root of a git repository.

        See ADR-039 §3.2 line 94.

        Returns ``True`` when ``.git`` exists at *path* **regardless of whether
        it is a directory (normal clone) or a plain file (git worktree gitlink)**
        — ``Path.exists()`` covers both.  In a ``git worktree add`` worktree the
        ``.git`` entry is a plain text file whose content is
        ``gitdir: <path-to-real-.git>``; ``(path / ".git").exists()`` returns
        ``True`` for that case, so this method correctly reports ``True`` for
        both normal checkouts and linked worktrees.

        .. note::
            ADR-039 P3-A (#969): a future tri-state return
            ``Literal['repo', 'worktree', 'not-a-repo']`` would let callers
            distinguish a main checkout from a linked worktree.  That is out
            of scope for the current implementation; all callers today only
            need the boolean "is this under git control?" answer.
            Followup: see issue #969.
        """
        try:
            if (Path(path) / ".git").exists():
                return True
            # Rare fallback for unusual layouts.
            proc = self._git.run(["-C", str(path), "rev-parse", "--git-dir"], check=False)
            return bool(proc.returncode == 0)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Public method bindings — bodies live in private ``_*_ops.py``
    # siblings per ADR-046 Addendum 1. See each sibling module for the
    # canonical method body + docstring.
    # ------------------------------------------------------------------

    # Commit / log / diff / restore
    commit = _commit_ops._commit
    log = _history_ops._log
    diff = _history_ops._diff
    restore = _history_ops._restore
    _files_unchanged_vs_commit = _history_ops._files_unchanged_vs_commit

    # Branch / tag
    branches = _branch_ops._branches
    current_branch = _branch_ops._current_branch
    branch_create = _branch_ops._branch_create
    branch_switch = _branch_ops._branch_switch
    branch_delete = _branch_ops._branch_delete
    commits_reachable_only_from = _branch_ops._commits_reachable_only_from
    tag = _branch_ops._tag

    # Working-tree status
    status = _status_ops._status
    head_state = _status_ops._head_state

    # Merge / cherry-pick / conflict resolution
    merge = _merge_ops._merge
    cherry_pick = _merge_ops._cherry_pick
    merge_stage_file = _merge_ops._merge_stage_file
    merge_complete = _merge_ops._merge_complete
    merge_abort = _merge_ops._merge_abort
