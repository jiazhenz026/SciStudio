#!/usr/bin/env bash
# Scaffold commit-msg hook for provenance trailers.
set -eu

msg_file="${1:-}"

# TODO(#1113): Replace warn-only scaffold with deterministic trailer validation
# after ADR-042/043 commit tooling is finalized. Out of scope per ADR-043 §5 /
# ADR-044 §11. Followup: #1113.

if [ -z "$msg_file" ] || [ ! -f "$msg_file" ]; then
  echo "trailer-validation: no commit message file supplied; scaffold allows."
  exit 0
fi

if ! grep -qE '^(Signed-off-by|Assisted-by|ADR|Fixes):' "$msg_file"; then
  echo "trailer-validation: reminder: add required SciEasy provenance trailers."
fi

exit 0
