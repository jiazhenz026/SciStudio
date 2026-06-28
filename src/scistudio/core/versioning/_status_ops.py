"""Private sibling for ``GitEngine`` working-tree status operations.

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

from scistudio.core.versioning.state import HeadState

if TYPE_CHECKING:
    from scistudio.core.versioning.git_engine import GitEngine


def _status(engine: GitEngine) -> dict[str, Any]:
    """Return the working-tree status as a dict.

    Returns:
        A dict with ``dirty`` (bool) and the path lists ``modified``,
        ``staged``, ``untracked``, and ``conflicted``. Clean defaults are
        returned when *path* is not a git repository.
    """
    proc = engine._run(["status", "--porcelain=v2", "--branch"], check=False)
    if proc.returncode != 0:
        # Most common cause: not a git repo. Return clean defaults.
        return {
            "dirty": False,
            "modified": [],
            "staged": [],
            "untracked": [],
            "conflicted": [],
        }

    modified: list[str] = []
    staged: list[str] = []
    untracked: list[str] = []
    conflicted: list[str] = []

    for raw_line in (proc.stdout or "").splitlines():
        if not raw_line:
            continue
        tag = raw_line[0]
        if tag == "#":
            continue
        if tag == "?":
            # Untracked: ``? <path>``
            parts = raw_line.split(" ", 1)
            if len(parts) == 2:
                untracked.append(parts[1])
            continue
        if tag == "!":
            # Ignored — skip.
            continue
        if tag == "u":
            # Unmerged entry: ``u <XY> <sub> <m1> <m2> <m3> <mw> <h1> <h2> <h3> <path>``
            parts = raw_line.split(" ", 10)
            if len(parts) >= 11:
                conflicted.append(parts[10])
            continue
        if tag == "1":
            # Ordinary changed: ``1 <XY> ... <path>``
            parts = raw_line.split(" ", 8)
            if len(parts) < 9:
                continue
            xy = parts[1]
            path = parts[8]
            x, y = xy[0], xy[1]
            if x != ".":
                staged.append(path)
            if y != ".":
                modified.append(path)
            continue
        if tag == "2":
            # Rename / copy: ``2 <XY> ... <path><tab><origPath>``
            parts = raw_line.split(" ", 9)
            if len(parts) < 10:
                continue
            xy = parts[1]
            rest = parts[9]
            # rest is "<path>\t<origPath>"
            path = rest.split("\t", 1)[0]
            x, y = xy[0], xy[1]
            if x != ".":
                staged.append(path)
            if y != ".":
                modified.append(path)
            continue

    dirty = bool(modified or staged or untracked or conflicted)
    return {
        "dirty": dirty,
        "modified": sorted(set(modified)),
        "staged": sorted(set(staged)),
        "untracked": sorted(set(untracked)),
        "conflicted": sorted(set(conflicted)),
    }


def _head_state(engine: GitEngine) -> HeadState:
    """Return the current HEAD commit SHA and whether the tree is dirty.

    Returns:
        A :class:`~scistudio.core.versioning.state.HeadState` with the HEAD SHA
        (empty string when there are no commits) and the dirty flag.
    """
    proc = engine._run(["rev-parse", "HEAD"], check=False)
    if proc.returncode != 0:
        return HeadState("", False)
    sha = (proc.stdout or "").strip()
    return HeadState(sha, engine.status()["dirty"])
