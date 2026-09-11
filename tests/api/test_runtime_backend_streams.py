"""The backend's long-lived streams end when it stops (#2327).

The web server finishes open connections before it runs the application's
shutdown. A connected page keeps the event socket and the log stream open, and
an AI terminal session can run with no socket at all. Each must end on a stop,
or the shutdown never runs (re-audit N2, R1). A deleted project must not be
recreated by a run's final write (re-audit N3).
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from scistudio.api import runtime as runtime_module
from scistudio.api.app import create_app
from scistudio.api.routes import ai_pty
from scistudio.api.runtime import ApiRuntime, LogBroadcaster, _rmtree_force, _run_lifetime, _stop_request
from scistudio.blocks.base.state import BlockState
from scistudio.api.ws import websocket_handler
from scistudio.core.lineage.record import RunRecord
from scistudio.core.lineage.store import LineageStore
from scistudio.engine.events import EventBus


class _TerminalSession:
    """Stands in for an AI terminal session: a real child process and kill_tree."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])

    def kill_tree(self) -> None:
        self.proc.kill()
        self.proc.wait(timeout=30)


class _FakeRecorder:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    def finalize_run(self, *, status: str) -> None:
        pass

    def dispose(self) -> None:
        pass


def test_the_event_socket_handler_returns_when_the_client_leaves() -> None:
    """Before the fix the outbound loop kept waiting on its idle queue."""

    async def _run() -> None:
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect(1012))
        ws.send_json = AsyncMock()
        await asyncio.wait_for(websocket_handler(ws, EventBus()), timeout=5)

    asyncio.run(_run())


def test_closing_the_log_broadcaster_ends_every_stream() -> None:
    async def _run() -> None:
        broadcaster = LogBroadcaster()
        existing = broadcaster.subscribe()
        broadcaster.close()
        assert await asyncio.wait_for(existing.get(), timeout=1) is LogBroadcaster.END
        late = broadcaster.subscribe()
        assert late.get_nowait() is LogBroadcaster.END
        broadcaster.close()  # a second close is harmless
        assert existing.empty()

    asyncio.run(_run())


def test_ai_terminal_sessions_are_killed_and_deregistered(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _TerminalSession()
    monkeypatch.setitem(ai_pty._active_ptys, "tab-unattached", session)
    monkeypatch.setitem(ai_pty._engine_tab_to_run, "tab-unattached", "run-x")
    monkeypatch.setitem(ai_pty._engine_run_to_run_dir, "run-x", Path("unused"))
    try:
        assert _stop_request.terminate_ai_terminal_sessions(timeout_sec=30) == 1
        assert session.proc.poll() is not None
        assert "tab-unattached" not in ai_pty._active_ptys
        assert "tab-unattached" not in ai_pty._engine_tab_to_run
        assert "run-x" not in ai_pty._engine_run_to_run_dir
    finally:
        if session.proc.poll() is None:
            session.kill_tree()


def test_a_graceful_stop_kills_an_ai_terminal_session_with_no_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-audit R1: an engine-started session without a socket survived Stop."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake_home))
    session = _TerminalSession()
    try:
        with TestClient(create_app()):
            ai_pty._active_ptys["tab-no-socket"] = session  # type: ignore[assignment]
        # Leaving the client ran the lifespan shutdown.
        assert session.proc.poll() is not None
        assert "tab-no-socket" not in ai_pty._active_ptys
    finally:
        ai_pty._active_ptys.pop("tab-no-socket", None)
        if session.proc.poll() is None:
            session.kill_tree()


def test_a_run_whose_project_was_deleted_does_not_recreate_it(tmp_path: Path) -> None:
    """Re-audit N3: the retry path recreated the folder and a fresh lineage.db."""
    project = tmp_path / "gone-project"
    store = LineageStore(_prepare_db(project))
    store.insert_run(
        RunRecord(
            run_id="run-orphaned",
            workflow_id="wf",
            workflow_yaml_snapshot="",
            started_at="2026-09-11T00:00:00+00:00",
            status="running",
            environment_snapshot={},
        )
    )
    stranded: Any = store
    stranded.close()
    _run_lifetime.claim_run(_FakeRecorder("run-orphaned"), workflow_id="wf", project_dir=project, store=stranded)
    _rmtree_force(project)
    assert not project.exists()

    _run_lifetime.release_run("run-orphaned", terminal_status="completed")

    assert not project.exists(), "a deleted project must stay deleted"
    assert "run-orphaned" not in _run_lifetime.live_run_ids()


def _prepare_db(project: Path) -> Path:
    db = _run_lifetime.lineage_db_path(project)
    db.parent.mkdir(parents=True)
    return db


def test_cleanup_after_a_completed_run_does_not_recreate_a_deleted_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2352: artifact retention after a successful run created an empty lineage.db.

    Goes through completion (the run's own finalisation) and the cleanup it
    triggers, for a project folder that is gone and for one whose database is.
    """
    monkeypatch.delenv("SCISTUDIO_ARTIFACT_RETENTION", raising=False)
    gone = tmp_path / "deleted-project"
    without_db = tmp_path / "project-without-lineage"
    (without_db / ".scistudio").mkdir(parents=True)
    runtime = object.__new__(ApiRuntime)
    for project in (gone, without_db):
        scheduler = SimpleNamespace(block_states=lambda: {"only": BlockState.DONE}, dispose=lambda: None)
        finished = SimpleNamespace(cancelled=lambda: False, exception=lambda: None)
        status = runtime._finalize_lineage_run(
            _FakeRecorder(f"run-{project.name}"),
            finished,  # type: ignore[arg-type]
            scheduler,  # type: ignore[arg-type]
            project_dir=str(project),
        )
        assert status == "completed", "the cleanup path only runs after a completed run"

    assert not gone.exists(), "a deleted project must stay deleted"
    assert not _run_lifetime.lineage_db_path(without_db).exists()
