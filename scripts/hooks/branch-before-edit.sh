#!/usr/bin/env bash
# Scaffold Claude PreToolUse hook for Edit/Write branch checks.
set -eu

branch="$(git branch --show-current 2>/dev/null || true)"

# TODO(#1113): Wire this hook into runtime settings after ADR-043 §5 hook
# activation is verified across supported runtimes. Out of scope per ADR-043
# §5 / ADR-044 §11. Followup: #1113.

if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Refusing edits on main/master; create a task branch first."}}'
  exit 0
fi

echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
