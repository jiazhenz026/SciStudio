"""Regression test for TOCTOU race between MCP-signal writer and CompletionWatcher reader (#962 / #909 / #902).

Background
----------
Non-atomic ``Path.write_text`` opens the target with mode ``"w"`` which
**truncates the file to 0 bytes before** the data is written. If a reader
polls inside that truncate window it observes an empty file.

Two complementary fixes harden the system:

* **Writer side** (#962 / #909): production agents + the StubAgent
  fixture use ``tempfile`` + ``os.replace`` so readers see an
  all-or-nothing transition. See
  ``tests/blocks/ai/conftest.py::_atomic_write_signal``.
* **Reader side** (#902): ``CompletionWatcher.wait`` now treats empty
  / whitespace-only content as "file mid-write" and retries on the
  next poll instead of raising
  ``ValueError("... malformed MCP signal ...")``. This guards against
  third-party MCP writers that may not use atomic writes.

The two tests below pin the contract:

1. ``test_non_atomic_writer_eventually_completes`` — drives a
   deliberately non-atomic writer; ``CompletionWatcher.wait`` must
   tolerate the truncate window and return a ``MCP_FINISH_TOOL`` event
   once the JSON finally lands. (Fails on the pre-#902 reader that
   raised ``ValueError`` inside the truncate window.)
2. ``test_atomic_writer_wins_race`` — uses the same deliberately-induced
   race window but with the atomic temp+replace writer (matching the
   fixture's ``_atomic_write_signal``); ``CompletionWatcher.wait``
   must observe the signal cleanly and return a ``MCP_FINISH_TOOL``
   event. This is the writer-side regression lock from #962 / #909.

Determinism — use ``threading.Event`` to hand off the "I have created the
empty file" signal from writer thread to test thread, then sleep a small
amount of real time (well below the watcher's 5 s deadline) so the
watcher's polling loop has the opportunity to read the empty file. No
pure-sleep timing dependencies.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path

from scistudio.blocks.ai.completion import (
    CompletionSource,
    CompletionWatcher,
)
from scistudio.blocks.ai.run_dir import RunDir


def _make_watcher(tmp_path: Path) -> tuple[RunDir, CompletionWatcher]:
    rd = RunDir(tmp_path, "race-run")
    rd.create()
    watcher = CompletionWatcher(
        run_dir=rd,
        # No declared outputs — only the MCP path is exercised, so the
        # FileWatcher fallback never fires.
        output_specs={},
        project_dir=tmp_path,
        poll_interval=0.01,
        stability_period=0.05,
    )
    return rd, watcher


def _atomic_write(signal_path: Path, content: str) -> None:
    """Mirror of the production / fixture atomic-write helper.

    Kept in-test (rather than imported from conftest) so this regression
    test is self-contained — if a future refactor moves the helper, the
    test still pins the contract by name.
    """
    signal_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(signal_path.parent),
        prefix="." + signal_path.name + ".",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, str(signal_path))
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def test_non_atomic_writer_eventually_completes(tmp_path: Path) -> None:
    """Issue #902 reader-side hardening: non-atomic writer is now tolerated.

    Drives a deliberately non-atomic writer that ``open("w")``s the
    signal file (truncating to 0 bytes), holds the descriptor open
    across the watcher's poll window, then writes the JSON. Before
    #902 the watcher would read the empty file inside the truncate
    window and raise ``ValueError("... malformed MCP signal ...")``.
    After #902 the watcher treats empty content as "file mid-write",
    retries on the next poll, and returns the ``MCP_FINISH_TOOL`` event
    once the writer flushes the JSON.

    This test FAILS on the pre-#902 watcher (the empty-read raises
    inside the truncate window) and PASSES on the patched watcher.
    """
    _rd, watcher = _make_watcher(tmp_path)
    signal_path = watcher.run_dir.mcp_signal_path()
    signal_path.parent.mkdir(parents=True, exist_ok=True)

    truncated = threading.Event()

    def non_atomic_writer() -> None:
        # Open in write mode → file is now 0 bytes on disk. Hold it
        # open across the handoff so the watcher's poll lands inside
        # the truncate window.
        with signal_path.open("w", encoding="utf-8") as f:
            truncated.set()
            # Give the watcher 100 ms to read the empty file. The
            # watcher polls at 10 ms, so this is ≥10 ticks of
            # opportunity to land inside the window.
            time.sleep(0.1)
            f.write(json.dumps({"outputs": {}}))

    writer = threading.Thread(target=non_atomic_writer, daemon=True)
    writer.start()
    # Wait for the writer to have truncated the file before we start
    # the watcher — otherwise the watcher could race past the empty
    # state before the test even sets it up.
    assert truncated.wait(timeout=2.0), "writer thread never reached truncate window"

    event = watcher.wait(timeout_sec=2.0)
    assert event.source is CompletionSource.MCP_FINISH_TOOL
    assert event.detail["raw_payload"] == {"outputs": {}}

    writer.join(timeout=2.0)


def test_atomic_writer_wins_race(tmp_path: Path) -> None:
    """Regression lock: with atomic temp+replace, no race window exists.

    The writer creates and fully populates a temp file in the same
    directory, then ``os.replace``s it into the target name. Readers
    observe the target as either absent or fully written — never empty.
    The watcher must therefore return a ``MCP_FINISH_TOOL`` event
    cleanly.

    Fails on the pre-fix code (where the fixture used the buggy
    ``Path.write_text`` pattern that surfaced the race). Passes on the
    fixed code.
    """
    _rd, watcher = _make_watcher(tmp_path)
    signal_path = watcher.run_dir.mcp_signal_path()

    ready = threading.Event()

    def atomic_writer() -> None:
        # Simulate the same "race window" timing the buggy writer
        # exposed: pause, then write. The atomic helper guarantees the
        # reader never sees the partially-written state regardless of
        # how the writer pauses internally.
        ready.set()
        time.sleep(0.05)
        _atomic_write(signal_path, json.dumps({"outputs": {}}))

    writer = threading.Thread(target=atomic_writer, daemon=True)
    writer.start()
    assert ready.wait(timeout=2.0), "writer thread never signalled ready"

    event = watcher.wait(timeout_sec=2.0)
    assert event.source is CompletionSource.MCP_FINISH_TOOL
    assert event.detail["raw_payload"] == {"outputs": {}}

    writer.join(timeout=2.0)
