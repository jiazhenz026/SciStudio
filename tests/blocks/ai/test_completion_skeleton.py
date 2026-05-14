"""Skeleton tests for CompletionWatcher (ADR-035 §3.5)."""

from __future__ import annotations

import pytest

from scieasy.blocks.ai.completion import (
    CompletionEvent,
    CompletionSource,
    CompletionWatcher,
)


# Smoke test on enum / dataclass shapes (no NotImplementedError dependency).
def test_completion_source_has_three_values() -> None:
    """ADR-035 §3.5: exactly three completion paths."""
    values = {s.value for s in CompletionSource}
    assert values == {"mcp_finish_tool", "file_watcher", "user_mark_done"}


def test_completion_event_dataclass_shape() -> None:
    """CompletionEvent has source, outputs, detail."""
    fields = CompletionEvent.__dataclass_fields__
    assert set(fields) == {"source", "outputs", "detail"}


# Behavioral tests — xfail until implementation phase.


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_init_resolves_relative_paths_against_project_dir() -> None:
    """Watcher resolves expected_path against project_dir per ADR-035 §3.3."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_init_handles_absolute_expected_paths() -> None:
    """Absolute expected_path passed through unchanged."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_wait_mcp_signal_returns_first() -> None:
    """ADR-035 §3.5 path (a) priority — MCP signal wins."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_wait_file_watcher_returns_when_all_paths_stable() -> None:
    """ADR-035 §3.5 path (b) — all expected_path size-stable for 2s."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_wait_user_mark_done_returns() -> None:
    """ADR-035 §3.5 path (c) — mark_done.json exists."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_wait_priority_mcp_beats_file_watcher_on_same_tick() -> None:
    """Both signals satisfied on same poll → MCP source wins."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_wait_timeout_raises_timeout_error() -> None:
    """timeout_sec exceeded → TimeoutError."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_wait_malformed_mcp_signal_raises_value_error() -> None:
    """Bad JSON in finish_ai_block.json → ValueError."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_wait_extra_output_in_mcp_signal_logs_and_ignores() -> None:
    """MCP signal references undeclared port → log warning, ignore."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_cancel_breaks_wait() -> None:
    """ADR-035 §3.9: cancel() unblocks wait() with CancelledError."""
    raise NotImplementedError("skeleton")


# Smoke import test — passes today.
def test_completion_watcher_class_imports() -> None:
    assert CompletionWatcher is not None
