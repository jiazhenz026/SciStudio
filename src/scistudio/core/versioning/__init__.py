"""SciStudio source-version-control subsystem (ADR-039).

This package wraps a **bundled portable git CLI binary** (MinGit on Windows,
static-built git on macOS/Linux) so every SciStudio project is a real git
repository with standard git semantics: history, diff, restore, branch,
merge, cherry-pick, stash.

Public surface
--------------

The package exposes the engine, binary locator, default ``.gitignore``
template helper, working-tree status helpers, and the external-change
watcher. The REST layer at ``scistudio.api.routes.git`` calls into this
module; nothing else in the runtime should shell out to git directly.

ADR references
--------------

- §3.1 — bundled git CLI engine decision
- §3.2 — auto-init on project open
- §3.3 — default ``.gitignore`` template
- §3.4 — pre-run auto-commit (auto: prefix)
- §3.4a — agent commit prefix (agent:)
- §3.5 — v1 feature set (~15 endpoints)
- §3.5a — Monaco-based conflict resolution
- §3.6 — restore semantics (soft restore default)
- §3.7 — branch UI scope (full v1 ops)
- §3.8 — external git changes respected via watcher

Skeleton phase (D39-2.2a)
-------------------------

All public callables in this package currently raise
``NotImplementedError`` with detailed comment blocks describing what the
impl agent (D39-2.2b) must write. Do not import from this package in
production code paths until D39-2.2b lands; importing the module to
inspect signatures is safe.
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
