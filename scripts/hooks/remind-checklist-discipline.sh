#!/usr/bin/env bash
# PostToolUse hook — fires after:
#  (a) Edit/Write/MultiEdit/NotebookEdit on docs/planning/adr-*-checklist.md
#  (b) a TaskStop call (dispatch round boundary)
#
# Reminds the dispatcher to verify checklist discipline: every ticked row has an
# artifact link, no out-of-scope edits, stale markers swept. Canonical guidance
# lives under docs/ai-developer/ (no user-specific memory paths are referenced).
#
# Noise control: only fires on checklist-file edits and TaskStop. The broad
# TaskCreate/TaskUpdate/TodoWrite triggers were dropped to avoid a reminder on
# every task-list mutation.

INPUT="$(cat 2>/dev/null || true)"

# Parse tool name + relevant arg using Python (no jq on this Windows shell).
TOOL=$(printf '%s' "$INPUT" | python -c "import sys,json
try:
    d=json.load(sys.stdin)
    print(d.get('tool_name', ''))
except Exception:
    print('')" 2>/dev/null)

FILE_PATH=$(printf '%s' "$INPUT" | python -c "import sys,json
try:
    d=json.load(sys.stdin)
    ti=d.get('tool_input',{})
    print(ti.get('file_path','') or ti.get('path',''))
except Exception:
    print('')" 2>/dev/null)

should_fire=false
case "$TOOL" in
  Edit|Write|MultiEdit|NotebookEdit)
    case "$FILE_PATH" in
      *adr-*-checklist.md*) should_fire=true ;;
    esac
    ;;
  TaskStop)
    should_fire=true
    ;;
esac

if [ "$should_fire" != "true" ]; then
  exit 0
fi

# Derive cascade name from the file path when we have one (e.g. adr-040,
# adr-035-036). Falls back to "the current cascade" when fired by TaskStop.
CASCADE=$(printf '%s' "$FILE_PATH" | python -c "
import sys, re
p = sys.stdin.read().strip()
m = re.search(r'(adr-[0-9]+(?:-[0-9]+)*)-checklist\.md', p)
print(m.group(1).upper() if m else 'the current cascade')
" 2>/dev/null)

cat <<EOF
[checklist-discipline reminder — $CASCADE]
You just modified a checklist (TaskStop on the inline list, or Edit/Write on a
docs/planning/$CASCADE-checklist.md row).

Before continuing, perform these steps:

1. RE-READ the canonical dispatch + persona guidance:
   - docs/ai-developer/specific_rules/agent-dispatch.md  (dispatch protocol, drift rules, artifact-link requirement)
   - docs/ai-developer/personas/manager.md               (coordination + integration/e2e expectations)
   - docs/ai-developer/templates/                         (verbatim dispatch prompt templates)

2. VERIFY every box you ticked in the checklist doc has an inline artifact link
   ( -> <PR-or-commit-link> or -> <test name passes> ).
   A tick without artifact = drift. Log under "Drift log" and revert if needed.

3. CONFIRM no out-of-scope rows touched. Each agent edits ONLY its own rows.
   Out-of-scope edit = drift; log + escalate.

4. SWEEP stale [~] markers — bump to [x] (with artifact) or [!] (with reason).

5. INLINE LIST: confirm task statuses match reality (no task marked completed
   before its artifacts exist; no task stuck in_progress when work is done).

6. DISPATCH COMPLIANCE: if you're about to dispatch a sub-agent, compose the
   prompt from docs/ai-developer/templates/ VERBATIM, include the
   [DISPATCH-TEMPLATE-V1: <role>] marker on the first line, and tell the agent
   CI MUST be green before it reports done.

If you intentionally made a meta-change (added a new section, restructured the
checklist), acknowledge the reminder and continue.
EOF

exit 0
