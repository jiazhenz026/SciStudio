#!/usr/bin/env bash
# Scaffold InstructionsLoaded hook for rule-load audits.
set -eu

trace_dir="docs/audit/instructions-loaded-trace"
session="${SCIEASY_AGENT_SESSION_ID:-manual}"

# TODO(#1113): Enable append-only audit logging only after ADR-043 §5 runtime
# hook activation and retention policy are finalized. Out of scope per ADR-043
# §5 / ADR-044 §11. Followup: #1113.

if [ "${SCIEASY_ENABLE_INSTRUCTIONS_AUDIT:-0}" = "1" ]; then
  mkdir -p "$trace_dir"
  printf '{"session":"%s","event":"InstructionsLoaded","status":"scaffold"}\n' "$session" >> "$trace_dir/$session.jsonl"
fi

echo '{"hookSpecificOutput":{"hookEventName":"InstructionsLoaded","permissionDecision":"allow"}}'
