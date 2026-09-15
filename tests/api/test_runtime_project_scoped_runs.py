"""#2362 / #2433 — a run belongs to the project that started it.

``ApiRuntime.workflow_runs`` is keyed by workflow id, and ``main`` is the default
workflow name in every project. #2362 stopped the next project's ``main`` from
resolving the previous project's run. #2365 then kept a live run executing,
detached, across the switch; its events still carried only ``workflow_id``, so
they landed on the next project's same-named workflow.

#2433 (owner decision): leaving a project ends its runs. The GUI asks first,
``end_project_runs`` cancels them, and a switch that would leave a live run
behind is refused. A GUI disconnect still never cancels a run (#2327).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime
from scistudio.api.runtime.models import WorkflowRun


class _FakeTask:
    """Stands in for a run's ``asyncio.Task``.

    The registry only reads ``done()``. The lifespan shutdown waits on real
    asyncio tasks, so every fake is marked finished before the client fixture
    tears the app down (see ``_finish_fake_runs``).
    """

    def __init__(self, *, done: bool) -> None:
        self._done = done

    def done(self) -> bool:
        return self._done

    def cancel(self) -> None:
        self._done = True

    def __await__(self):  # type: ignore[no-untyped-def]
        return iter(())


_FAKE_TASKS: list[_FakeTask] = []


@pytest.fixture(autouse=True)
def _finish_fake_runs(client: TestClient) -> Iterator[None]:
    """Finish every fake run before ``client`` runs the lifespan shutdown."""
    yield
    for task in _FAKE_TASKS:
        task.cancel()
    _FAKE_TASKS.clear()


def _fake_run(*, done: bool) -> WorkflowRun:
    """A ``WorkflowRun`` stand-in; only ``task.done()`` is read by the registry."""
    task = _FakeTask(done=done)
    _FAKE_TASKS.append(task)
    return WorkflowRun(
        scheduler=object(),  # type: ignore[arg-type]
        task=task,  # type: ignore[arg-type]
        checkpoint_manager=object(),  # type: ignore[arg-type]
    )


def _make_project(client: TestClient, parent: Path, name: str) -> str:
    response = client.post(
        "/api/projects/",
        json={"name": name, "description": "", "path": str(parent)},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_switching_projects_retires_the_previous_projects_runs(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    alpha = _make_project(client, project_parent, "Alpha")
    beta = _make_project(client, project_parent, "Beta")

    runtime.open_project(alpha)
    finished = _fake_run(done=True)
    runtime.workflow_runs["main"] = finished

    runtime.open_project(beta)

    # Beta's `main` must not resolve Alpha's run.
    assert "main" not in runtime.workflow_runs
    with pytest.raises(KeyError):
        runtime.get_run("main")


def test_switching_away_from_a_live_run_is_refused(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    """#2433: a run is never carried into another project; it must be ended first."""
    from scistudio.api.runtime._runs import ProjectRunsLiveError

    alpha = _make_project(client, project_parent, "Alpha")
    beta = _make_project(client, project_parent, "Beta")

    runtime.open_project(alpha)
    live = _fake_run(done=False)
    live.run_id = "run-alpha"
    runtime.workflow_runs["main"] = live

    with pytest.raises(ProjectRunsLiveError) as refused:
        runtime.open_project(beta)

    assert refused.value.run_ids == ["run-alpha"]
    assert runtime.active_project is not None and runtime.active_project.id == alpha
    assert runtime.workflow_runs.get("main") is live


def test_the_projects_route_refuses_the_switch_with_the_live_run_ids(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    alpha = _make_project(client, project_parent, "Alpha")
    beta = _make_project(client, project_parent, "Beta")
    runtime.open_project(alpha)
    live = _fake_run(done=False)
    live.run_id = "run-alpha"
    runtime.workflow_runs["main"] = live

    listed = client.get("/api/projects/active/runs")
    assert listed.status_code == 200
    assert listed.json() == {"project_id": alpha, "runs": [{"run_id": "run-alpha", "workflow_id": "main"}]}

    for response in (
        client.get(f"/api/projects/{beta}"),
        client.post("/api/projects/", json={"name": "Gamma", "description": "", "path": str(project_parent)}),
    ):
        assert response.status_code == 409, response.text
        detail = response.json()["detail"]
        assert detail["code"] == "project_runs_live"
        assert detail["run_ids"] == ["run-alpha"]
    assert runtime.active_project is not None and runtime.active_project.id == alpha


def test_ended_runs_let_the_switch_proceed(client: TestClient, runtime: ApiRuntime, project_parent: Path) -> None:
    alpha = _make_project(client, project_parent, "Alpha")
    beta = _make_project(client, project_parent, "Beta")
    runtime.open_project(alpha)
    live = _fake_run(done=False)
    runtime.workflow_runs["main"] = live

    live.task.cancel()  # what end_project_runs achieves
    assert client.get("/api/projects/active/runs").json() == {"project_id": alpha, "runs": []}
    assert client.get(f"/api/projects/{beta}").status_code == 200
    assert runtime.workflow_runs == {}


def test_a_same_workflow_start_is_refused_while_its_run_is_live(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    """Different workflows may run at once; the same workflow may not run twice (#2433)."""
    from scistudio.api.runtime._runs import WorkflowAlreadyRunningError, _is_workflow_running

    alpha = _make_project(client, project_parent, "Alpha")
    runtime.open_project(alpha)
    runtime.workflow_runs["main"] = _fake_run(done=False)

    assert _is_workflow_running(runtime, "main") is True
    assert _is_workflow_running(runtime, "other") is False
    with pytest.raises(WorkflowAlreadyRunningError):
        runtime.start_workflow("main")


def test_reopening_the_active_project_keeps_its_runs(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    """The GUI re-opens the project it is already on; that is not a switch."""
    alpha = _make_project(client, project_parent, "Alpha")
    runtime.open_project(alpha)
    live = _fake_run(done=False)
    runtime.workflow_runs["main"] = live

    runtime.open_project(alpha)

    assert runtime.workflow_runs.get("main") is live


def test_updating_or_deleting_another_project_does_not_switch_to_it(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    """#2433: only an explicit open leaves the active project and ends its runs."""
    alpha = _make_project(client, project_parent, "Alpha")
    beta = _make_project(client, project_parent, "Beta")
    runtime.open_project(alpha)
    live = _fake_run(done=False)
    runtime.workflow_runs["main"] = live

    runtime.update_project(beta, description="renamed while Alpha runs")
    runtime.delete_project(beta)

    assert runtime.active_project is not None and runtime.active_project.id == alpha
    assert runtime.workflow_runs.get("main") is live


def test_activity_poll_sees_the_active_projects_live_run(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    """Idle culling must not stop a backend that is still executing (#2362)."""
    from scistudio.api.seam import workflow_runs_active

    alpha = _make_project(client, project_parent, "Alpha")
    runtime.open_project(alpha)
    runtime.workflow_runs["main"] = _fake_run(done=False)

    assert workflow_runs_active(client.app) is True  # type: ignore[arg-type]


def test_deleting_the_active_project_retires_its_runs(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    alpha = _make_project(client, project_parent, "Alpha")
    runtime.open_project(alpha)
    runtime.workflow_runs["main"] = _fake_run(done=True)

    runtime.delete_project(alpha)

    assert runtime.workflow_runs == {}


def test_opening_a_path_refused_for_live_runs_registers_nothing(
    client: TestClient, runtime: ApiRuntime, project_parent: Path, tmp_path: Path
) -> None:
    """Codex review on #2439: a refused open by path must not add the project to the registry."""
    from scistudio.api.runtime._runs import ProjectRunsLiveError

    alpha = _make_project(client, project_parent, "Alpha")
    runtime.open_project(alpha)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "project.yaml").write_text("project:\n  id: elsewhere\n  name: Elsewhere\n", encoding="utf-8")
    runtime.workflow_runs["main"] = _fake_run(done=False)
    registry_before = runtime.known_projects_path.read_text(encoding="utf-8")

    with pytest.raises(ProjectRunsLiveError):
        runtime.open_project(str(elsewhere))

    assert "elsewhere" not in runtime.known_projects
    assert runtime.known_projects_path.read_text(encoding="utf-8") == registry_before


def test_a_run_that_ignored_the_switch_keeps_its_workflow_id_reserved(
    client: TestClient, runtime: ApiRuntime, project_parent: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex review on #2439: worker handles are keyed by (workflow_id, block_id), so a run a
    switch could not stop keeps that workflow id from starting again, in any project, until it stops."""
    import asyncio

    from scistudio.api.runtime import _run_lifetime
    from scistudio.api.runtime._runs import WorkflowAlreadyRunningError, _is_workflow_running
    from scistudio.api.seam import workflow_runs_active

    monkeypatch.setattr(_run_lifetime, "_PROJECT_LEAVE_RUN_TIMEOUT_SEC", 0.3)
    monkeypatch.setattr(_run_lifetime, "_PROJECT_LEAVE_CANCEL_GRACE_SEC", 0.1)
    alpha = _make_project(client, project_parent, "Alpha")
    beta = _make_project(client, project_parent, "Beta")
    runtime.open_project(alpha)

    async def scenario() -> None:
        release = asyncio.Event()

        async def stubborn() -> None:
            while not release.is_set():
                try:
                    await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    continue

        task = asyncio.create_task(stubborn())
        run = WorkflowRun(
            scheduler=object(),  # type: ignore[arg-type]
            task=task,
            checkpoint_manager=object(),  # type: ignore[arg-type]
            run_id="run-stuck",
        )
        runtime.workflow_runs["main"] = run

        await runtime.end_project_runs()
        assert not task.done()
        assert "main" not in runtime.workflow_runs
        runtime.open_project(beta)

        assert _is_workflow_running(runtime, "main") is True
        assert _is_workflow_running(runtime, "other") is False
        with pytest.raises(WorkflowAlreadyRunningError):
            runtime.start_workflow("main")
        assert workflow_runs_active(client.app) is True  # type: ignore[arg-type]

        release.set()
        await asyncio.wait_for(task, timeout=5)
        await asyncio.sleep(0)
        assert _is_workflow_running(runtime, "main") is False
        assert runtime._stopping_runs == {}

    asyncio.run(scenario())
