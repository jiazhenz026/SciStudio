#!/usr/bin/env bash
# PostToolUse hook — fires after:
#  (a) Edit/Write/MultiEdit on docs/planning/adr-035-036-checklist.md
#  (b) any TaskCreate / TaskUpdate / TaskStop call on the inline TodoWrite list
#
# Reminds the dispatcher to re-read memory, verify the Drift log, and
# confirm every ticked row has an artifact link.

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
      *adr-035-036-checklist.md*) should_fire=true ;;
    esac
    ;;
  TaskCreate|TaskUpdate|TaskStop|TodoWrite)
    should_fire=true
    ;;
esac

if [ "$should_fire" != "true" ]; then
  exit 0
fi

cat <<'EOF'
[checklist-discipline reminder]
You just modified a checklist (TaskCreate/TaskUpdate/TaskStop on the inline list, or Edit/Write on docs/planning/adr-035-036-checklist.md).

Before continuing, perform these steps:

1. RE-READ relevant memory entries:
   - feedback_multi_agent_checklist_protocol.md  (drift rules, artifact-link requirement)
   - project_adr035_036_overnight_dispatch.md    (current dispatch state, branches, scope)
   - feedback_ticket_dispatch_playbook.md        (dispatch prompt template)
   - feedback_audit_p1_override.md               (override deferred Codex P1)
   - feedback_mandatory_chrome_smoke_test.md     (UI-touching audit must do live Chrome)
   - feedback_agent_discipline_and_pytest_timeout.md  (--timeout=60 + scope discipline)

2. VERIFY every box you ticked in the checklist doc has an inline artifact link
   ( -> <PR-or-commit-link> or -> <test name passes> ).
   A tick without artifact = drift. Log under "Drift log" and revert if needed.

3. CONFIRM no out-of-scope rows touched. Each agent edits ONLY its own rows.
   Out-of-scope edit = drift; log + escalate.

4. SWEEP stale [~] markers — bump to [x] (with artifact) or [!] (with reason).

5. INLINE LIST: confirm task #1..#8 statuses match reality (no task marked
   completed before its artifacts exist; no task stuck in_progress when work
   is actually done).

If you intentionally made a meta-change (added a new section, restructured
the checklist), acknowledge the reminder and continue.
EOF

exit 0
