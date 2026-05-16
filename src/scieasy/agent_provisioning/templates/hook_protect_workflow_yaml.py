#!/usr/bin/env python
"""hook_protect_workflow_yaml.py — PreToolUse / Edit|Write (ADR-040 §3.6).

Blocks direct ``Edit`` / ``Write`` tool calls targeting
``workflows/*.yaml`` so workflow edits flow through the schema-validated
MCP path.
"""

from __future__ import annotations

import json
import re
import sys

_YAML_RE = re.compile(r"workflows/.*\.ya?ml$", re.IGNORECASE)
_MESSAGE = (
    "workflows/*.yaml is managed by mcp__scieasy__write_workflow "
    "(schema-validated) and mcp__scieasy__update_block_config "
    "(preserves comments). Direct Edit/Write bypasses validation."
)


def _read_payload() -> dict:
    try:
        raw = sys.stdin.read()
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def main() -> int:
    payload = _read_payload()
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    file_path = str(tool_input.get("file_path") or "")
    file_path_norm = file_path.replace("\\", "/")
    if _YAML_RE.search(file_path_norm):
        print(_MESSAGE, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
