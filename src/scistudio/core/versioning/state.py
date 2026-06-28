"""Public value types for ``scistudio.core.versioning``.

Holds :class:`HeadState`, the result of :meth:`GitEngine.head_state`. It lives
in its own leaf module so the status helpers can import it without importing the
engine. ``HeadState`` is also re-exported from ``git_engine`` for backward
compatibility.

This module must not import from any other ``scistudio.core.versioning``
sibling.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HeadState:
    """The repository HEAD: its commit SHA and whether the tree is dirty."""

    commit_sha: str
    """SHA of the current HEAD commit; empty string when there are no commits."""
    dirty: bool
    """``True`` when the working tree has uncommitted changes."""
