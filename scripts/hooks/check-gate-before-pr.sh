#!/bin/bash
# Claude/Codex PreToolUse hook: validate ADR-042 gate readiness before gh pr create.
#
# Thin caller of the single shared evaluator (ADR-042 Addendum 6 §6): extract the
# PR body from the `gh pr create` argv into a temp file, then run
#   gate_record check --mode pre-pr --pr-body-file <path> --base origin/main --head HEAD
# No closing-keyword regex, label extraction, bypass vocabulary, or receipt step
# lives here — the evaluator's pre-pr mode owns all of that (PR-state-impossible
# findings are classified internally as pre-PR gaps, not caller-filtered).

set -euo pipefail

INPUT=$(cat)
CMD=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")

if ! echo "$CMD" | grep -qE '(^|[[:space:]])gh[[:space:]]+pr[[:space:]]+create([[:space:]]|$)'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
  exit 0
fi

BASE_REF="${SCISTUDIO_GATE_BASE:-origin/main}"

# Extract the PR body (from --body / --body-file) into a temp file. The evaluator
# requires the real PR body for issue-closure reconciliation.
BODY_FILE=$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/scistudio-pr-body.$$")
trap 'rm -f "$BODY_FILE"' EXIT

if ! SCISTUDIO_CMD="$CMD" python - "$BODY_FILE" <<'PY'
import os
import shlex
import sys
from pathlib import Path

out = Path(sys.argv[1])
try:
    tokens = shlex.split(os.environ.get("SCISTUDIO_CMD", ""))
except ValueError:
    sys.exit(1)

index = 0
while index < len(tokens):
    token = tokens[index]
    value = None
    if token in {"--body", "-b"} and index + 1 < len(tokens):
        value = tokens[index + 1]
    elif token.startswith("--body=") or token.startswith("-b="):
        value = token.split("=", 1)[1]
    elif token == "--body-file" and index + 1 < len(tokens):
        value = Path(tokens[index + 1]).read_text(encoding="utf-8")
    elif token.startswith("--body-file="):
        value = Path(token.split("=", 1)[1]).read_text(encoding="utf-8")
    if value is not None:
        out.write_text(value, encoding="utf-8")
        sys.exit(0)
    index += 1
sys.exit(2)
PY
then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"ADR-042 gate: gh pr create must provide the real PR body via --body or --body-file. Use scripts/scistudio_pr_create.py for gate-backed PR creation."}}'
  exit 0
fi

OUTPUT=$(PYTHONPATH=src python -m scistudio.qa.governance.gate_record check \
  --mode pre-pr \
  --base "$BASE_REF" \
  --head HEAD \
  --pr-body-file "$BODY_FILE" 2>&1) || {
  REASON=$(printf '%s' "$OUTPUT" | python -c "import json,sys; print(json.dumps(sys.stdin.read()[:1800]))")
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":$REASON}}"
  exit 0
}

echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
