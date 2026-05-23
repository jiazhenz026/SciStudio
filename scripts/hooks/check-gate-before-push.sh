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
if [ -z "$BRANCH" ] || [ "$BRANCH" = "main" ] || [ "$BRANCH" = "HEAD" ]; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
  exit 0
fi

BYPASS_LABELS=$(SCISTUDIO_CMD="$CMD" SCISTUDIO_BRANCH="$BRANCH" python - <<'PY'
import os
import subprocess

valid = {
    "human-authored",
    "admin-approved:ai-override",
    "admin-approved:core-change",
    "admin-approved:merge",
}
labels: set[str] = set()
for raw in os.environ.get("SCISTUDIO_GATE_BYPASS_LABELS", "").replace(",", " ").split():
    labels.add(raw.strip())

branch = os.environ.get("SCISTUDIO_BRANCH", "")
if branch:
    try:
        output = subprocess.check_output(
            ["gh", "pr", "view", branch, "--json", "labels", "--jq", ".labels[].name"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        labels.update(line.strip() for line in output.splitlines() if line.strip())
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

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
  LABEL_ARGS+=(--bypass-label "$label")
done <<EOF
$BYPASS_LABELS
EOF
OUTPUT=$(PYTHONPATH=src python -m scistudio.qa.governance.gate_record pre-push \
  --repo-root . \
  --base "$BASE_REF" \
  --head HEAD \
  "${LABEL_ARGS[@]}" 2>&1) || {
  REASON=$(printf '%s' "$OUTPUT" | python -c "import json,sys; print(json.dumps(sys.stdin.read()[:1800]))")
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":$REASON}}"
  exit 0
}

if [ -n "$BROAD_BYPASS" ]; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"ADR-042 local gate bypassed by broad override label; CI/review still runs."}}'
  exit 0
fi

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
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"ADR-042 gate: exactly one gate record must match the current branch before push."}}'
  exit 0
fi

RECEIPT_OUTPUT=$(PYTHONPATH=src python -m scistudio.qa.governance.gate_receipt validate \
  --repo-root . \
  --gate-record "$GATE_RECORD" \
  --base "$BASE_REF" \
  --head HEAD 2>&1) || {
  REASON=$(printf '%s' "$RECEIPT_OUTPUT" | python -c "import json,sys; print(json.dumps(sys.stdin.read()[:1800]))")
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":$REASON}}"
  exit 0
}

echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
