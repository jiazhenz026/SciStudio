#!/usr/bin/env bash
# Scaffold Claude PreToolUse hook for pytest timeout reminders.
set -eu

input="$(cat || true)"
cmd="$(printf '%s' "$input" | python -c "import json,sys; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || true)"

# TODO(#1113): Convert this reminder into runtime-specific command mutation or
# enforcement after ADR-043 §5 hook activation is verified. Out of scope per
# ADR-043 §5 / ADR-044 §11. Followup: #1113.

if printf '%s' "$cmd" | grep -qE '(^|[ ;])pytest([ ;]|$)' &&
   ! printf '%s' "$cmd" | grep -q -- '--timeout'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"Reminder: prefer pytest --timeout=60 for focused SciEasy tests."}}'
  exit 0
fi

echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
