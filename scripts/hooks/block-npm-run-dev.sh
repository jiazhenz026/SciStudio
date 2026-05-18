#!/usr/bin/env bash
# Scaffold Claude PreToolUse hook to block accidental long-lived frontend dev servers.
set -eu

input="$(cat || true)"
cmd="$(printf '%s' "$input" | python -c "import json,sys; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || true)"

# TODO(#1113): Wire this hook only after the frontend smoke workflow defines the
# approved long-lived-server exception path. Out of scope per ADR-043 §5 /
# ADR-044 §11. Followup: #1113.

if printf '%s' "$cmd" | grep -qE 'npm run dev'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Do not start long-lived npm run dev unless the task explicitly requires it."}}'
  exit 0
fi

echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
