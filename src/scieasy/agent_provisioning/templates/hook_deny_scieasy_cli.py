#!/usr/bin/env python
"""hook_deny_scieasy_cli.py — PreToolUse / Bash matcher (ADR-040 §3.6).

Blocks ``scieasy <subcommand>`` invocations via Bash to enforce
MCP-only access. Closes the CLI-vs-MCP half of issue #875.

Hook contract:
  - Stdin: JSON payload with ``tool_input.command`` for Bash matchers.
  - Matcher (settings.json): ``"Bash"``.
  - Exit 2 + stderr line: blocks the tool call.
  - Exit 0: allows the tool call.
"""

from __future__ import annotations

import json
import re
import sys

_SCIEASY_RE = re.compile(r"^\s*(?:\S*/)?scieasy(?:\s|$)")
_MESSAGE = (
    "SciEasy CLI calls bypass the GUI and lineage. Use mcp__scieasy__* "
    "tools instead: list_blocks, write_workflow, run_workflow, "
    "get_run_status."
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
    cmd = ""
    tool_input = payload.get("tool_input") or {}
    if isinstance(tool_input, dict):
        cmd = str(tool_input.get("command") or "")
    if _SCIEASY_RE.search(cmd):
        print(_MESSAGE, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
