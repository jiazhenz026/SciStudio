"""Private sibling for ``GitEngine`` commit operations.

This module is **package-private** per ADR-028 Addendum 1 §C9 +
ADR-046 Addendum 1 ("private functions, not helper classes"): every
public symbol is prefixed with an underscore, the module name itself
starts with an underscore, and it contains zero ``class`` definitions.
External callers must import :class:`GitEngine` from
:mod:`scistudio.core.versioning.git_engine`; importing helpers
directly is unsupported and the names may change without notice.

The function here was extracted from
:mod:`scistudio.core.versioning.git_engine` in issue #1472 (Phase 3
of the backend god-file refactor umbrella #1427) per ADR-046
Addendum 1. The bound method body is byte-identical to the original;
only ``self.`` was rewritten to ``engine.``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scistudio.core.versioning.errors import GitError

if TYPE_CHECKING:
    from scistudio.core.versioning.git_engine import GitEngine

# Identity constants (duplicated from git_engine to avoid a cycle at
# import-time; values must stay in sync with the canonical definitions
# in ``scistudio.core.versioning.git_engine``).
_DEFAULT_AUTHOR_NAME = "SciStudio User"
_DEFAULT_AUTHOR_EMAIL = "noreply@scistudio.local"


def _commit(
    engine: GitEngine,
    message: str,
    *,
    files: list[str] | None = None,
    author: str | None = None,
    prefix: str | None = None,
) -> str:
    """Create a new commit; return the new HEAD SHA. See ADR-039 §3.4."""
    if not message or not message.strip():
        raise ValueError("Commit message must not be empty.")

    if prefix is not None:
        if prefix not in ("auto", "agent"):
            raise ValueError(f"Invalid commit prefix {prefix!r} — only 'auto' or 'agent' allowed.")
        final_message = f"{prefix}: {message}"
    else:
        final_message = message

    # Stage.
    if files is None:
        engine._run(["add", "-A"])
    else:
        engine._run(["add", "--", *files])

    # D39-3.2 (#968) P2-C: empty-repo edge case.
    #
    # ``git diff --cached --quiet`` against a missing HEAD (a freshly
    # ``git init``-ed repo with no commits) historically returned 0
    # even when the index was non-empty — making the empty-tree guard
    # below raise ``nothing to commit`` for what is actually the
    # repo's initial commit. Detect the no-HEAD case first via
    # ``git rev-parse --verify HEAD`` (rc != 0). When HEAD is missing,
    # fall back to ``git diff --cached --quiet HEAD`` against the
    # empty-tree object so the staged-files check is correct.
    head_check = engine._run(["rev-parse", "--verify", "-q", "HEAD"], check=False)
    has_head = head_check.returncode == 0
    if has_head:
        proc = engine._run(["diff", "--cached", "--quiet"], check=False)
        tree_is_empty = proc.returncode == 0
    else:
        # No HEAD: ask git directly whether the index has anything
        # staged. ``ls-files --cached`` prints one line per staged
        # entry; empty stdout means the index is empty.
        ls_proc = engine._run(["ls-files", "--cached"], check=False)
        tree_is_empty = not (ls_proc.stdout or "").strip()
    if tree_is_empty:
        raise GitError(1, "nothing to commit, working tree clean", ["commit"])

    # Build commit invocation with config-injected identity so
    # commits succeed even when the user has no global user.name.
    commit_args = [
        "-c",
        f"user.name={_DEFAULT_AUTHOR_NAME}",
        "-c",
        f"user.email={_DEFAULT_AUTHOR_EMAIL}",
        "commit",
        "-m",
        final_message,
        "--cleanup=strip",
    ]
    if author:
        commit_args.extend(["--author", author])
    engine._run(commit_args)
    return engine._rev_parse_head(engine.project_path)
