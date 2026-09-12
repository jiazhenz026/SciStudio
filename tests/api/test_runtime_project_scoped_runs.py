"""#2362 — a run belongs to the project that started it.

``ApiRuntime.workflow_runs`` is keyed by workflow id and nothing else, and
``main`` is the default workflow name in every project. Nothing ever cleared the
registry on a project switch, so after opening a second project its ``main``
resolved the first project's run: ``get_run`` handed back the other project's
scheduler and storage paths, ``_is_workflow_running`` rejected a start with
"workflow is already running", and the MCP ``cancel_run`` tool terminated a live
execution in a project the caller had already left.

These tests fail against the pre-#2362 runtime.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime
from scistudio.api.runtime.models import WorkflowRun


class _FakeTask:
    """Stands in for a run's ``asyncio.Task``.

    The registry only reads ``done()``; the lifespan shutdown additionally
    cancels and awaits whatever ``all_workflow_runs`` hands it, which these
    tests deliberately exercise. Left un-dataclassed so it stays hashable —
    ``asyncio.gather`` requires that.
    """

    def __init__(self, *, done: bool) -> None:
        self._done = done

    def done(self) -> bool:
        return self._done

    def cancel(self) -> None:
        self._done = True

    def __await__(self):  # type: ignore[no-untyped-def]
        return iter(())


def _fake_run(*, done: bool) -> WorkflowRun:
    """A ``WorkflowRun`` stand-in; only ``task.done()`` is read by the registry."""
    return WorkflowRun(
        scheduler=object(),  # type: ignore[arg-type]
        task=_FakeTask(done=done),  # type: ignore[arg-type]
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


def test_a_live_run_survives_the_switch_but_is_no_longer_addressable(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    """It still has a worker to finish, and shutdown still has to cancel it."""
    alpha = _make_project(client, project_parent, "Alpha")
    beta = _make_project(client, project_parent, "Beta")

    runtime.open_project(alpha)
    live = _fake_run(done=False)
    runtime.workflow_runs["main"] = live

    runtime.open_project(beta)

    assert "main" not in runtime.workflow_runs
    assert live in runtime.all_workflow_runs()


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


def test_detach_drops_finished_runs_and_prunes_earlier_detached_ones(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    alpha = _make_project(client, project_parent, "Alpha")
    runtime.open_project(alpha)

    runtime.workflow_runs["done"] = _fake_run(done=True)
    live = _fake_run(done=False)
    runtime.workflow_runs["live"] = live
    runtime.detach_workflow_runs()

    assert runtime.all_workflow_runs() == [live]

    # Once it finishes, a later detach prunes it rather than accumulating.
    live.task.cancel()  # the worker finished
    runtime.detach_workflow_runs()
    assert runtime.all_workflow_runs() == []


def test_all_workflow_runs_covers_active_and_detached(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    alpha = _make_project(client, project_parent, "Alpha")
    beta = _make_project(client, project_parent, "Beta")

    runtime.open_project(alpha)
    from_alpha = _fake_run(done=False)
    runtime.workflow_runs["main"] = from_alpha

    runtime.open_project(beta)
    from_beta = _fake_run(done=False)
    runtime.workflow_runs["main"] = from_beta

    everything = runtime.all_workflow_runs()
    assert set(map(id, everything)) == {id(from_alpha), id(from_beta)}
    # Addressable by workflow id: only the active project's.
    assert runtime.workflow_runs["main"] is from_beta


def test_activity_poll_still_sees_a_detached_live_run(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    """Idle culling must not stop a backend that is still executing (#2362)."""
    from scistudio.api.seam import workflow_runs_active

    alpha = _make_project(client, project_parent, "Alpha")
    beta = _make_project(client, project_parent, "Beta")

    runtime.open_project(alpha)
    runtime.workflow_runs["main"] = _fake_run(done=False)
    runtime.open_project(beta)

    assert runtime.workflow_runs == {}
    assert workflow_runs_active(client.app) is True  # type: ignore[arg-type]


def test_gui_disconnect_sweep_still_sees_a_detached_live_run(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    from scistudio.api.ws import _every_workflow_run

    alpha = _make_project(client, project_parent, "Alpha")
    beta = _make_project(client, project_parent, "Beta")

    runtime.open_project(alpha)
    live = _fake_run(done=False)
    runtime.workflow_runs["main"] = live
    runtime.open_project(beta)

    assert live in _every_workflow_run(runtime)


def test_every_workflow_run_tolerates_a_runtime_without_the_accessor() -> None:
    """``api/ws`` duck-types the runtime; a stub must not break the sweep."""
    from scistudio.api.ws import _every_workflow_run

    class _Stub:
        workflow_runs: ClassVar[dict[str, Any]] = {"main": "run"}

    assert _every_workflow_run(_Stub()) == ["run"]
    assert _every_workflow_run(object()) == []


def test_deleting_the_active_project_retires_its_runs(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    alpha = _make_project(client, project_parent, "Alpha")
    runtime.open_project(alpha)
    runtime.workflow_runs["main"] = _fake_run(done=True)

    runtime.delete_project(alpha)

    assert runtime.workflow_runs == {}
