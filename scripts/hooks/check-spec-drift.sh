#!/usr/bin/env bash
# Pre-push + CI hook: run the spec_audit drift check.
#
# Wired into:
#   - .github/workflows/ci.yml (Phase 8: enabled with `if: ${{ always() }}`)
#   - .workflow/hooks/ (Phase 8: pre-push)
#
# Local escape: SCIEASY_SKIP_SPEC_AUDIT=1 (logs a reminder).

set -e

if [ "${SCIEASY_SKIP_SPEC_AUDIT:-0}" = "1" ]; then
    echo "[check-spec-drift] SKIPPED via SCIEASY_SKIP_SPEC_AUDIT=1"
    echo "[check-spec-drift] REMINDER: spec drift is uncaught locally; CI will re-check"
    exit 0
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if [ ! -f "docs/specs/INTERFACE_SPEC.md" ]; then
    echo "[check-spec-drift] docs/specs/INTERFACE_SPEC.md not present — running baseline mode"
    python scripts/spec_audit.py --baseline
    exit $?
fi

python scripts/spec_audit.py
RC=$?

if [ $RC -eq 2 ]; then
    echo ""
    echo "[check-spec-drift] FAIL — interface drift detected."
    echo "[check-spec-drift] See build/spec-audit/diff-report.md for details."
    echo "[check-spec-drift] Fix by amending docs/specs/INTERFACE_SPEC.md or the code"
    echo "[check-spec-drift] (per the authority hierarchy in INTERFACE_SPEC.md preamble)."
elif [ $RC -eq 1 ]; then
    echo "[check-spec-drift] OK with warnings — see build/spec-audit/diff-report.md"
fi

exit $RC
