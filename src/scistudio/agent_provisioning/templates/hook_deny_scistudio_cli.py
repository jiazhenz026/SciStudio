#!/usr/bin/env python
"""hook_deny_scistudio_cli.py — PreToolUse / Bash matcher (ADR-040 §3.6).

Blocks ``scistudio <subcommand>`` invocations via Bash to enforce
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

_SCISTUDIO_RE = re.compile(r"^\s*(?:\S*/)?scistudio(?:\s|$)")
_MESSAGE = (
    "SciStudio CLI calls bypass the GUI and lineage. Use mcp__scistudio__* "
    "tools instead: list_blocks, write_workflow, run_workflow, "
    "get_run_status."
)


def _read_payload() -> dict:
    """Read the hook payload, degrading to ``{}`` instead of ever crashing.

    #1994: this used to guard only ``OSError``. When a CLI starts a hook with
    no usable stdin, Python sets ``sys.stdin`` to ``None``, so
    ``sys.stdin.read()`` raised ``AttributeError`` — which nothing caught. The
    hook died with **exit 1** before evaluating anything, which the CLI reports
    as a failed hook and then proceeds, so the guard silently did not guard.
    It reproduced identically for all seven hooks, because they all share this
    function.

    An unreadable payload is indistinguishable from an empty one: in both cases
    the hook cannot tell what the agent is about to do. It returns ``{}`` and
    the caller allows the call, which is the behaviour an empty payload already
    had — and blocking every tool call on a stdin quirk would be far worse than
    the exposure it removes. ``BaseException`` is deliberately not caught; only
    the ways reading a missing or closed stream can fail.
    """
    stream = sys.stdin
    if stream is None:
        return {}
    try:
        raw = stream.read()
    except (OSError, ValueError, AttributeError):
        # ValueError: reading a closed file. AttributeError: a replaced stdin
        # that is not a stream at all.
        return {}
    if not isinstance(raw, str) or not raw.strip():
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
    if _SCISTUDIO_RE.search(cmd):
        print(_MESSAGE, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
