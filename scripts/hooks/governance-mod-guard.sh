#!/usr/bin/env bash
# Scaffold Claude PreToolUse hook for governance path edits.
set -eu

input="$(cat || true)"
cmd="$(printf '%s' "$input" | python -c "import json,sys; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || true)"

# TODO(#1113): Wire path-aware governance denial after ADR-043 §3 guard tooling
# and runtime hook activation are complete. Out of scope per ADR-043 §5 /
# ADR-044 §11. Followup: #1113.

if printf '%s' "$cmd" | grep -qE '(MAINTAINERS|CODEOWNERS|docs/identity/humans.yml|governance-changes.log|overrides.log)'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"Governance path touched; confirm explicit authority before editing."}}'
  exit 0
fi

echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
