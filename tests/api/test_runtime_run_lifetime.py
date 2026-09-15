"""How a run ends without a browser (#2327), and the #1500 guarantee.

#1500 found lineage rows stuck in ``running`` in two scenarios: the GUI
websocket went away while a run was in flight, and the app shut down while a
run was in flight. Its hotfix cancelled every run two seconds after the last
``/ws`` client left and made shutdown await the cancelled tasks. ADR-055 §7
says closing the browser must not stop an analysis, so #2327 removed the
disconnect cancel. These tests pin what replaces it:

* a GUI disconnect neither cancels a run nor strands its lineage;
* reopening the project, or switching to another one, mid-run keeps the run
  and records its blocks and outcome in its own project;
* graceful shutdown mid-run leaves a terminal lineage row, also for a run that
  ignores cancellation, and that run's own later completion does not
  overwrite it;
* a row that a killed or crashed process left ``running`` is reconciled when
  the project is next opened, unless its owner may still be alive;
* a run's terminal write is checked, retried through a reopened store, and
  otherwise kept in its owner marker for the next open;
* a worker process that dies finalises its run as ``failed``;
* a run whose start fails after its row was inserted is finalised too.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote

import psutil
import pytest
from fastapi.testclient import TestClient

from scistudio.api import runtime as runtime_module
from scistudio.api.app import create_app
from scistudio.api.runtime import ApiRuntime, _run_lifetime
from scistudio.api.runtime import _runs as runs_module
from scistudio.blocks.base.state import BlockState
from scistudio.core.lineage.record import RunRecord
from scistudio.core.lineage.store import LineageStore
from scistudio.engine.events import WORKFLOW_COMPLETED
from scistudio.engine.run_logging import run_log_path
from scistudio.workflow.definition import WorkflowDefinition
from tests.api.helpers import build_linear_workflow, wait_for_condition, wait_for_workflow_completion, ws_hello

_LOGGER = "scistudio.api.runtime._run_lifetime"

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class _GatedRunner:
    """Holds every block at the runner until ``release`` is set, then delegates.

    Lets a test keep a run in flight for as long as it needs without a
    sleeping worker, while the run still executes through the real runner.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.started = threading.Event()
        self.release = threading.Event()
        self.cancelled = threading.Event()

    async def run(self, block: Any, inputs: dict[str, Any], config: dict[str, Any]) -> Any:
        self.started.set()
        try:
            while not self.release.is_set():
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return await self._inner.run(block, inputs, config)

    async def run_prompt(self, block: Any, inputs: dict[str, Any], config: dict[str, Any]) -> Any:
        return await self._inner.run_prompt(block, inputs, config)

    async def cancel(self, workflow_id: str, block_id: str) -> Any:
        return await self._inner.cancel(workflow_id, block_id)


class _FakeRecorder:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.statuses: list[str] = []

    def finalize_run(self, *, status: str) -> None:
        self.statuses.append(status)

    def dispose(self) -> None:
        pass


def _lineage_rows(client: TestClient, workflow_id: str) -> list[dict[str, Any]]:
    response = client.get("/api/runs", params={"workflow_id": workflow_id})
    assert response.status_code == 200
    return list(response.json()["runs"])


def _seed_running_row(store: LineageStore, run_id: str, *, status: str = "running") -> None:
    store.insert_run(
        RunRecord(
            run_id=run_id,
            workflow_id="crashed-flow",
            workflow_yaml_snapshot="",
            started_at="2026-09-11T00:00:00+00:00",
            status=status,
            environment_snapshot={},
        )
    )


def _owner(pid: int, create_time: float | None, **extra: Any) -> dict[str, Any]:
    """An owner description on this machine, the way ``claim_run`` writes one."""
    return {
        "pid": pid,
        "process_create_time": create_time,
        "machine_id": _run_lifetime.machine_id(),
        "host": socket.gethostname(),
        **extra,
    }


def _write_marker(project: Path, run_id: str, owner: dict[str, Any]) -> Path:
    path = _run_lifetime.owner_marker_path(project, run_id)
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": 2,
        "run_id": run_id,
        "workflow_id": "crashed-flow",
        "claimed_at": datetime.now(UTC).isoformat(),
    }
    path.write_text(json.dumps({**payload, **owner}), encoding="utf-8")
    return path


def _unused_pid() -> int:
    pid = 2**31 - 7
    while psutil.pid_exists(pid):
        pid -= 1
    return pid


def _start_gated_run(client: TestClient, runtime: ApiRuntime, project: Path, workflow_id: str) -> _GatedRunner:
    payload = build_linear_workflow(project, workflow_id=workflow_id)
    assert client.post("/api/workflows/", json=payload).status_code == 200
    gate = _GatedRunner(runtime.runner)
    runtime.runner = gate  # type: ignore[assignment]
    assert client.post(f"/api/workflows/{workflow_id}/execute").status_code == 200
    assert gate.started.wait(10)
    return gate


def _finish(runtime: ApiRuntime, gate: _GatedRunner, workflow_id: str, run_id: str) -> None:
    gate.release.set()
    wait_for_workflow_completion(runtime, workflow_id, timeout=60)
    wait_for_condition(lambda: run_id not in _run_lifetime.live_run_ids(), timeout=10)


@pytest.fixture()
def live_process() -> Iterator[dict[str, Any]]:
    """A running process on this machine, described the way an owner marker is."""
    proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
    try:
        yield _owner(proc.pid, psutil.Process(proc.pid).create_time())
    finally:
        proc.communicate(input=b"", timeout=30)


# ---------------------------------------------------------------------------
# #1500 scenario 1: the GUI websocket goes away mid-run
# ---------------------------------------------------------------------------


def test_gui_disconnect_keeps_run_going_and_a_reconnect_sees_history_and_later_events(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    """The run outlives the removed 2 s grace period and finishes normally."""
    payload = build_linear_workflow(opened_project, workflow_id="disconnect-flow")
    assert client.post("/api/workflows/", json=payload).status_code == 200
    gate = _GatedRunner(runtime.runner)
    runtime.runner = gate  # type: ignore[assignment]

    with client.websocket_connect("/ws"):
        assert client.post("/api/workflows/disconnect-flow/execute").status_code == 200
        assert gate.started.wait(10)
    # The only GUI client is gone. #1500 cancelled every run 2 s after this.
    time.sleep(2.5)

    run = runtime.workflow_runs["disconnect-flow"]
    assert not run.task.done()
    assert not gate.cancelled.is_set()

    with client.websocket_connect("/ws") as websocket:
        ws_hello(websocket)
        # What a reconnecting page gets: no snapshot of the states it missed
        # (after its identity greeting, the next frame answers its ping), the
        # run in Run history, and the run's events from here on.
        websocket.send_json({"type": "ping"})
        assert websocket.receive_json() == {"type": "pong"}
        rows = _lineage_rows(client, "disconnect-flow")
        assert [row["status"] for row in rows] == ["running"]
        run_id = rows[0]["run_id"]

        gate.release.set()
        seen: list[str] = []
        while WORKFLOW_COMPLETED not in seen:
            seen.append(websocket.receive_json()["type"])
            assert len(seen) < 500

    wait_for_workflow_completion(runtime, "disconnect-flow", timeout=60)
    assert run.scheduler.block_states() == {
        "load": BlockState.DONE,
        "transform": BlockState.DONE,
        "final": BlockState.DONE,
    }
    wait_for_condition(lambda: _lineage_rows(client, "disconnect-flow")[0]["status"] == "completed", timeout=10)
    assert run_id not in _run_lifetime.live_run_ids()


# ---------------------------------------------------------------------------
# Reopening the project, or switching projects, mid-run (audit P1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("how", ["id", "path"])
def test_reopening_the_project_mid_run_keeps_its_history(
    client: TestClient, runtime: ApiRuntime, opened_project: Path, how: str
) -> None:
    """A page reload reopens the project (Open Recent by id, the dialog by path)."""
    gate = _start_gated_run(client, runtime, opened_project, "reopen-flow")
    store_before = runtime.lineage_store
    (run_id,) = store_before.runs_in_progress()

    target = runtime.active_project.id if how == "id" else quote(opened_project.as_posix(), safe="/:")
    assert client.get(f"/api/projects/{target}").status_code == 200
    assert runtime.lineage_store is store_before, "reopening the active project keeps its store"
    assert [row["status"] for row in _lineage_rows(client, "reopen-flow")] == ["running"]

    _finish(runtime, gate, "reopen-flow", run_id)

    row = runtime.lineage_store.get_run(run_id)
    assert row["status"] == "completed"
    assert row["provenance_degraded"] == 0
    assert len(runtime.lineage_store.list_block_executions(run_id)) == 3
    marker = _run_lifetime.owner_marker_path(opened_project, run_id)
    assert marker is not None and not marker.exists()
    # The next open has nothing to reconcile.
    runtime.open_project(str(opened_project))
    assert runtime.lineage_store.get_run(run_id)["status"] == "completed"


def test_switching_projects_mid_run_keeps_the_run_and_its_history(
    client: TestClient, runtime: ApiRuntime, opened_project: Path, project_parent: Path
) -> None:
    """A switch does not end the run; it is visible on switching back and records in its own project."""
    gate = _start_gated_run(client, runtime, opened_project, "switch-flow")
    first_id = runtime.active_project.id
    first_store = runtime.lineage_store
    (run_id,) = first_store.runs_in_progress()

    other = client.post(
        "/api/projects/", json={"name": "Other Project", "description": "", "path": str(project_parent)}
    )
    assert other.status_code == 200
    assert runtime.active_project.id != first_id
    assert runtime.lineage_store is not first_store
    assert not runtime.workflow_runs["switch-flow"].task.done(), "a project switch does not end the run"

    assert client.get(f"/api/projects/{first_id}").status_code == 200
    assert [row["status"] for row in _lineage_rows(client, "switch-flow")] == ["running"]
    assert client.get(f"/api/projects/{other.json()['id']}").status_code == 200

    _finish(runtime, gate, "switch-flow", run_id)

    store = LineageStore(_run_lifetime.lineage_db_path(opened_project))
    try:
        row = store.get_run(run_id)
        assert row is not None
        assert row["status"] == "completed"
        assert row["provenance_degraded"] == 0
        assert len(store.list_block_executions(run_id)) == 3
    finally:
        store.close()
    with pytest.raises(sqlite3.ProgrammingError):
        first_store.count("runs")  # the retired store closed once its last run ended


# ---------------------------------------------------------------------------
# #1500 scenario 2: the app shuts down mid-run
# ---------------------------------------------------------------------------


def test_graceful_shutdown_mid_run_leaves_terminal_lineage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake_home))
    parent = tmp_path / "projects"
    parent.mkdir()

    with TestClient(create_app()) as client:
        runtime = client.app.state.runtime
        created = client.post("/api/projects/", json={"name": "Shutdown", "description": "", "path": str(parent)})
        project = Path(created.json()["path"])
        gate = _start_gated_run(client, runtime, project, "shutdown-flow")
        (run_id,) = runtime.lineage_store.runs_in_progress()
        marker = _run_lifetime.owner_marker_path(project, run_id)
        assert marker is not None and marker.is_file()
    # Leaving the client ran the lifespan shutdown.

    assert gate.cancelled.is_set()
    store = LineageStore(_run_lifetime.lineage_db_path(project))
    try:
        row = store.get_run(run_id)
    finally:
        store.close()
    assert row is not None
    assert row["status"] == "cancelled"
    assert row["finished_at"]
    assert not marker.exists()
    assert run_id not in _run_lifetime.live_run_ids()


def test_shutdown_finalises_a_run_that_ignores_cancellation_and_keeps_that_outcome(tmp_path: Path) -> None:
    """A straggler is recorded cancelled; its own later completion does not overwrite it."""

    async def _run() -> None:
        release = asyncio.Event()
        entered = asyncio.Event()

        async def _stubborn() -> None:
            entered.set()
            while not release.is_set():
                try:
                    await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    continue

        task = asyncio.create_task(_stubborn())
        # A cancel delivered before the task's first step ends it at once; a
        # real run task is always already executing when shutdown cancels it.
        await entered.wait()
        recorder = _FakeRecorder("run-stubborn")
        _run_lifetime.claim_run(recorder, workflow_id="wf", project_dir=tmp_path, store=None)
        _run_lifetime.attach_task("run-stubborn", task)
        marker = _run_lifetime.owner_marker_path(tmp_path, "run-stubborn")
        assert marker is not None and marker.is_file()
        fake_runtime = SimpleNamespace(workflow_runs={"wf": SimpleNamespace(task=task)})

        forced = await _run_lifetime.shutdown_workflow_runs(fake_runtime, timeout_sec=0.1)  # type: ignore[arg-type]

        assert forced == ["run-stubborn"]
        assert recorder.statuses == ["cancelled"]
        assert "run-stubborn" not in _run_lifetime.live_run_ids()
        assert not marker.exists()

        release.set()
        await task
        # The task's own done-callback finalisation after the fact.
        runtime = object.__new__(ApiRuntime)
        scheduler = SimpleNamespace(block_states=lambda: {}, dispose=lambda: None)
        runtime._finalize_lineage_run(recorder, task, scheduler)  # type: ignore[arg-type]
        assert recorder.statuses == ["cancelled"]

    asyncio.run(_run())


def test_shutdown_with_no_live_runs_is_a_no_op() -> None:
    async def _run() -> None:
        done = asyncio.create_task(asyncio.sleep(0))
        await done
        fake_runtime = SimpleNamespace(workflow_runs={"wf": SimpleNamespace(task=done)})
        assert await _run_lifetime.shutdown_workflow_runs(fake_runtime) == []  # type: ignore[arg-type]

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# The backend was killed or crashed: reconcile on the next open
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "owner_kind",
    ["crashed_process", "reused_pid", "renamed_host", "no_marker", "this_process_not_live", "invalid_marker"],
)
def test_open_reconciles_run_left_running_by_a_dead_owner(
    runtime: ApiRuntime,
    opened_project: Path,
    live_process: dict[str, Any],
    owner_kind: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    run_id = f"stale-{owner_kind.replace('_', '-')}"
    _seed_running_row(runtime.lineage_store, run_id)
    marker: Path | None = None
    if owner_kind == "crashed_process":
        marker = _write_marker(opened_project, run_id, _owner(_unused_pid(), time.time() - 60))
    elif owner_kind == "reused_pid":
        marker = _write_marker(
            opened_project,
            run_id,
            {**live_process, "process_create_time": live_process["process_create_time"] - 1000},
        )
    elif owner_kind == "renamed_host":
        # Same machine id, a hostname this machine no longer has: judged here.
        marker = _write_marker(
            opened_project,
            run_id,
            _owner(_unused_pid(), time.time() - 60, host=f"old-name-of-{socket.gethostname()}"),
        )
    elif owner_kind == "this_process_not_live":
        marker = _write_marker(opened_project, run_id, _owner(os.getpid(), psutil.Process(os.getpid()).create_time()))
    elif owner_kind == "invalid_marker":
        marker = _run_lifetime.owner_marker_path(opened_project, run_id)
        assert marker is not None
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("{not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        runtime.open_project(str(opened_project))

    row = runtime.lineage_store.get_run(run_id)
    assert row["status"] == _run_lifetime.INTERRUPTED_RUN_STATUS == "failed"
    assert row["finished_at"]
    assert run_id not in runtime.lineage_store.runs_in_progress()
    if marker is not None:
        assert not marker.exists()
    reasons = [record.getMessage() for record in caplog.records if run_id in record.getMessage()]
    assert reasons, "reconciliation must say why the run was finalised"
    assert "can no longer finish" in reasons[0]
    log_file = run_log_path(run_id, project_root=opened_project)
    assert log_file.is_file()
    assert "can no longer finish" in log_file.read_text(encoding="utf-8")


def test_open_reconciles_a_run_whose_owner_is_a_zombie(
    runtime: ApiRuntime, opened_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zombie_pid = _unused_pid()
    created = time.time() - 30
    real_process = psutil.Process

    class _Zombie:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def create_time(self) -> float:
            return created

        def status(self) -> str:
            return psutil.STATUS_ZOMBIE

    def _process(pid: int | None = None) -> Any:
        return _Zombie(zombie_pid) if pid == zombie_pid else real_process(pid)

    monkeypatch.setattr(psutil, "Process", _process)
    _seed_running_row(runtime.lineage_store, "run-zombie-owner")
    _write_marker(opened_project, "run-zombie-owner", _owner(zombie_pid, created))

    runtime.open_project(str(opened_project))

    assert runtime.lineage_store.get_run("run-zombie-owner")["status"] == "failed"


def test_open_leaves_a_run_whose_marker_cannot_be_read(
    runtime: ApiRuntime, opened_project: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A read error is not proof that the owner is dead (with-context audit P3-1)."""
    _seed_running_row(runtime.lineage_store, "run-unreadable")
    marker = _write_marker(opened_project, "run-unreadable", _owner(_unused_pid(), time.time() - 60))
    real_read_text = Path.read_text

    def _read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.name == marker.name:
            raise PermissionError(13, "The process cannot access the file because it is being used")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _read_text)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        runtime.open_project(str(opened_project))
    monkeypatch.setattr(Path, "read_text", real_read_text)

    assert runtime.lineage_store.get_run("run-unreadable")["status"] == "running"
    assert marker.is_file()
    assert any(
        "run-unreadable" in record.getMessage() and "could not be read" in record.getMessage()
        for record in caplog.records
    )


def test_open_keeps_run_owned_by_a_live_process(
    runtime: ApiRuntime, opened_project: Path, live_process: dict[str, Any]
) -> None:
    """Another live backend's run stays in flight, so retention keeps protecting it."""
    _seed_running_row(runtime.lineage_store, "run-live-elsewhere")
    marker = _write_marker(opened_project, "run-live-elsewhere", live_process)

    runtime.open_project(str(opened_project))

    assert runtime.lineage_store.get_run("run-live-elsewhere")["status"] == "running"
    assert marker.is_file()


def test_open_keeps_runs_owned_by_another_machine_and_reports_stale_ones(
    runtime: ApiRuntime, opened_project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Another machine's process cannot be checked; one older than the limit is reported."""
    elsewhere = {"pid": _unused_pid(), "process_create_time": time.time(), "machine_id": "another-machine-id"}
    _seed_running_row(runtime.lineage_store, "run-foreign-recent")
    _seed_running_row(runtime.lineage_store, "run-foreign-stale")
    _write_marker(opened_project, "run-foreign-recent", {**elsewhere, "host": "lab-node-1"})
    stale_since = datetime.now(UTC) - _run_lifetime.FOREIGN_OWNER_STALE_AFTER - timedelta(hours=1)
    _write_marker(
        opened_project,
        "run-foreign-stale",
        {**elsewhere, "host": "lab-node-2", "claimed_at": stale_since.isoformat()},
    )

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        runtime.open_project(str(opened_project))

    assert runtime.lineage_store.get_run("run-foreign-recent")["status"] == "running"
    assert runtime.lineage_store.get_run("run-foreign-stale")["status"] == "running"
    messages = [record.getMessage() for record in caplog.records]
    assert any("run-foreign-stale" in message and "another machine" in message for message in messages)
    assert not any("run-foreign-recent" in message for message in messages)


def test_open_keeps_run_live_in_this_process(runtime: ApiRuntime, opened_project: Path) -> None:
    recorder = _FakeRecorder("run-live-here")
    _run_lifetime.claim_run(recorder, workflow_id="crashed-flow", project_dir=opened_project, store=None)
    try:
        _seed_running_row(runtime.lineage_store, "run-live-here")

        runtime.open_project(str(opened_project))

        assert runtime.lineage_store.get_run("run-live-here")["status"] == "running"
    finally:
        _run_lifetime.release_run("run-live-here")


def test_open_removes_markers_of_runs_that_already_finished(runtime: ApiRuntime, opened_project: Path) -> None:
    """A process that died between finalising its row and removing its marker."""
    _seed_running_row(runtime.lineage_store, "run-finished", status="completed")
    marker = _write_marker(opened_project, "run-finished", _owner(_unused_pid(), time.time()))

    runtime.open_project(str(opened_project))

    assert runtime.lineage_store.get_run("run-finished")["status"] == "completed"
    assert not marker.exists()


def test_open_removes_staging_files_of_claims_that_died(runtime: ApiRuntime, opened_project: Path) -> None:
    owner_dir = opened_project / ".scistudio" / "run-owners"
    owner_dir.mkdir(parents=True, exist_ok=True)
    abandoned = owner_dir / "run-died.json.tmp"
    abandoned.write_text("{}", encoding="utf-8")
    an_hour_ago = time.time() - 3600
    os.utime(abandoned, (an_hour_ago, an_hour_ago))
    in_progress = owner_dir / "run-writing.json.tmp"
    in_progress.write_text("{}", encoding="utf-8")

    runtime.open_project(str(opened_project))

    assert not abandoned.exists()
    assert in_progress.exists()


def test_machine_id_is_stable_and_names_the_machine() -> None:
    assert _run_lifetime.machine_id() == _run_lifetime.machine_id()
    if sys.platform == "win32" or Path("/etc/machine-id").is_file():
        assert not _run_lifetime.machine_id().startswith("hostname:")


# ---------------------------------------------------------------------------
# A run's terminal write is checked
# ---------------------------------------------------------------------------


def test_release_rewrites_the_outcome_through_a_reopened_store(runtime: ApiRuntime, opened_project: Path) -> None:
    """The store a run wrote through failed; its outcome still lands."""
    store = runtime.lineage_store
    _seed_running_row(store, "run-stranded")
    stranded = LineageStore(_run_lifetime.lineage_db_path(opened_project))
    stranded.close()
    _run_lifetime.claim_run(
        _FakeRecorder("run-stranded"), workflow_id="crashed-flow", project_dir=opened_project, store=stranded
    )
    marker = _run_lifetime.owner_marker_path(opened_project, "run-stranded")
    assert marker is not None and marker.is_file()

    _run_lifetime.release_run("run-stranded", terminal_status="completed")

    row = store.get_run("run-stranded")
    assert row["status"] == "completed"
    assert row["provenance_degraded"] == 1
    assert not marker.exists()


def test_an_unrecordable_outcome_waits_in_the_marker_for_the_next_open(
    runtime: ApiRuntime, opened_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner marker is never deleted unless the terminal write succeeded."""
    store = runtime.lineage_store
    _seed_running_row(store, "run-unrecorded")
    stranded = LineageStore(_run_lifetime.lineage_db_path(opened_project))
    stranded.close()
    _run_lifetime.claim_run(
        _FakeRecorder("run-unrecorded"), workflow_id="crashed-flow", project_dir=opened_project, store=stranded
    )
    marker = _run_lifetime.owner_marker_path(opened_project, "run-unrecorded")
    assert marker is not None
    original = _run_lifetime._open_store_by_path

    def _no_store(project_dir: Path) -> Any:
        raise OSError("the disk went away")

    monkeypatch.setattr(_run_lifetime, "_open_store_by_path", _no_store)
    _run_lifetime.release_run("run-unrecorded", terminal_status="completed")
    monkeypatch.setattr(_run_lifetime, "_open_store_by_path", original)

    assert store.get_run("run-unrecorded")["status"] == "running"
    assert json.loads(marker.read_text(encoding="utf-8"))["unrecorded_status"] == "completed"

    runtime.open_project(str(opened_project))

    assert store.get_run("run-unrecorded")["status"] == "completed"
    assert not marker.exists()


def test_a_claim_is_live_before_its_marker_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A sweep that finds the marker must see the run as live (with-context audit P3-2)."""
    seen: dict[str, bool] = {}
    original = _run_lifetime._write_marker

    def _spy(path: Path, payload: dict[str, Any]) -> None:
        seen["live"] = payload["run_id"] in _run_lifetime.live_run_ids()
        original(path, payload)

    monkeypatch.setattr(_run_lifetime, "_write_marker", _spy)
    _run_lifetime.claim_run(_FakeRecorder("run-order"), workflow_id="wf", project_dir=tmp_path, store=None)
    try:
        assert seen == {"live": True}
    finally:
        _run_lifetime.release_run("run-order")


def test_a_run_whose_marker_cannot_be_written_runs_without_lineage(
    runtime: ApiRuntime, opened_project: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Better no row than an unowned one another backend would take for interrupted."""

    def _fail(path: Path, payload: dict[str, Any]) -> None:
        raise PermissionError(13, "read-only project directory")

    monkeypatch.setattr(_run_lifetime, "_write_marker", _fail)
    before = _run_lifetime.live_run_ids()

    with caplog.at_level(logging.WARNING):
        recorder = runtime._build_lineage_recorder(
            workflow_id="main", workflow=WorkflowDefinition(id="main"), execute_from=None
        )

    assert recorder is None
    assert runtime.lineage_store.list_runs(workflow_id="main") == []
    assert _run_lifetime.live_run_ids() == before
    assert any("running it without lineage" in record.getMessage() for record in caplog.records)


# ---------------------------------------------------------------------------
# A run's worker process dies
# ---------------------------------------------------------------------------


def test_worker_death_finalises_run_as_failed(client: TestClient, runtime: ApiRuntime, opened_project: Path) -> None:
    payload = build_linear_workflow(opened_project, workflow_id="worker-death-flow", middle_sleep_seconds=120)
    assert client.post("/api/workflows/", json=payload).status_code == 200
    assert client.post("/api/workflows/worker-death-flow/execute").status_code == 200

    handle = wait_for_condition(
        lambda: runtime.process_registry.get_handle("worker-death-flow", "transform"),
        timeout=25,
    )
    # Kill the worker from outside, the way an OOM kill or a crash ends it.
    psutil.Process(handle.pid).kill()

    run = wait_for_workflow_completion(runtime, "worker-death-flow", timeout=25)
    states = run.scheduler.block_states()
    assert states["load"] == BlockState.DONE
    assert states["transform"] == BlockState.ERROR
    assert states["final"] == BlockState.SKIPPED
    wait_for_condition(lambda: _lineage_rows(client, "worker-death-flow")[0]["status"] == "failed", timeout=10)
    assert not runtime.lineage_store.runs_in_progress()


# ---------------------------------------------------------------------------
# A run whose start fails after its row was inserted
# ---------------------------------------------------------------------------


def test_start_failure_after_row_insert_finalises_the_row(
    client: TestClient, runtime: ApiRuntime, opened_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = build_linear_workflow(opened_project, workflow_id="broken-start-flow")
    assert client.post("/api/workflows/", json=payload).status_code == 200

    def _broken_scheduler(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("scheduler construction failed")

    monkeypatch.setattr(runs_module, "DAGScheduler", _broken_scheduler)

    with pytest.raises(RuntimeError, match="scheduler construction failed"):
        runtime.start_workflow("broken-start-flow")

    rows = runtime.lineage_store.list_runs(workflow_id="broken-start-flow")
    assert [row["status"] for row in rows] == ["failed"]
    assert rows[0]["run_id"] not in _run_lifetime.live_run_ids()
    marker = _run_lifetime.owner_marker_path(opened_project, rows[0]["run_id"])
    assert marker is not None and not marker.exists()
