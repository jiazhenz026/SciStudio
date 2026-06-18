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

# Resolve the diff base for the gate check (#1345). Precedence:
#   1. the PR's actual target branch parsed from `gh pr create --base <ref>`
#      (stacked PRs target an umbrella branch, NOT main; checking against main
#      would pull the umbrella's commits into the child's scope and false-fail);
#   2. a `# SCISTUDIO_GATE_BASE=<ref>` token embedded in the command (the env var
#      does NOT propagate into the harness hook subprocess, so an inline command
#      comment is the only agent-side override that survives);
#   3. the SCISTUDIO_GATE_BASE environment variable when it IS set;
#   4. origin/main.
# A bare branch name (e.g. `umbrella/x`) is resolved against `origin/` so the
# gate diffs against the remote target the PR will actually merge into.
BASE_REF=$(SCISTUDIO_CMD="$CMD" SCISTUDIO_ENV_BASE="${SCISTUDIO_GATE_BASE:-}" python - <<'PY'
import os
import re
import shlex

cmd = os.environ.get("SCISTUDIO_CMD", "")
try:
    tokens = shlex.split(cmd)
except ValueError:
    tokens = []

base = None
index = 0
while index < len(tokens):
    token = tokens[index]
    if token in {"--base", "-B"} and index + 1 < len(tokens):
        base = tokens[index + 1]
        break
    if token.startswith("--base="):
        base = token.split("=", 1)[1]
        break
    if token.startswith("-B="):
        base = token.split("=", 1)[1]
        break
    index += 1

# Command-token override survives even when --base was omitted (env var does not
# propagate into the hook subprocess): `gh pr create ... # SCISTUDIO_GATE_BASE=ref`.
if base is None:
    match = re.search(r"SCISTUDIO_GATE_BASE=([^\s#]+)", cmd)
    if match:
        base = match.group(1)

if base is None:
    base = os.environ.get("SCISTUDIO_ENV_BASE") or "origin/main"

base = base.strip()
# Normalize a bare local branch name to its remote-tracking ref so the gate
# diffs against what the PR merges into. Leave explicit remotes / refspecs alone.
if base and "/" not in base:
    base = f"origin/{base}"
elif base.startswith("origin/") or base.startswith("refs/"):
    pass
elif "/" in base and not base.startswith(("origin/", "upstream/", "refs/")):
    # e.g. "umbrella/arch-drift" -> origin/umbrella/arch-drift
    base = f"origin/{base}"
print(base)
PY
)
BASE_REF="${BASE_REF:-origin/main}"

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
