#!/usr/bin/env sh
set -eu

REPO_ROOT="$(git rev-parse --show-toplevel)"
PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  python -m scistudio.qa.governance.worktree_write_guard --hook-json
