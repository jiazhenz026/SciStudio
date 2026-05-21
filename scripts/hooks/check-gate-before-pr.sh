#!/bin/bash
# Claude/Codex PreToolUse hook: validate ADR-042 gate record before gh pr create.

set -euo pipefail

INPUT=$(cat)
CMD=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")

if ! echo "$CMD" | grep -qE '(^|[[:space:]])gh[[:space:]]+pr[[:space:]]+create([[:space:]]|$)'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
  exit 0
fi

BRANCH=$(git branch --show-current 2>/dev/null || echo "")
if [ -z "$BRANCH" ] || [ "$BRANCH" = "main" ] || [ "$BRANCH" = "HEAD" ]; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
  exit 0
fi

BYPASS_LABELS=$(SCISTUDIO_CMD="$CMD" python - <<'PY'
import os
import shlex

valid = {
    "human-authored",
    "admin-approved:ai-override",
    "admin-approved:core-change",
    "admin-approved:merge",
}
labels: set[str] = set()
for raw in os.environ.get("SCISTUDIO_GATE_BYPASS_LABELS", "").replace(",", " ").split():
    labels.add(raw.strip())

try:
    tokens = shlex.split(os.environ.get("SCISTUDIO_CMD", ""))
except ValueError:
    tokens = []
index = 0
while index < len(tokens):
    token = tokens[index]
    value = None
    if token in {"--label", "-l"} and index + 1 < len(tokens):
        value = tokens[index + 1]
        index += 1
    elif token.startswith("--label="):
        value = token.split("=", 1)[1]
    elif token.startswith("-l="):
        value = token.split("=", 1)[1]
    if value is not None:
        labels.update(item.strip() for item in value.split(",") if item.strip())
    index += 1

override_like = {
    label
    for label in labels
    if label in valid or label.startswith("human") or label.startswith("admin-approved")
}
print("\n".join(sorted(override_like)))
PY
)

BASE_REF="${SCISTUDIO_GATE_BASE:-origin/main}"
LABEL_ARGS=()
while IFS= read -r label; do
  [ -n "$label" ] || continue
  LABEL_ARGS+=(--pr-label "$label")
done <<EOF
$BYPASS_LABELS
EOF

if [ -n "$BYPASS_LABELS" ]; then
  OUTPUT=$(PYTHONPATH=src python -m scistudio.qa.governance.gate_record pr-ready \
    --repo-root . \
    --base "$BASE_REF" \
    --head HEAD \
    --pr-body "$CMD" \
    "${LABEL_ARGS[@]}" 2>&1) || {
    REASON=$(printf '%s' "$OUTPUT" | python -c "import json,sys; print(json.dumps(sys.stdin.read()[:1800]))")
    echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":$REASON}}"
    exit 0
  }
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"ADR-042 local gate bypassed by approved override label; CI/review still runs."}}'
  exit 0
fi

if ! echo "$CMD" | grep -qiE '(closes|fixes|resolves)[[:space:]]+#?[0-9]+'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"ADR-042 gate: gh pr create command must include a PR body with Closes/Fixes/Resolves #N."}}'
  exit 0
fi

OUTPUT=$(PYTHONPATH=src python -m scistudio.qa.governance.gate_record pr-ready \
  --repo-root . \
  --base "$BASE_REF" \
  --head HEAD \
  --pr-body "$CMD" \
  "${LABEL_ARGS[@]}" 2>&1) || {
  REASON=$(printf '%s' "$OUTPUT" | python -c "import json,sys; print(json.dumps(sys.stdin.read()[:1800]))")
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":$REASON}}"
  exit 0
}

echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
