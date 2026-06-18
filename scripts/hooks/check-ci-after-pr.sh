#!/bin/bash
# Claude Code PostToolUse hook: after gh pr create, remind agent to check CI.
# Outputs a blocking message that the agent must address.

set -e

INPUT=$(cat)
CMD=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")

# Only trigger after gh pr create
if ! echo "$CMD" | grep -qE 'gh pr create'; then
  exit 0
fi

# Extract PR number from tool output (stdout)
STDOUT=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('stdout',''))" 2>/dev/null || echo "")
PR_URL=$(echo "$STDOUT" | grep -oE 'https://github.com/[^ ]+/pull/[0-9]+' | head -1)

if [ -z "$PR_URL" ]; then
  exit 0
fi

PR_NUM=$(echo "$PR_URL" | grep -oE '[0-9]+$')

cat <<EOF
⚠️ MANDATORY POST-PR STEPS: PR #${PR_NUM} created (${PR_URL}).
You MUST now:
1. Record PR provenance in the gate ledger:
   python -m scistudio.qa.governance.gate_record finalize --pr ${PR_URL}
2. Wait 2-3 minutes for CI to start
3. Run: gh pr checks ${PR_NUM} --watch
4. If ANY check fails: diagnose, fix, push, repeat until ALL GREEN
5. Do NOT report the PR as done until CI passes

This is a NON-NEGOTIABLE requirement per CLAUDE.md §6.4 and ADR-042 Addendum 6.
EOF