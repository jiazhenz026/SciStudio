"""Error envelope for ``scistudio.core.versioning`` (ADR-039).

Holds the :class:`GitError` exception type shared by
:mod:`scistudio.core.versioning.git_binary` and
:mod:`scistudio.core.versioning.git_engine`. Extracting it here breaks the
former pair-cycle between those modules (#1337 / PR #1344) so neither has
to use lazy imports to reference the other.

This module MUST NOT import from any other ``scistudio.core.versioning``
sibling — that constraint is what makes it a safe cycle-breaking shim.
``GitError`` is still re-exported from ``git_engine`` for backward
compatibility with the public ADR-039 governs surface.
"""

from __future__ import annotations


class GitError(RuntimeError):
    """A git invocation returned non-zero exit.

    Carries enough information to render a structured 500 / 409 / 422
    response in the REST layer (see ADR-039 §3.1, §3.5).
    """

    def __init__(self, returncode: int, stderr: str, args: list[str]) -> None:
        super().__init__(f"git {' '.join(args)} → exit {returncode}: {stderr.strip()}")
        self.returncode = returncode
        self.stderr = stderr
        self.git_args = args
