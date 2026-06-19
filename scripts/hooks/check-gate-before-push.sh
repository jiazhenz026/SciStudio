#!/bin/bash
# Claude/Codex PreToolUse hook: allow git push without running the gate evaluator.
#
# PR creation still runs the gate through check-gate-before-pr.sh and
# scripts/scistudio_pr_create.py, and CI remains authoritative. This hook stays
# installed as a cheap compatibility shim so existing hook configs do not need
# to be rewritten just to stop duplicate pre-push validation.

set -euo pipefail

echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
