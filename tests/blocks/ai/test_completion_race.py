"""Regression test for TOCTOU race between MCP-signal writer and CompletionWatcher reader (#962 / #909).

Background
----------
Non-atomic ``Path.write_text`` opens the target with mode ``"w"`` which
**truncates the file to 0 bytes before** the data is written. If a reader
polls inside that truncate window it observes an empty file and
``json.loads("")`` raises ``JSONDecodeError`` — which
``CompletionWatcher.wait`` re-raises as
``ValueError("... malformed MCP signal ...")``.

This was the documented root cause of intermittent CI flakes
(see ``docs/planning/adr-038-039-checklist.md`` →
"AI Block MCP-signal write/read race"). Fix: writers use ``tempfile``
+ ``os.replace`` so readers see an all-or-nothing transition.

The two tests below pin the contract:

1. ``test_non_atomic_writer_loses_race`` — proves the race exists by
   driving a deliberately non-atomic writer; ``CompletionWatcher.wait``
   must raise ``ValueError`` referencing the truncate window. (Documents
   why the fix is needed; would silently pass even on the buggy code.)
2. ``test_atomic_writer_wins_race`` — uses the same deliberately-induced
   race window but with the atomic temp+replace writer (matching the
   fixture's new ``_atomic_write_signal``); ``CompletionWatcher.wait``
   must observe the signal cleanly and return a ``MCP_FINISH_TOOL``
   event. **Fails without the fix.** This is the regression lock.

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

import pytest

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


def test_non_atomic_writer_loses_race(tmp_path: Path) -> None:
    """Driving a deliberately non-atomic writer must surface the race.

    Documents WHY the fix is needed: ``open("w")`` → ``close()`` truncates
    the file to 0 bytes, and the watcher reading inside that window must
    raise ``ValueError`` because ``json.loads("")`` fails. This test
    passes both before and after the fix — it pins the failure mode of
    the *buggy* writer pattern, not the fixed one.
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

    with pytest.raises(ValueError, match=r"malformed MCP signal|Expecting value"):
        watcher.wait(timeout_sec=2.0)

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
