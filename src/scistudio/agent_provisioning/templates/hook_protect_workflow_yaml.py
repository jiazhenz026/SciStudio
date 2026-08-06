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
    "workflows/*.yaml is managed by mcp__scistudio__write_workflow "
    "(schema-validated) and mcp__scistudio__update_block_config "
    "(preserves comments). Direct Edit/Write bypasses validation."
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
