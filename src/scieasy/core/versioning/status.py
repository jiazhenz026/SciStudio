"""Thin status helpers over :class:`GitEngine.status` (ADR-039 §3.5).

Convenience wrappers used by callers that don't need the full status
dict — primarily the runtime hooks
(``ApiRuntime.start_workflow`` pre-run auto-commit) and the
GitStatusBadge polling endpoint.
"""

from __future__ import annotations

from pathlib import Path


def is_dirty(project_path: Path) -> bool:
    """Return True if the working tree has uncommitted changes.

    See ADR-039 §3.4 line 148 (pre-run auto-commit predicate).
    """
    from scieasy.core.versioning.git_engine import GitEngine

    engine = GitEngine(project_path)
    return bool(engine.status()["dirty"])


def modified_files(project_path: Path) -> list[str]:
    """Return paths of modified + staged + untracked files (sorted, deduped).

    See ADR-039 §3.5 line 244 (CommitDialog auto-detected list).
    """
    from scieasy.core.versioning.git_engine import GitEngine

    engine = GitEngine(project_path)
    s = engine.status()
    combined = set(s["modified"]) | set(s["staged"]) | set(s["untracked"])
    return sorted(combined)
