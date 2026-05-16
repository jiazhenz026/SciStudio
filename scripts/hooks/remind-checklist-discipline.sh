#!/usr/bin/env bash
# PostToolUse hook — fires after:
#  (a) Edit/Write/MultiEdit on docs/planning/adr-*-checklist.md (any cascade)
#  (b) any TaskCreate / TaskUpdate / TaskStop call on the inline TodoWrite list
#
# Reminds the dispatcher to re-read memory, verify the Drift log, and
# confirm every ticked row has an artifact link.
#
# Pre-2026-05-16 the filter was hard-coded to adr-035-036-checklist.md;
# this missed all subsequent cascades (ADR-038/039, ADR-040, ...). Generalised
# to glob *adr-*-checklist.md* so every cascade gets the reminder.

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
  TaskCreate|TaskUpdate|TaskStop|TodoWrite)
    should_fire=true
    ;;
esac

if [ "$should_fire" != "true" ]; then
  exit 0
fi

# Derive cascade name from the file path when we have one (e.g. adr-040,
# adr-035-036). Falls back to "the current cascade" when fired by a Task tool.
CASCADE=$(printf '%s' "$FILE_PATH" | python -c "
import sys, re
p = sys.stdin.read().strip()
m = re.search(r'(adr-[0-9]+(?:-[0-9]+)*)-checklist\.md', p)
print(m.group(1).upper() if m else 'the current cascade')
" 2>/dev/null)

cat <<EOF
[checklist-discipline reminder — $CASCADE]
You just modified a checklist (TaskCreate/TaskUpdate/TaskStop on the inline list, or Edit/Write on docs/planning/$CASCADE-checklist.md).

Before continuing, perform these steps:

1. RE-READ relevant memory entries:
   - feedback_skill_rules_are_protocol_not_guidance.md (read SKILL + templates + hooks IN FULL before dispatching; do not customize)
   - feedback_multi_agent_checklist_protocol.md  (drift rules, artifact-link requirement)
   - feedback_ticket_dispatch_playbook.md        (dispatch prompt template)
   - feedback_audit_p1_override.md               (override deferred Codex P1)
   - feedback_mandatory_chrome_smoke_test.md     (UI-touching audit must do live Chrome)
   - feedback_agent_discipline_and_pytest_timeout.md  (--timeout=60 + scope discipline)
   - feedback_out_of_scope_todo.md               (CLAUDE.md §7.6 — every deferral needs TODO(#NNN))

2. VERIFY every box you ticked in the checklist doc has an inline artifact link
   ( -> <PR-or-commit-link> or -> <test name passes> ).
   A tick without artifact = drift. Log under "Drift log" and revert if needed.

3. CONFIRM no out-of-scope rows touched. Each agent edits ONLY its own rows.
   Out-of-scope edit = drift; log + escalate.

4. SWEEP stale [~] markers — bump to [x] (with artifact) or [!] (with reason).

5. INLINE LIST: confirm task statuses match reality (no task marked completed before its artifacts exist; no task stuck in_progress when work is actually done).

6. AGENT-MANAGER SKILL COMPLIANCE: if you're about to dispatch a sub-agent,
   verify the prompt is composed from \`templates/00-common-boilerplate.md\`
   + \`templates/<role>-agent.md\` VERBATIM, includes the
   \`[DISPATCH-TEMPLATE-V1: <role>]\` marker on the first line, and tells the
   agent that CI MUST be green before report-done (common-boilerplate rule #9).

If you intentionally made a meta-change (added a new section, restructured
the checklist), acknowledge the reminder and continue.
EOF

exit 0
