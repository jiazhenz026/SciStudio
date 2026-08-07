#!/usr/bin/env python
"""hook_mark_list_blocks_called.py — PostToolUse / list_blocks (ADR-040 §3.6).

After ``mcp__scistudio__list_blocks`` returns, write a session-keyed
marker file the companion PreToolUse hook
(``hook_enforce_list_blocks_before_block_write.py``) reads to gate
block-authoring tool calls.

Marker layout: <project>/.scistudio/.session-state/<session_id>/list_blocks_called

The ``.scistudio/`` tree is gitignored by ADR-039's default .gitignore.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


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
    session_id = str(payload.get("session_id") or "")
    if not session_id:
        # No session_id → cannot write a session-keyed marker. Exit 0 so
        # the PostToolUse hook never blocks anything; the corresponding
        # PreToolUse will just fail to find the marker (same fail-closed
        # behavior as a fresh session).
        return 0
    if re.search(r"[\\/\x00]", session_id):
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if not project_dir:
        return 0

    target_dir = Path(project_dir) / ".scistudio" / ".session-state" / session_id
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "list_blocks_called").touch()
    except OSError as exc:
        # Best-effort; do not block the tool call on filesystem errors.
        print(f"warning: could not write list_blocks marker: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
