"""Thin status helpers over :meth:`GitEngine.status`.

Convenience wrappers for callers that only need a quick "is it dirty?" or
"what changed?" answer rather than the full status dict — primarily the pre-run
auto-commit hook and the status-badge polling endpoint.
"""

from __future__ import annotations

from pathlib import Path


def is_dirty(project_path: Path) -> bool:
    """Return ``True`` when the working tree has uncommitted changes.

    Args:
        project_path: The project repository to check.

    Returns:
        ``True`` if there are modified, staged, or untracked files.
    """
    from scistudio.core.versioning.git_engine import GitEngine

    engine = GitEngine(project_path)
    return bool(engine.status()["dirty"])


def modified_files(project_path: Path) -> list[str]:
    """Return the modified, staged, and untracked paths (sorted, de-duplicated).

    Args:
        project_path: The project repository to inspect.

    Returns:
        A sorted list of changed file paths.
    """
    from scistudio.core.versioning.git_engine import GitEngine

    engine = GitEngine(project_path)
    s = engine.status()
    combined = set(s["modified"]) | set(s["staged"]) | set(s["untracked"])
    return sorted(combined)
