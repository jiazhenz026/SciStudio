#!/usr/bin/env sh
# Claude/Codex PreToolUse hook on Edit|Write|MultiEdit|NotebookEdit|apply_patch.
#
# Minimal worktree write guard (ADR-042 Addendum 6 §6.1): block only the
# "forgot to create a worktree" case — an AI edit whose target resolves into the
# MAIN repo working tree. All linked-worktree and non-repo writes are allowed.
# The block decision lives in the Python module and does not depend on cwd; this
# shell only puts the package on PYTHONPATH and forwards stdin/exit code.
set -eu

# PYTHONPATH entry separator (#2030). This is a POSIX shell script, but on
# Windows it runs under Git Bash while invoking the *Windows* interpreter, which
# splits PYTHONPATH on ';' — not ':'. Joining with ':' there produced a single
# unusable entry, so `import scistudio` failed and the guard exited 1. A
# PreToolUse hook exiting 1 is a non-blocking error, so the guard silently
# stopped guarding: it failed OPEN, and an agent that forgot its worktree could
# write into the main checkout unchallenged. Only reachable when the caller
# already exported PYTHONPATH (common in this repo, since `pip install -e .` is
# forbidden and callers point PYTHONPATH at ./src).
case "${OS:-}$(uname -s 2>/dev/null || echo)" in
  Windows_NT*|*MINGW*|*MSYS*) PATH_SEP=';' ;;
  *) PATH_SEP=':' ;;
esac

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+$PATH_SEP$PYTHONPATH}" \
  python -m scistudio.qa.governance.worktree_write_guard --hook-json
