"""Tests for CompletionWatcher (ADR-035 §3.5) — Phase 2A implementation."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from scistudio.blocks.ai.completion import (
    CompletionEvent,
    CompletionSource,
    CompletionWatcher,
    WatcherCancelledError,
)
from scistudio.blocks.ai.run_dir import RunDir

# ---------------------------------------------------------------------------
# Smoke tests on enum / dataclass shapes
# ---------------------------------------------------------------------------


def test_completion_source_has_three_values() -> None:
    values = {s.value for s in CompletionSource}
    assert values == {"mcp_finish_tool", "file_watcher", "user_mark_done"}


def test_completion_event_dataclass_shape() -> None:
    fields = CompletionEvent.__dataclass_fields__
    assert set(fields) == {"source", "outputs", "detail"}


def test_completion_watcher_class_imports() -> None:
    assert CompletionWatcher is not None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_watcher(
    tmp_path: Path,
    output_specs: dict[str, dict[str, object]],
    poll_interval: float = 0.02,
    stability_period: float = 0.1,
) -> tuple[RunDir, CompletionWatcher]:
    rd = RunDir(tmp_path, "test-run")
    rd.create()
    watcher = CompletionWatcher(
        run_dir=rd,
        output_specs=output_specs,
        project_dir=tmp_path,
        poll_interval=poll_interval,
        stability_period=stability_period,
    )
    return rd, watcher


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


def test_init_resolves_relative_paths_against_project_dir(tmp_path: Path) -> None:
    _rd, watcher = _make_watcher(tmp_path, {"out": {"expected_path": "./results/out.csv"}})
    assert watcher._resolved["out"] == (tmp_path / "results" / "out.csv").resolve()


def test_init_handles_absolute_expected_paths(tmp_path: Path) -> None:
    abs_path = tmp_path / "absolute" / "out.csv"
    _rd, watcher = _make_watcher(tmp_path, {"out": {"expected_path": str(abs_path)}})
    assert watcher._resolved["out"] == abs_path


# ---------------------------------------------------------------------------
# wait() — happy paths
# ---------------------------------------------------------------------------


def test_wait_mcp_signal_returns_first(tmp_path: Path) -> None:
    rd, watcher = _make_watcher(tmp_path, {"out": {"expected_path": "./out.csv"}})
    payload_path = tmp_path / "out.csv"
    rd.mcp_signal_path().parent.mkdir(parents=True, exist_ok=True)
    rd.mcp_signal_path().write_text(json.dumps({"outputs": {"out": str(payload_path)}}), encoding="utf-8")
    event = watcher.wait(timeout_sec=2.0)
    assert event.source is CompletionSource.MCP_FINISH_TOOL
    assert event.outputs["out"] == payload_path


def test_wait_file_watcher_returns_when_all_paths_stable(tmp_path: Path) -> None:
    _rd, watcher = _make_watcher(
        tmp_path,
        {"out": {"expected_path": "./out.csv"}},
        stability_period=0.2,
    )
    expected = tmp_path / "out.csv"

    def writer() -> None:
        time.sleep(0.05)
        expected.write_text("done", encoding="utf-8")

    threading.Thread(target=writer, daemon=True).start()
    event = watcher.wait(timeout_sec=3.0)
    assert event.source is CompletionSource.FILE_WATCHER
    assert event.outputs["out"] == expected.resolve()


def test_wait_user_mark_done_returns(tmp_path: Path) -> None:
    rd, watcher = _make_watcher(tmp_path, {"out": {"expected_path": "./out.csv"}})
    # No MCP signal, no output file. Mark-done fires.
    rd.mark_done_signal_path().parent.mkdir(parents=True, exist_ok=True)
    rd.mark_done_signal_path().write_text(json.dumps({"timestamp": "now"}), encoding="utf-8")
    event = watcher.wait(timeout_sec=2.0)
    assert event.source is CompletionSource.USER_MARK_DONE
    assert event.detail == {"timestamp": "now"}


def test_wait_priority_mcp_beats_file_watcher_on_same_tick(tmp_path: Path) -> None:
    rd, watcher = _make_watcher(
        tmp_path,
        {"out": {"expected_path": "./out.csv"}},
        stability_period=0.0,  # file becomes stable immediately
    )
    # Pre-create both signals before the first poll.
    expected = tmp_path / "out.csv"
    expected.write_text("file content", encoding="utf-8")
    rd.mcp_signal_path().parent.mkdir(parents=True, exist_ok=True)
    rd.mcp_signal_path().write_text(json.dumps({"outputs": {"out": str(expected)}}), encoding="utf-8")
    event = watcher.wait(timeout_sec=2.0)
    assert event.source is CompletionSource.MCP_FINISH_TOOL


# ---------------------------------------------------------------------------
# wait() — error / edge paths
# ---------------------------------------------------------------------------


def test_wait_timeout_raises_timeout_error(tmp_path: Path) -> None:
    _rd, watcher = _make_watcher(tmp_path, {"out": {"expected_path": "./never.csv"}})
    with pytest.raises(TimeoutError, match="no signal"):
        watcher.wait(timeout_sec=0.2)


def test_wait_malformed_mcp_signal_raises_value_error(tmp_path: Path) -> None:
    rd, watcher = _make_watcher(tmp_path, {"out": {"expected_path": "./out.csv"}})
    rd.mcp_signal_path().parent.mkdir(parents=True, exist_ok=True)
    rd.mcp_signal_path().write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed MCP signal"):
        watcher.wait(timeout_sec=2.0)


def test_wait_empty_mcp_signal_is_retried_not_raised(tmp_path: Path) -> None:
    """Issue #902: empty MCP signal file is mid-write, not malformed.

    A signal file that has been created but whose content has not yet
    been flushed reads as ``""``. ``json.loads("")`` would raise
    ``JSONDecodeError`` and historically surfaced as a spurious
    ``ValueError("malformed MCP signal")`` (the documented CI flake on
    ``test_ai_block_skeleton.py``). With Option B production hardening
    the watcher must treat empty / whitespace as "file mid-write" and
    keep polling. If the writer never catches up the deadline still
    elapses, surfacing :class:`TimeoutError` rather than the misleading
    ValueError.
    """
    rd, watcher = _make_watcher(
        tmp_path,
        {},
        poll_interval=0.02,
    )
    rd.mcp_signal_path().parent.mkdir(parents=True, exist_ok=True)
    # Empty file: simulates the truncate-window read in #902.
    rd.mcp_signal_path().write_text("", encoding="utf-8")
    with pytest.raises(TimeoutError, match="no signal"):
        watcher.wait(timeout_sec=0.2)


def test_wait_whitespace_only_mcp_signal_is_retried_not_raised(tmp_path: Path) -> None:
    """Issue #902: whitespace-only content is treated as mid-write too.

    Mirrors :func:`test_wait_empty_mcp_signal_is_retried_not_raised` for
    a file containing only whitespace (``"\\n"``, ``"  "``, etc.).
    """
    rd, watcher = _make_watcher(
        tmp_path,
        {},
        poll_interval=0.02,
    )
    rd.mcp_signal_path().parent.mkdir(parents=True, exist_ok=True)
    rd.mcp_signal_path().write_text("   \n\t  ", encoding="utf-8")
    with pytest.raises(TimeoutError, match="no signal"):
        watcher.wait(timeout_sec=0.2)


def test_wait_empty_mcp_signal_eventually_becomes_valid(tmp_path: Path) -> None:
    """Issue #902: empty signal -> later filled with JSON -> watcher succeeds.

    Drives the end-to-end Option B contract: a non-atomic writer that
    truncates the file (size = 0) and only later writes the JSON must
    not crash the watcher. Once the JSON lands the watcher returns the
    :class:`CompletionEvent` cleanly.
    """
    rd, watcher = _make_watcher(
        tmp_path,
        {},
        poll_interval=0.02,
    )
    signal_path = rd.mcp_signal_path()
    signal_path.parent.mkdir(parents=True, exist_ok=True)
    signal_path.write_text("", encoding="utf-8")

    def delayed_writer() -> None:
        # Long enough that the watcher polls the empty file at least once.
        time.sleep(0.1)
        signal_path.write_text(json.dumps({"outputs": {}}), encoding="utf-8")

    threading.Thread(target=delayed_writer, daemon=True).start()
    event = watcher.wait(timeout_sec=3.0)
    assert event.source is CompletionSource.MCP_FINISH_TOOL
    assert event.detail["raw_payload"] == {"outputs": {}}


def test_wait_extra_output_in_mcp_signal_logs_and_ignores(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    rd, watcher = _make_watcher(tmp_path, {"out": {"expected_path": "./out.csv"}})
    rd.mcp_signal_path().parent.mkdir(parents=True, exist_ok=True)
    rd.mcp_signal_path().write_text(
        json.dumps({"outputs": {"out": "./out.csv", "ghost": "./ghost.csv"}}),
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        event = watcher.wait(timeout_sec=2.0)
    assert "ghost" not in event.outputs
    assert any("undeclared port" in r.message for r in caplog.records)


def test_wait_empty_output_specs_falls_through_to_mark_done(tmp_path: Path) -> None:
    """Degenerate case: no declared outputs → file_watcher trivially can't fire
    (we have no paths to watch), so wait must rely on mcp/mark-done signals.
    """
    rd, watcher = _make_watcher(tmp_path, {})
    rd.mark_done_signal_path().parent.mkdir(parents=True, exist_ok=True)
    rd.mark_done_signal_path().write_text("{}", encoding="utf-8")
    event = watcher.wait(timeout_sec=2.0)
    assert event.source is CompletionSource.USER_MARK_DONE


def test_cancel_breaks_wait(tmp_path: Path) -> None:
    _rd, watcher = _make_watcher(tmp_path, {"out": {"expected_path": "./out.csv"}})

    def canceller() -> None:
        time.sleep(0.05)
        watcher.cancel()

    threading.Thread(target=canceller, daemon=True).start()
    with pytest.raises(WatcherCancelledError):
        watcher.wait(timeout_sec=5.0)


def test_wait_file_watcher_requires_size_stability(tmp_path: Path) -> None:
    """A file that keeps growing is NOT considered done."""
    _rd, watcher = _make_watcher(
        tmp_path,
        {"out": {"expected_path": "./out.csv"}},
        stability_period=0.3,
    )
    expected = tmp_path / "out.csv"

    def grower() -> None:
        for i in range(10):
            with expected.open("a", encoding="utf-8") as fh:
                fh.write(f"line {i}\n")
            time.sleep(0.05)

    threading.Thread(target=grower, daemon=True).start()
    # 0.5s wait: we expect TimeoutError because the file is changing
    # the whole time.
    with pytest.raises(TimeoutError):
        watcher.wait(timeout_sec=0.4)
