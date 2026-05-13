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

* Reads JSON envelopes from stdin in a loop. For each user envelope
  read, emits one canned stream. If stdin closes without sending any
  message, we still emit the canned stream once so spawn-only tests
  work.
* Issue #804: multi-turn support — emits exactly one ``init`` event for
  the lifetime of the subprocess (matching the real ``claude`` CLI in
  ``--input-format stream-json`` mode where the subprocess stays alive
  across user turns). Subsequent turns emit only assistant_text_delta
  + tool_use + tool_result + done. This lets us test the
  session-persistence invariant: \"two user_messages on one WS produce
  exactly one ev-init\".
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
import contextlib
import json
import os
import queue as _queue
import sys
import threading
import time
import uuid
from typing import Any

# Wall-clock budget for reading one line from stdin before we give up and
# proceed to emit the canned stream. Windows asyncio Proactor pipes do not
# propagate EOF synchronously when the parent calls StreamWriter.close(),
# so sys.stdin.readline() can block indefinitely. The reader thread is a
# daemon, so any never-returned read is reaped on process exit.
_STDIN_READ_TIMEOUT_SECONDS = 1.0


def _try_read_one_line(timeout: float) -> str:
    """Read one line from stdin with a wall-clock timeout.

    Returns the line on success, or an empty string on timeout / EOF /
    read error. Avoids blocking forever on Windows pipes that never
    deliver EOF.
    """
    q: _queue.Queue[str] = _queue.Queue(maxsize=1)

    def _reader() -> None:
        try:
            line = sys.stdin.readline()
        except (BrokenPipeError, OSError, ValueError):
            line = ""
        with contextlib.suppress(_queue.Full):
            q.put_nowait(line)

    threading.Thread(target=_reader, daemon=True).start()
    try:
        return q.get(timeout=timeout)
    except _queue.Empty:
        return ""


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--output-format", default=None)
    parser.add_argument("--input-format", default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--append-system-prompt", default=None)
    parser.add_argument("--mcp-config", default=None)
    parser.add_argument("--resume", default=None)
    parser.add_argument("--model", default=None)
    # Issue #784: provider now passes --disallowedTools to suppress
    # AskUserQuestion (and possibly more). Accept and ignore — the stub
    # has no native-tool surface to disallow.
    parser.add_argument("--disallowedTools", default=None)
    # Issue #791: ClaudeCodeProvider appends ``--permission-mode bypassPermissions``
    # when the session is launched in BYPASS mode. The stub doesn't care
    # about the value but must accept the flag or argparse will SystemExit.
    parser.add_argument("--permission-mode", default=None)
    return parser.parse_args(argv)


def _emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()
    time.sleep(0.05)


def _emit_init(session_id: str) -> None:
    """Emit a single ``init`` event for the subprocess lifetime."""
    _emit({"kind": "init", "session_id": session_id, "model": "stub-model"})


def _emit_turn_stream() -> None:
    """Emit one turn's worth of events (no ``init`` — that's lifetime-once).

    Issue #804: split out from ``_emit_canned_stream`` so multi-turn
    invocations don't keep re-emitting ``init``. The real claude CLI
    emits ``init`` exactly once per subprocess lifetime in stream-json
    input mode; the persistence test asserts the same invariant.
    """
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


def _emit_canned_stream(*, session_id: str) -> None:
    """Backwards-compatible single-turn emit (init + one turn)."""
    _emit_init(session_id)
    _emit_turn_stream()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if os.environ.get("STUB_CLAUDE_CRASH") == "1":
        sys.stderr.write("stub_claude: simulated crash\n")
        return 2

    session_id = args.resume or f"stub-session-{uuid.uuid4()}"

    # Issue #804: multi-turn. Emit ``init`` once for the subprocess
    # lifetime; then loop on stdin and emit one turn's stream per
    # envelope. The first read uses a short timeout so spawn-only tests
    # (which never send a message) still get the canned stream and the
    # subprocess exits cleanly. Subsequent reads use the same bounded
    # timeout — if stdin is silent for that long we assume no more
    # turns are coming and exit.
    _emit_init(session_id)
    first_line = _try_read_one_line(timeout=_STDIN_READ_TIMEOUT_SECONDS)
    _emit_turn_stream()
    # If we never received a message (spawn-only test), exit now.
    if not first_line:
        return 0
    # Multi-turn loop: each additional stdin line drives one more turn.
    # Empty / EOF ends the loop.
    while True:
        line = _try_read_one_line(timeout=_STDIN_READ_TIMEOUT_SECONDS)
        if not line:
            break
        _emit_turn_stream()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
