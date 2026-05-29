#!/usr/bin/env bash
# PreToolUse hook on Agent — warns (does NOT block) when a non-Explore Agent
# dispatch is missing the [DISPATCH-TEMPLATE-V1: <role>] marker.
#
# Behavior: warns on stderr (does NOT block) when the marker is absent. The
# marker convention is part of the agent-dispatch templates under
# docs/ai-developer/templates/. This hook is a dispatch-hygiene reminder, not a
# quality gate; it is not wired into the evaluator.

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

For cascade/parallel dispatches, prompts MUST start with one of:
  [DISPATCH-TEMPLATE-V1: skeleton]
  [DISPATCH-TEMPLATE-V1: implement]
  [DISPATCH-TEMPLATE-V1: audit]
  [DISPATCH-TEMPLATE-V1: fix]

These templates live under docs/ai-developer/templates/ and contain the
mandatory hygiene + scope + CI rules every dispatched agent must follow.

If this is an unrelated Agent call (not part of a multi-agent dispatch),
ignore this warning and continue. The hook does not block; it only flags
potential drift from the dispatch protocol.
EOF

exit 0
