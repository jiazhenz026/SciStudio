#!/usr/bin/env bash
# Scaffold Stop hook for Codex review reconcile rounds.
set -eu

rounds="${SCIEASY_CODEX_RECONCILE_ROUNDS:-0}"

# TODO(#1113): Connect this to real review-reconcile state after ADR-043 §5
# hook activation and review workflow state exist. Out of scope per ADR-043 §5 /
# ADR-044 §11. Followup: #1113.

case "$rounds" in
  ''|*[!0-9]*) rounds=0 ;;
esac

if [ "$rounds" -gt 1 ]; then
  echo "codex-review-reconcile-cap: warning: more than one reconcile round."
fi

exit 0
