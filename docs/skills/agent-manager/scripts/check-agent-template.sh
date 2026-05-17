#!/usr/bin/env bash
set -euo pipefail

target="${1:-docs/skills/agent-manager/templates/00-common-boilerplate.md}"
if [[ ! -f "$target" ]]; then
  echo "missing template: $target" >&2
  exit 1
fi

echo "template present: $target"
