"""Stand-in for the real ``codex`` CLI used by provider tests.

The stub mirrors the observed Codex non-interactive shape:

```
codex exec --json ... -
codex exec --json ... resume <thread_id> -
```

It emits Codex-style JSONL frames that ``CodexSession`` normalises into
SciEasy's canonical event taxonomy.
"""

from __future__ import annotations

import contextlib
import json
import os
import queue as _queue
import sys
import threading
import time
import uuid
from typing import Any


_STDIN_READ_TIMEOUT_SECONDS = 1.0


def _try_read_stdin(timeout: float) -> str:
    q: _queue.Queue[str] = _queue.Queue(maxsize=1)

    def _reader() -> None:
        try:
            text = sys.stdin.read()
        except (BrokenPipeError, OSError, ValueError):
            text = ""
        with contextlib.suppress(_queue.Full):
            q.put_nowait(text)

    threading.Thread(target=_reader, daemon=True).start()
    try:
        return q.get(timeout=timeout)
    except _queue.Empty:
        return ""


def _emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()
    time.sleep(0.02)


def _session_id_from_args(argv: list[str]) -> str:
    if argv and argv[0] == "exec" and "resume" in argv:
        resume_index = argv.index("resume")
        # The real provider passes exec-level options before "resume",
        # then the id immediately after it.
        for value in argv[resume_index + 1 :]:
            if not value.startswith("-"):
                return value
    return f"stub-codex-thread-{uuid.uuid4()}"


def _emit_stream(session_id: str) -> None:
    _emit({"type": "thread.started", "thread_id": session_id})
    _emit({"type": "turn.started"})
    _emit({"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "Reading the SciEasy project."}})
    _emit(
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "function_call",
                "name": "Read",
                "arguments": {"path": "."},
                "call_id": "stub-codex-tool-1",
            },
        }
    )
    _emit(
        {
            "type": "item.completed",
            "item": {
                "id": "item_2",
                "type": "function_call_output",
                "call_id": "stub-codex-tool-1",
                "output": "stub-codex: listed directory\n",
            },
        }
    )
    _emit({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}})


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if os.environ.get("STUB_CODEX_CRASH") == "1":
        sys.stderr.write("stub_codex: simulated crash\n")
        return 2
    if not args or args[0] != "exec":
        sys.stderr.write("stub_codex: expected exec command\n")
        return 2

    session_id = _session_id_from_args(args)
    _ = _try_read_stdin(_STDIN_READ_TIMEOUT_SECONDS)
    _emit_stream(session_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
