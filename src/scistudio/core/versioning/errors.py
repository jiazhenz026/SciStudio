"""Error envelope for ``scistudio.core.versioning``.

Holds :class:`GitError`, the exception type shared by the git-binary wrapper and
the git engine. It lives in its own leaf module so neither of those modules has
to import the other just to reference the error type. ``GitError`` is also
re-exported from ``git_engine`` for backward compatibility.

This module must not import from any other ``scistudio.core.versioning``
sibling.
"""

from __future__ import annotations


class GitError(RuntimeError):
    """A git invocation exited with a non-zero status.

    Carries enough context (exit code, captured stderr, and the git arguments)
    for the REST layer to render a structured error response.
    """

    def __init__(self, returncode: int, stderr: str, args: list[str]) -> None:
        """Build the error from a failed git invocation.

        Args:
            returncode: The non-zero exit code git returned.
            stderr: The captured standard-error text.
            args: The git arguments that were run (without the leading ``git``).
        """
        super().__init__(f"git {' '.join(args)} → exit {returncode}: {stderr.strip()}")
        self.returncode = returncode
        """The non-zero exit code git returned."""
        self.stderr = stderr
        """The captured standard-error text from the failed invocation."""
        self.git_args = args
        """The git arguments that were run (without the leading ``git``)."""
