"""Thin status helpers over :class:`GitEngine.status` (ADR-039 §3.5).

These are convenience wrappers used by callers that don't need the full
status dict — primarily the runtime hooks
(``ApiRuntime.start_workflow`` pre-run auto-commit) and the
GitStatusBadge polling endpoint.

Skeleton phase: bodies raise ``NotImplementedError``. The impl agent
(D39-2.2b) wires these to :class:`GitEngine` once that class is
implemented.
"""

from __future__ import annotations

from pathlib import Path


def is_dirty(project_path: Path) -> bool:
    """Return True if the working tree has uncommitted changes.

    Purpose
    -------
    Cheap predicate for "should pre-run auto-commit fire?" and "is the
    GitStatusBadge red?". Backed by :meth:`GitEngine.status`'s ``dirty``
    field.

    Signature contract
    ------------------
    - Input: ``project_path`` — path to a SciEasy project (assumed to
      be a git repo; caller branches on ``GitEngine.is_repository``).
    - Output: ``True`` if any modified / staged / untracked / conflicted
      files exist, else ``False``.
    - Errors: :class:`GitError` propagated if the underlying status call
      fails.

    Implementation steps (for D39-2.2b)
    -----------------------------------
    1. Construct ``GitEngine(project_path)``.
    2. Return ``engine.status()["dirty"]``.

    Edge cases
    ----------
    - Path is not a repo — propagates GitError. Callers should guard
      with ``GitEngine.is_repository`` first.

    Test plan
    ---------
    - ``test_is_dirty_clean_tree`` — fresh commit → False.
    - ``test_is_dirty_modified_file`` — edit → True.
    - ``test_is_dirty_untracked_file`` — new file → True.

    ADR references
    --------------
    - §3.4 line 148 (used for pre-run auto-commit predicate).
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


def modified_files(project_path: Path) -> list[str]:
    """Return paths of modified + staged + untracked files.

    Purpose
    -------
    Backs the CommitDialog's auto-detected-files list (ADR-039 §3.5
    lines 230-244). The template ``# M  workflows/...`` lines come from
    here.

    Signature contract
    ------------------
    - Input: ``project_path``.
    - Output: list of repo-relative paths, deduplicated, sorted.
    - Errors: GitError propagated.

    Implementation steps (for D39-2.2b)
    -----------------------------------
    1. Construct ``GitEngine(project_path)``.
    2. Call ``engine.status()``.
    3. Concatenate ``modified + staged + untracked`` lists (exclude
       conflicted — those are handled separately).
    4. Dedup (set), sort, return as list.

    Edge cases
    ----------
    - Clean tree → empty list.
    - Large repos with hundreds of untracked files — the list is
      passed to the UI which can truncate; engine returns everything.

    Test plan
    ---------
    - ``test_modified_files_empty_when_clean`` → ``[]``.
    - ``test_modified_files_includes_untracked`` — new file appears.
    - ``test_modified_files_sorted_dedup`` — same file modified AND
      staged → appears once.

    ADR references
    --------------
    - §3.5 line 244.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")
