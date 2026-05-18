#!/usr/bin/env bash
# Scaffold Claude PreToolUse hook for gh pr merge tracking-branch checks.
set -eu

input="$(cat || true)"
cmd="$(printf '%s' "$input" | python -c "import json,sys; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || true)"

# TODO(#1113): Make this a deterministic merge guard after ADR-043 §5 hook
# activation is verified. Out of scope per ADR-043 §5 / ADR-044 §11.
# Followup: #1113.

if printf '%s' "$cmd" | grep -qE 'gh pr merge'; then
  upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
  if [ -z "$upstream" ]; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"Reminder: verify tracking branch before PR merge."}}'
    exit 0
  fi
fi

echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
