#!/usr/bin/env sh
# Claude/Codex PreToolUse hook on Edit|Write|MultiEdit|NotebookEdit|apply_patch.
#
# Minimal worktree write guard (ADR-042 Addendum 6 §6.1): block only the
# "forgot to create a worktree" case — an AI edit whose target resolves into the
# MAIN repo working tree. All linked-worktree and non-repo writes are allowed.
# The block decision lives in the Python module and does not depend on cwd; this
# shell only puts the package on PYTHONPATH and forwards stdin/exit code.
set -eu

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  python -m scistudio.qa.governance.worktree_write_guard --hook-json
