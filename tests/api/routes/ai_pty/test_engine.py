"""Behavior tests for ``ai_pty._engine`` (issue #1432).

Focused on the small surface of ``_engine`` that the larger
test_ai_pty_engine_spawn.py integration tests do not cover with a
single, easily-traceable assertion:

* Explicit-provider validation against the registry (ADR-034 FR-010,
  FR-011) — the module no longer infers a provider from argv.
* Late-bound ``MAX_ACTIVE_PTYS`` / ``_spawn`` lookup on the package
  (so the existing monkeypatch contract survives the refactor).
* ``get_run_dir_for_block_run`` / ``get_block_run_id_for_tab`` lookup
  fall-backs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.ai.agent.providers_registry import agent_keys
from scistudio.api.routes import ai_pty
from scistudio.api.routes.ai_pty import engine as engine_module


@pytest.fixture(autouse=True)
def _reset_engine_state() -> None:
    """Clear engine-side maps between tests so order doesn't bleed."""
    ai_pty._active_ptys.clear()
    ai_pty._engine_tab_to_run.clear()
    ai_pty._engine_run_to_run_dir.clear()
    yield
    ai_pty._active_ptys.clear()
    ai_pty._engine_tab_to_run.clear()
    ai_pty._engine_run_to_run_dir.clear()


def test_provider_from_argv_is_gone() -> None:
    """FR-011: no code path may infer a provider from an argv basename."""
    assert not hasattr(engine_module, "_provider_from_argv")


def test_open_engine_initiated_tab_rejects_unknown_provider(tmp_path: Path) -> None:
    """FR-010: an unknown key errors instead of defaulting to claude-code.

    The deleted ``_provider_from_argv`` returned ``claude-code`` for
    anything it did not recognise, so a typo spawned the wrong agent
    silently. The rejection enumerates the registry-derived accepted set.
    """
    with pytest.raises(RuntimeError, match="unknown provider") as excinfo:
        ai_pty.open_engine_initiated_tab(
            title="t",
            provider="claude",  # binary name, not a provider key
            cwd=str(tmp_path),
            initial_stdin="",
            block_run_id="rid-unknown",
            permission_mode="safe",
        )
    for key in agent_keys():
        assert key in str(excinfo.value)


def test_open_engine_initiated_tab_rejects_empty_provider(tmp_path: Path) -> None:
    """An absent provider on the IPC wire is an error, not a default."""
    with pytest.raises(RuntimeError, match="unknown provider"):
        ai_pty.open_engine_initiated_tab(
            title="t",
            provider="",
            cwd=str(tmp_path),
            initial_stdin="",
            block_run_id="rid-empty",
            permission_mode="safe",
        )


def test_open_engine_initiated_tab_rejects_invalid_permission_mode(tmp_path: Path) -> None:
    """``permission_mode`` is restricted to ``safe`` | ``bypass``."""
    with pytest.raises(RuntimeError, match="permission_mode must be"):
        ai_pty.open_engine_initiated_tab(
            title="t",
            provider="claude-code",
            cwd=str(tmp_path),
            initial_stdin="",
            block_run_id="rid-perm",
            permission_mode="root",  # invalid
        )


def test_open_engine_initiated_tab_rejects_relative_cwd() -> None:
    """``cwd`` must be an existing absolute directory."""
    with pytest.raises(RuntimeError, match="cwd must be an existing"):
        ai_pty.open_engine_initiated_tab(
            title="t",
            provider="claude-code",
            cwd="relative/path",  # not absolute
            initial_stdin="",
            block_run_id="rid-cwd",
            permission_mode="safe",
        )


def test_open_engine_initiated_tab_honours_monkeypatched_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``MAX_ACTIVE_PTYS = 0`` blocks any new engine-initiated tab.

    Asserts the late-bound lookup against the package namespace is
    intact — the same contract the existing
    test_ai_pty_engine_spawn.py relies on.
    """
    monkeypatch.setattr(ai_pty._state, "MAX_ACTIVE_PTYS", 0)
    with pytest.raises(RuntimeError, match="PTY cap"):
        ai_pty.open_engine_initiated_tab(
            title="t",
            provider="claude-code",
            cwd=str(tmp_path),
            initial_stdin="",
            block_run_id="rid-cap",
            permission_mode="safe",
        )


def test_get_run_dir_for_block_run_returns_none_for_unknown() -> None:
    """Unknown block_run_id resolves to ``None``."""
    assert ai_pty.get_run_dir_for_block_run("no-such-rid") is None


def test_get_block_run_id_for_tab_returns_none_for_unknown() -> None:
    """Unknown tab_id resolves to ``None``."""
    assert ai_pty.get_block_run_id_for_tab("no-such-tab") is None
