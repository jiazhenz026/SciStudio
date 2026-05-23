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
BROAD_BYPASS=$(printf '%s\n' "$BYPASS_LABELS" | grep -E '^(human-authored|admin-approved:ai-override)$' || true)
LABEL_ARGS=()
while IFS= read -r label; do
  [ -n "$label" ] || continue
  LABEL_ARGS+=(--pr-label "$label")
done <<EOF
$BYPASS_LABELS
EOF

PR_BODY=$(SCISTUDIO_CMD="$CMD" python - <<'PY'
import os
import shlex
import sys
from pathlib import Path

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
        index += 1
    elif token.startswith("--body=") or token.startswith("-b="):
        value = token.split("=", 1)[1]
    elif token == "--body-file" and index + 1 < len(tokens):
        value = Path(tokens[index + 1]).read_text(encoding="utf-8")
        index += 1
    elif token.startswith("--body-file="):
        value = Path(token.split("=", 1)[1]).read_text(encoding="utf-8")
    if value is not None:
        print(value, end="")
        sys.exit(0)
    index += 1
sys.exit(2)
PY
) || {
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"ADR-042 gate: gh pr create must provide the real PR body via --body or --body-file. Use scripts/scistudio_pr_create.py for receipt-backed PR creation."}}'
  exit 0
}

if [ -n "$BROAD_BYPASS" ]; then
  OUTPUT=$(PYTHONPATH=src python -m scistudio.qa.governance.gate_record pr-ready \
    --repo-root . \
    --base "$BASE_REF" \
    --head HEAD \
    --pr-body "$PR_BODY" \
    "${LABEL_ARGS[@]}" 2>&1) || {
    REASON=$(printf '%s' "$OUTPUT" | python -c "import json,sys; print(json.dumps(sys.stdin.read()[:1800]))")
    echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":$REASON}}"
    exit 0
  }
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"ADR-042 local gate bypassed by broad override label; CI/review still runs."}}'
  exit 0
fi

if ! printf '%s' "$PR_BODY" | grep -qiE '(closes|fixes|resolves)[[:space:]]+#?[0-9]+'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"ADR-042 gate: gh pr create command must include a PR body with Closes/Fixes/Resolves #N."}}'
  exit 0
fi

OUTPUT=$(PYTHONPATH=src python -m scistudio.qa.governance.gate_record pr-ready \
  --repo-root . \
  --base "$BASE_REF" \
  --head HEAD \
  --pr-body "$PR_BODY" \
  "${LABEL_ARGS[@]}" 2>&1) || {
  REASON=$(printf '%s' "$OUTPUT" | python -c "import json,sys; print(json.dumps(sys.stdin.read()[:1800]))")
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":$REASON}}"
  exit 0
}

GATE_RECORD=$(SCISTUDIO_BRANCH="$BRANCH" python - <<'PY'
import json
import os
from pathlib import Path

branch = os.environ.get("SCISTUDIO_BRANCH", "")
records = []
for path in sorted(Path(".workflow/records").glob("*.json")):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        continue
    if data.get("branch") == branch:
        records.append(path.as_posix())
print(records[0] if len(records) == 1 else "")
PY
)

if [ -z "$GATE_RECORD" ]; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"ADR-042 gate: exactly one gate record must match the current branch before PR creation."}}'
  exit 0
fi

RECEIPT_OUTPUT=$(PYTHONPATH=src python -m scistudio.qa.governance.gate_receipt validate \
  --repo-root . \
  --gate-record "$GATE_RECORD" \
  --base "$BASE_REF" \
  --head HEAD \
  --pr-body "$PR_BODY" 2>&1) || {
  REASON=$(printf '%s' "$RECEIPT_OUTPUT" | python -c "import json,sys; print(json.dumps(sys.stdin.read()[:1800]))")
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":$REASON}}"
  exit 0
}

echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
