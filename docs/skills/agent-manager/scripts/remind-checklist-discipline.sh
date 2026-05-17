#!/usr/bin/env bash
set -euo pipefail

# Generic reminder hook for checklist edits across cascades.
TOOL="${1:-}"
FILE_PATH="${2:-}"

should_fire=false
case "$TOOL" in
  Edit|Write|MultiEdit|NotebookEdit)
    case "$FILE_PATH" in
      *checklist*.md*|*adr-*-checklist.md*|*docs/planning/*checklist*.md*) should_fire=true ;;
    esac
    ;;
esac

if [[ "$should_fire" == true ]]; then
  cat <<'MSG'
[agent-manager reminder]
- Edit only rows you own.
- Every checked box must append: -> <artifact link>
- Log drift in append-only drift section.
MSG
fi
