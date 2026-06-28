"""SciStudio source-version-control subsystem.

Wraps a bundled portable git CLI binary (MinGit on Windows, static-built git on
macOS/Linux) so every SciStudio project is a real git repository with standard
git semantics: history, diff, restore, branch, merge, and cherry-pick. Bundling
git means users do not need git installed.

Public surface:

The package exposes the engine (:class:`GitEngine`), the binary locator
(:class:`GitBinary`), its "git is unavailable" error
(:class:`BundledGitMissing`), the git-error envelope (:class:`GitError`), the
default ``.gitignore`` template (:data:`DEFAULT_GITIGNORE`) and its writer
(:func:`write_default_gitignore`), and the working-tree status helpers
(:func:`is_dirty`, :func:`modified_files`). The REST layer calls into this
package; nothing else in the runtime should shell out to git directly.
"""

from __future__ import annotations

from scistudio.core.versioning.git_binary import BundledGitMissing, GitBinary
from scistudio.core.versioning.git_engine import GitEngine, GitError
from scistudio.core.versioning.gitignore_template import (
    DEFAULT_GITIGNORE,
    write_default_gitignore,
)
from scistudio.core.versioning.status import is_dirty, modified_files

# D39-3.2 (#968): the standalone asyncio-poll ``GitChangeWatcher`` was
# collapsed into ``scistudio.api.routes.workflow_watcher._GitHeadHandler``
# (watchdog Observer) which emits the canonical ``commit_sha`` field on
# ``git.head_changed`` matching the frontend reader. Importers that
# previously consumed ``GitChangeWatcher`` should use the unified
# watcher's ``start_for_project`` API instead.

__all__ = [
    "DEFAULT_GITIGNORE",
    "BundledGitMissing",
    "GitBinary",
    "GitEngine",
    "GitError",
    "is_dirty",
    "modified_files",
    "write_default_gitignore",
]
