"""Example PreToolUse hook script for the T-ECA-105 spike.

Invoked by Claude Code as the ``PreToolUse`` hook. Reads CC's hook input
JSON from stdin, logs it to ``$SPIKE_HOOK_LOG`` (one line per invocation),
optionally sleeps for ``$SPIKE_HOOK_SLEEP`` seconds, then exits 0
(approve) or 2 (deny) based on ``$SPIKE_HOOK_DECISION``.

This mirrors the shape that ``scieasy hook-bridge`` will take in
T-ECA-110, but with simple env-var-driven behaviour so spike scenarios
can be parameterised externally.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    payload_text = sys.stdin.read()
    try:
        payload = json.loads(payload_text) if payload_text else {}
    except json.JSONDecodeError:
        payload = {"_raw": payload_text}

    log_path = os.environ.get("SPIKE_HOOK_LOG")
    if log_path:
        record = {
            "received_at": time.time(),
            "decision_env": os.environ.get("SPIKE_HOOK_DECISION", "approve"),
            "sleep_seconds": os.environ.get("SPIKE_HOOK_SLEEP", "0"),
            "payload": payload,
        }
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    try:
        sleep_s = float(os.environ.get("SPIKE_HOOK_SLEEP", "0"))
    except ValueError:
        sleep_s = 0.0
    if sleep_s > 0:
        time.sleep(sleep_s)

    decision = os.environ.get("SPIKE_HOOK_DECISION", "approve").lower()
    if decision == "deny":
        # Print to stderr so CC surfaces the reason to the user.
        sys.stderr.write("spike hook: denied by SPIKE_HOOK_DECISION=deny\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
