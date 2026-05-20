#!/bin/bash
# Claude/Codex PreToolUse hook: validate ADR-042 gate record before git push.

set -euo pipefail

INPUT=$(cat)
CMD=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")

if ! echo "$CMD" | grep -qE '^git push'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
  exit 0
fi

BRANCH=$(git branch --show-current 2>/dev/null || echo "")
if [ -z "$BRANCH" ] || ! echo "$BRANCH" | grep -qE '^(feat|fix|refactor|hotfix)/'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
  exit 0
fi

BASE_REF="${SCIEASY_GATE_BASE:-origin/main}"
OUTPUT=$(PYTHONPATH=src python -m scieasy.qa.governance.gate_record pre-push \
  --repo-root . \
  --base "$BASE_REF" \
  --head HEAD 2>&1) || {
  REASON=$(printf '%s' "$OUTPUT" | python -c "import json,sys; print(json.dumps(sys.stdin.read()[:1800]))")
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":$REASON}}"
  exit 0
}

echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
