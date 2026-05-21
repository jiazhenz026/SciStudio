"""Skeleton tests for engine.pty_control IPC helpers (ADR-035 §3.10)."""

from __future__ import annotations

import pytest

from scistudio.engine.pty_control import (
    PtyTabSpec,
    notify_block_pty_event,
)


# Dataclass shape — passes today.
def test_pty_tab_spec_has_expected_fields() -> None:
    """PtyTabSpec exposes the contract fields per ADR-035 §3.10."""
    fields = PtyTabSpec.__dataclass_fields__
    # ``run_dir_path`` was added by the audit P1-E fix so user-mark-done /
    # user-cancel WS frames can be translated into ``signals/mark_done.json``
    # writes under the right run dir.
    assert set(fields) == {
        "title",
        "spawn_argv",
        "cwd",
        "initial_stdin",
        "block_run_id",
        "permission_mode",
        "run_dir_path",
    }


# Behavioral tests — xfail until I35b implements.


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_request_pty_tab_happy_path_returns_tab_id() -> None:
    """ADR-035 §3.10: worker IPC returns engine-assigned tab_id.

    Test plan:
        1. Mock the worker's IPC handle to reply with
           ``{"tab_id": "abc123", "error": None}``.
        2. Call request_pty_tab(spec).
        3. Assert returns "abc123" and the IPC message shape was
           ``{"type": "request_pty_tab", "spec": <spec dict>}``.
    """
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_request_pty_tab_engine_error_raises() -> None:
    """Engine reply with non-None error → RuntimeError(error)."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_request_pty_tab_timeout() -> None:
    """Engine never replies within deadline → TimeoutError."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_request_pty_tab_max_ptys_raises() -> None:
    """ADR-034 §8 cap exceeded → RuntimeError with explanatory message."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_notify_completed_sends_correct_ipc_message() -> None:
    """notify_block_pty_event(event="completed") emits the right IPC msg."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_notify_cancelled_sends_correct_ipc_message() -> None:
    """notify_block_pty_event(event="cancelled_by_user_close") emits msg."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_notify_error_includes_detail() -> None:
    """notify_block_pty_event(event="error", detail={...}) propagates detail."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_notify_swallows_ipc_failure() -> None:
    """IPC failure during notify → log warning, do not raise."""
    raise NotImplementedError("skeleton")


def test_notify_unknown_event_raises_value_error() -> None:
    """Type checker catches this; runtime defense raises ValueError.

    Implementation (I35b, PR for #846) defends early. Skeleton imported
    cleanly; the impl now raises ValueError for unknown event literals.
    """
    with pytest.raises(ValueError, match="unknown event"):
        notify_block_pty_event("rid", "bogus_event")  # type: ignore[arg-type]
