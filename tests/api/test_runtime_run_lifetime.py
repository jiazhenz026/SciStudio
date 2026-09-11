"""How a run ends without a browser (#2327), and the #1500 guarantee.

#1500 found lineage rows stuck in ``running`` in two scenarios: the GUI
websocket went away while a run was in flight, and the app shut down while a
run was in flight. Its hotfix cancelled every run two seconds after the last
``/ws`` client left and made shutdown await the cancelled tasks. ADR-055 §7
says closing the browser must not stop an analysis, so #2327 removed the
disconnect cancel. These tests pin what replaces it:

* a GUI disconnect neither cancels a run nor strands its lineage: the run keeps
  going, a reconnecting client still sees it, and it finishes normally;
* graceful shutdown mid-run leaves a terminal lineage row, also for a run that
  ignores cancellation;
* a row that a killed or crashed process left ``running`` is reconciled when
  the project is next opened, unless its owner is provably still alive;
* a worker process that dies finalises its run as ``failed``;
* a run whose start fails after its row was inserted is finalised too.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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
from tests.api.helpers import build_linear_workflow, wait_for_condition, wait_for_workflow_completion

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


def _write_marker(project: Path, run_id: str, owner: dict[str, Any]) -> Path:
    path = _run_lifetime.owner_marker_path(project, run_id)
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema": 1, "run_id": run_id, "workflow_id": "crashed-flow", **owner}), encoding="utf-8"
    )
    return path


def _unused_pid() -> int:
    pid = 2**31 - 7
    while psutil.pid_exists(pid):
        pid -= 1
    return pid


@pytest.fixture()
def live_process() -> Iterator[dict[str, Any]]:
    """A running process on this host, described the way an owner marker is."""
    proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
    try:
        owner = {
            "pid": proc.pid,
            "process_create_time": psutil.Process(proc.pid).create_time(),
            "host": socket.gethostname(),
        }
        yield owner
    finally:
        proc.communicate(input=b"", timeout=30)


# ---------------------------------------------------------------------------
# #1500 scenario 1: the GUI websocket goes away mid-run
# ---------------------------------------------------------------------------


def test_gui_disconnect_keeps_run_going_and_reconnect_still_sees_it(
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
        payload = build_linear_workflow(project, workflow_id="shutdown-flow")
        assert client.post("/api/workflows/", json=payload).status_code == 200
        gate = _GatedRunner(runtime.runner)
        runtime.runner = gate

        assert client.post("/api/workflows/shutdown-flow/execute").status_code == 200
        assert gate.started.wait(10)
        (run_id,) = runtime.lineage_store.runs_in_progress()
        marker = _run_lifetime.owner_marker_path(project, run_id)
        assert marker is not None and marker.is_file()
    # Leaving the client ran the lifespan shutdown.

    assert gate.cancelled.is_set()
    store = LineageStore(project / ".scistudio" / "lineage.db")
    try:
        row = store.get_run(run_id)
    finally:
        store.close()
    assert row is not None
    assert row["status"] == "cancelled"
    assert row["finished_at"]
    assert not marker.exists()
    assert run_id not in _run_lifetime.live_run_ids()


def test_shutdown_finalises_a_run_that_ignores_cancellation(tmp_path: Path) -> None:
    """A run still pending after the shutdown bound is finalised as cancelled."""

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
        _run_lifetime.claim_run(recorder, workflow_id="wf", project_dir=tmp_path)
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
    ["crashed_process", "reused_pid", "no_marker", "this_process_not_live", "unreadable_marker"],
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
        marker = _write_marker(
            opened_project,
            run_id,
            {"pid": _unused_pid(), "process_create_time": time.time() - 60, "host": socket.gethostname()},
        )
    elif owner_kind == "reused_pid":
        marker = _write_marker(
            opened_project,
            run_id,
            {**live_process, "process_create_time": live_process["process_create_time"] - 1000},
        )
    elif owner_kind == "this_process_not_live":
        # A run this process started whose store was closed under it (for
        # example by a project switch), so its own finalisation failed.
        marker = _write_marker(
            opened_project,
            run_id,
            {
                "pid": os.getpid(),
                "process_create_time": psutil.Process(os.getpid()).create_time(),
                "host": socket.gethostname(),
            },
        )
    elif owner_kind == "unreadable_marker":
        marker = _run_lifetime.owner_marker_path(opened_project, run_id)
        assert marker is not None
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("{not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="scistudio.api.runtime._run_lifetime"):
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


def test_open_keeps_run_owned_by_a_live_process(
    runtime: ApiRuntime, opened_project: Path, live_process: dict[str, Any]
) -> None:
    """Another live backend's run stays in flight, so retention keeps protecting it."""
    _seed_running_row(runtime.lineage_store, "run-live-elsewhere")
    marker = _write_marker(opened_project, "run-live-elsewhere", live_process)

    runtime.open_project(str(opened_project))

    assert runtime.lineage_store.get_run("run-live-elsewhere")["status"] == "running"
    assert marker.is_file()


def test_open_keeps_run_owned_by_another_host(runtime: ApiRuntime, opened_project: Path) -> None:
    """A process on another machine cannot be checked, so it counts as alive."""
    _seed_running_row(runtime.lineage_store, "run-other-host")
    marker = _write_marker(
        opened_project,
        "run-other-host",
        {"pid": _unused_pid(), "process_create_time": time.time(), "host": f"not-{socket.gethostname()}"},
    )

    runtime.open_project(str(opened_project))

    assert runtime.lineage_store.get_run("run-other-host")["status"] == "running"
    assert marker.is_file()


def test_open_keeps_run_live_in_this_process(runtime: ApiRuntime, opened_project: Path) -> None:
    recorder = _FakeRecorder("run-live-here")
    _run_lifetime.claim_run(recorder, workflow_id="crashed-flow", project_dir=opened_project)
    try:
        _seed_running_row(runtime.lineage_store, "run-live-here")

        runtime.open_project(str(opened_project))

        assert runtime.lineage_store.get_run("run-live-here")["status"] == "running"
    finally:
        _run_lifetime.release_run("run-live-here")


def test_open_removes_markers_of_runs_that_already_finished(runtime: ApiRuntime, opened_project: Path) -> None:
    """A process that died between finalising its row and removing its marker."""
    _seed_running_row(runtime.lineage_store, "run-finished", status="completed")
    marker = _write_marker(
        opened_project,
        "run-finished",
        {"pid": _unused_pid(), "process_create_time": time.time(), "host": socket.gethostname()},
    )

    runtime.open_project(str(opened_project))

    assert runtime.lineage_store.get_run("run-finished")["status"] == "completed"
    assert not marker.exists()


def test_a_started_run_is_claimed_before_its_row_is_visible(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    """Reopening the project mid-run must not reconcile the run this process is executing."""
    payload = build_linear_workflow(opened_project, workflow_id="claimed-flow")
    assert client.post("/api/workflows/", json=payload).status_code == 200
    gate = _GatedRunner(runtime.runner)
    runtime.runner = gate  # type: ignore[assignment]
    assert client.post("/api/workflows/claimed-flow/execute").status_code == 200
    assert gate.started.wait(10)
    (run_id,) = runtime.lineage_store.runs_in_progress()
    assert run_id in _run_lifetime.live_run_ids()

    runtime.open_project(str(opened_project))

    assert runtime.lineage_store.get_run(run_id)["status"] == "running"
    gate.release.set()
    wait_for_workflow_completion(runtime, "claimed-flow", timeout=60)


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
