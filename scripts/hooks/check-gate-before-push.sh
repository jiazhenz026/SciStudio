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

# Resolve the diff base for the pre-push gate (#1345). The SCISTUDIO_GATE_BASE
# env var does NOT propagate into the harness hook subprocess, so for stacked
# work (a branch whose real base is an umbrella branch, not main) honor a
# `# SCISTUDIO_GATE_BASE=<ref>` token embedded in the `git push` command as the
# agent-side override. Precedence: command-token > env var > origin/main. A bare
# branch name is normalized to its origin/ remote-tracking ref.
BASE_REF=$(SCISTUDIO_CMD="$CMD" SCISTUDIO_ENV_BASE="${SCISTUDIO_GATE_BASE:-}" python - <<'PY'
import os
import re

cmd = os.environ.get("SCISTUDIO_CMD", "")
base = None
match = re.search(r"SCISTUDIO_GATE_BASE=([^\s#]+)", cmd)
if match:
    base = match.group(1)
if base is None:
    base = os.environ.get("SCISTUDIO_ENV_BASE") or "origin/main"
base = base.strip()
if base and "/" not in base:
    base = f"origin/{base}"
elif not base.startswith(("origin/", "upstream/", "refs/")) and "/" in base:
    base = f"origin/{base}"
print(base)
PY
)
BASE_REF="${BASE_REF:-origin/main}"

OUTPUT=$(PYTHONPATH=src python -m scistudio.qa.governance.gate_record check \
  --mode pre-push \
  --base "$BASE_REF" \
  --head HEAD 2>&1) || {
  REASON=$(printf '%s' "$OUTPUT" | python -c "import json,sys; print(json.dumps(sys.stdin.read()[:1800]))")
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":$REASON}}"
  exit 0
}

echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
