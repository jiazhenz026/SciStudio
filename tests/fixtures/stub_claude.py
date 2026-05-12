"""Stand-in for the real ``claude`` CLI used by T-ECA-104 and T-ECA-109 tests.

Invoked by :class:`scieasy.ai.agent.claude_code.ClaudeCodeProvider` when
its ``binary_override`` argument points at this file. The provider
spawns ``[sys.executable, str(stub_claude.py), ...]`` so we read the
same argv pattern as the real CLI:

```
stub_claude.py --output-format stream-json --verbose \
    --append-system-prompt @<prompt> --mcp-config @<mcp> \
    [--resume <id>] [--model <m>]
```

Behaviour:

* Reads one JSON envelope from stdin (the user message). If stdin
  closes without sending a message, we still emit the canned stream so
  spawn-only tests work.
* Emits an ``init`` event (with synthetic session id, or the
  ``--resume`` value if provided) followed by three
  ``assistant_text_delta`` events, one ``tool_use``, one
  ``tool_result``, and one ``done`` event.
* Each event line is followed by a 50 ms sleep to simulate real
  streaming.
* Exit code 0 on normal flow; exit code 2 if the
  ``STUB_CLAUDE_CRASH=1`` environment variable is set (used by the
  crash test).

The stub deliberately writes the ADR-canonical ``kind`` field rather
than Claude Code's wire ``type`` — the parser handles both.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from typing import Any


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--output-format", default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--append-system-prompt", default=None)
    parser.add_argument("--mcp-config", default=None)
    parser.add_argument("--resume", default=None)
    parser.add_argument("--model", default=None)
    return parser.parse_args(argv)


def _emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()
    time.sleep(0.05)


def _emit_canned_stream(*, session_id: str) -> None:
    _emit({"kind": "init", "session_id": session_id, "model": "stub-model"})
    for delta in ("Looking ", "at your ", "project."):
        _emit({"kind": "assistant_text_delta", "delta": delta})
    _emit(
        {
            "kind": "tool_use",
            "tool_name": "Read",
            "tool_input": {"path": "."},
            "tool_use_id": "stub-tool-1",
        }
    )
    _emit(
        {
            "kind": "tool_result",
            "tool_use_id": "stub-tool-1",
            "output": "stub: listed directory\n",
            "is_error": False,
        }
    )
    _emit({"kind": "done"})


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if os.environ.get("STUB_CLAUDE_CRASH") == "1":
        sys.stderr.write("stub_claude: simulated crash\n")
        return 2

    session_id = args.resume or f"stub-session-{uuid.uuid4()}"

    # Try to read one user message; tolerate stdin EOF for spawn-only tests.
    try:
        line = sys.stdin.readline()
        # Touch the variable so static analysers don't flag it as unused.
        _ = line
    except (BrokenPipeError, OSError):
        pass

    _emit_canned_stream(session_id=session_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
