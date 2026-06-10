#!/bin/bash
# Claude/Codex PreToolUse hook: validate the ADR-042 gate ledger before git push.
#
# Thin caller of the single shared evaluator (ADR-042 Addendum 6 §6):
#   gate_record check --mode pre-push --base origin/main --head HEAD
# No bypass vocabulary, protected-path list, or receipt step lives here — the
# evaluator owns all of that. The hook only forwards the exit code.

set -euo pipefail

INPUT=$(cat)
CMD=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")

if ! echo "$CMD" | grep -qE '^git push'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
  exit 0
fi

BASE_REF="${SCISTUDIO_GATE_BASE:-origin/main}"

OUTPUT=$(PYTHONPATH=src python -m scistudio.qa.governance.gate_record check \
  --mode pre-push \
  --base "$BASE_REF" \
  --head HEAD 2>&1) || {
  REASON=$(printf '%s' "$OUTPUT" | python -c "import json,sys; print(json.dumps(sys.stdin.read()[:1800]))")
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":$REASON}}"
  exit 0
}

echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
