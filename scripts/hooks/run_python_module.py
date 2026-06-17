#!/usr/bin/env python3
"""Run a repository src-layout Python module from local hooks.

Local git hooks (pre-commit / commit-msg / pre-push) run through this launcher.
Git invokes hooks with repo-locating environment variables set -- in a *linked
worktree* it exports ``GIT_DIR`` (pointing at ``.git/worktrees/<name>``, whose
``commondir`` resolves to the real shared ``.git``) and ``GIT_INDEX_FILE``. If
the gate/pytest child this launcher runs inherits those, ANY git command that
child runs -- even from its own ``tmp_path`` cwd, since Git defaults the work
tree to the cwd when ``GIT_WORK_TREE`` is unset -- is redirected to the **real
shared repository**. That is the root cause of the issue #1609 corruption: a
test fixture's ``git commit`` / ``git init`` landed bogus commits on sibling
worktrees' branches and flipped ``core.bare`` on the shared config.

So this launcher scrubs the inherited git environment (``scrub_git_env``) before
running the target module. Kept self-contained and dependency-free on purpose:
the launcher is the one thing that must always scrub, so it must not rely on the
src tree being importable.
"""

from __future__ import annotations

import os
import runpy
import sys
from collections.abc import MutableMapping
from pathlib import Path

# Repo-locating git env vars, i.e. the output of ``git rev-parse
# --local-env-vars``. Hardcoded (so the scrub never forks a git process -- which
# would itself read the polluted env -- on the hook hot path) and MUST be kept in
# sync with that command's output. tests/scripts/test_run_python_module.py
# cross-checks this tuple against ``git rev-parse --local-env-vars``.
_GIT_LOCAL_ENV_VARS: tuple[str, ...] = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CONFIG",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
    "GIT_OBJECT_DIRECTORY",
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_GRAFT_FILE",
    "GIT_INDEX_FILE",
    "GIT_INTERNAL_SUPER_PREFIX",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_REPLACE_REF_BASE",
    "GIT_PREFIX",
    "GIT_SHALLOW_FILE",
    "GIT_COMMON_DIR",
)

# Identity vars are NOT reported by ``git rev-parse --local-env-vars`` (they set
# author/committer, not repo location), so they must be scrubbed separately. An
# inherited identity is what stamped the bogus ``SciStudio Agent`` commit in the
# issue #1609 incident.
_GIT_IDENTITY_ENV_VARS: tuple[str, ...] = (
    "GIT_AUTHOR_NAME",
    "GIT_AUTHOR_EMAIL",
    "GIT_AUTHOR_DATE",
    "GIT_COMMITTER_NAME",
    "GIT_COMMITTER_EMAIL",
    "GIT_COMMITTER_DATE",
)

GIT_INHERITED_ENV_VARS: tuple[str, ...] = (*_GIT_LOCAL_ENV_VARS, *_GIT_IDENTITY_ENV_VARS)


def scrub_git_env(environ: MutableMapping[str, str] | None = None) -> list[str]:
    """Drop inherited git repo-locating + identity vars from ``environ``.

    Defaults to the live ``os.environ``. Returns the variable names actually
    removed (for logging/testing). Idempotent: scrubbing a clean environment is
    a no-op.
    """

    env = os.environ if environ is None else environ
    removed: list[str] = []
    for var in GIT_INHERITED_ENV_VARS:
        if var in env:
            del env[var]
            removed.append(var)
    return removed


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: run_python_module.py <module> [args...]", file=sys.stderr)
        return 2

    # Drop git env vars Git injected into this hook process BEFORE launching the
    # target module; otherwise the child's git ops hit the real shared .git
    # (issue #1609).
    scrub_git_env()

    module = args[0]
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "src"))
    sys.argv = [module, *args[1:]]
    runpy.run_module(module, run_name="__main__", alter_sys=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
