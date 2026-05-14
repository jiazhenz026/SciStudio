#!/usr/bin/env bash
# PreToolUse hook on Agent — enforces the [DISPATCH-TEMPLATE-V1: <role>] marker
# on every non-Explore Agent dispatch for the ADR-035/036 cascade.
#
# Behavior: warns on stderr (does NOT block) when the marker is absent.
# Codex auto-review on PR #852 flagged the original boilerplate as referring
# to a non-existent hook (P2); this script closes that gap.

INPUT="$(cat 2>/dev/null || true)"

PARSED=$(printf '%s' "$INPUT" | python -c "
import sys, json
try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input', {})
    sub = ti.get('subagent_type', '')
    prompt = ti.get('prompt', '')
    has_marker = '[DISPATCH-TEMPLATE-V1:' in prompt
    print(f'sub={sub}|marker={has_marker}')
except Exception:
    print('sub=|marker=true')
" 2>/dev/null)

# Parse "sub=...|marker=..."
SUBAGENT=$(printf '%s' "$PARSED" | sed -n 's/^sub=\(.*\)|.*$/\1/p')
HAS_MARKER=$(printf '%s' "$PARSED" | sed -n 's/^.*|marker=\(.*\)$/\1/p')

# Read-only Explore agents don't need the marker
case "$SUBAGENT" in
  Explore|explore|""|claude-code-guide|statusline-setup|Plan|plan)
    exit 0
    ;;
esac

# Non-Explore agents: enforce the marker
if [ "$HAS_MARKER" = "True" ]; then
  exit 0
fi

cat >&2 <<'EOF'
[agent-template enforcement]
You are dispatching a non-Explore Agent without the [DISPATCH-TEMPLATE-V1: <role>] marker.

For ADR-035/036 cascade dispatches, prompts MUST start with one of:
  [DISPATCH-TEMPLATE-V1: skeleton]
  [DISPATCH-TEMPLATE-V1: implement]
  [DISPATCH-TEMPLATE-V1: audit]
  [DISPATCH-TEMPLATE-V1: fix]

These templates live at docs/planning/agent-prompt-templates/<role>-agent.md
and contain the mandatory hygiene + scope + CI rules.

If this is an unrelated Agent call (not part of the ADR-035/036 cascade),
ignore this warning and continue. The hook does not block; it only flags
potential drift from the dispatch protocol.

Reference: PR #852 Codex P2 closure — scripts/hooks/check-agent-template.sh
ships in the repo and is wired in .claude/settings.json (PreToolUse, Agent
matcher).
EOF

exit 0
