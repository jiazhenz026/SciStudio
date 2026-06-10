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


def test_notify_unknown_event_raises_value_error() -> None:
    """Type checker catches this; runtime defense raises ValueError.

    Implementation (I35b, PR for #846) defends early. Skeleton imported
    cleanly; the impl now raises ValueError for unknown event literals.
    """
    with pytest.raises(ValueError, match="unknown event"):
        notify_block_pty_event("rid", "bogus_event")  # type: ignore[arg-type]
