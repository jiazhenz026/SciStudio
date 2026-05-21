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
