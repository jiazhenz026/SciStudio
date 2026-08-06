#!/usr/bin/env python
"""hook_remind_poll_status.py — PostToolUse / run_workflow (ADR-040 §3.6).

After ``mcp__scistudio__run_workflow`` returns, inject a reminder telling
the agent to poll ``get_run_status`` until the run reaches a terminal
state. PostToolUse hooks cannot block the call — they can only surface
stderr feedback for the agent's next turn.
"""

from __future__ import annotations

import json
import sys


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
    run_id_hint = ""
    response = payload.get("tool_response") or payload.get("response") or {}
    if isinstance(response, dict):
        rid = response.get("run_id") or response.get("runId")
        if rid:
            run_id_hint = f" (run_id={rid})"
    print(
        "run_workflow has been kicked off"
        + run_id_hint
        + ". Poll mcp__scistudio__get_run_status periodically until status "
        "is 'completed', 'failed', or 'cancelled' before proceeding.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
