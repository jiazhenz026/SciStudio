"""#2362 — tutorial conditions ask about the workflow the reader is building.

``port_has_output`` and ``plot_rendered`` select on a node id and a port, and a
node id is not unique across a project — generated ids like ``load_data_1``
repeat in every workflow. Both halves of ``port_has_output`` (the scheduler's
in-memory outputs and the lineage store) scanned every workflow, and
``rendered_plots`` walked the whole preview cache, so a step about the workflow
the reader is building could be marked complete by a node of the same name in
one they had already finished.

These tests fail against the pre-#2362 product-state port.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scistudio.api.routes.tutorials import _ApiProductState, _RecordedSignals
from scistudio.api.runtime import ApiRuntime

NODE = "load_data_1"
PORT = "table"


class _StubScheduler:
    def __init__(self, block_outputs: dict[str, dict[str, Any]]) -> None:
        self._block_outputs = block_outputs


class _FinishedTask:
    """The lifespan shutdown sweeps every run; a finished one is left alone."""

    def done(self) -> bool:
        return True


class _StubRun:
    def __init__(self, block_outputs: dict[str, dict[str, Any]]) -> None:
        self.scheduler = _StubScheduler(block_outputs)
        self.task = _FinishedTask()


def _write_workflow(project: Path, workflow_id: str, *, declare_id: bool = True) -> None:
    wf_dir = project / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / f"{workflow_id}.yaml").write_text(
        "workflow:\n" + (f"  id: {workflow_id}\n" if declare_id else "") + "  version: 1.0.0\n"
        "  nodes:\n"
        f"  - id: {NODE}\n"
        "    block_type: load_data\n"
        "    config: {}\n"
        "  edges: []\n",
        encoding="utf-8",
    )


def _state(runtime: ApiRuntime) -> _ApiProductState:
    return _ApiProductState(
        runtime=runtime,
        recorded=_RecordedSignals(),
        project_dir=runtime.project_dir,
        tutorial_library_dir=None,
    )


@pytest.fixture()
def two_workflows(client: TestClient, runtime: ApiRuntime, project_parent: Path) -> Path:
    response = client.post(
        "/api/projects/",
        json={"name": "Tutorial", "description": "", "path": str(project_parent)},
    )
    assert response.status_code == 200, response.text
    project = Path(response.json()["path"])
    # The reader is building `current`; `finished` is one they completed earlier.
    _write_workflow(project, "current")
    _write_workflow(project, "finished")
    runtime.open_project(response.json()["id"])
    return project


def test_port_has_output_ignores_a_namesake_in_another_workflow(runtime: ApiRuntime, two_workflows: Path) -> None:
    runtime.active_workflow_id = "current"
    runtime.workflow_runs["finished"] = _StubRun({NODE: {PORT: {"path": "/tmp/x.parquet"}}})

    assert _state(runtime).port_has_output(NODE, PORT) is False


def test_port_has_output_sees_the_readers_own_workflow(runtime: ApiRuntime, two_workflows: Path) -> None:
    runtime.active_workflow_id = "current"
    runtime.workflow_runs["current"] = _StubRun({NODE: {PORT: {"path": "/tmp/x.parquet"}}})

    assert _state(runtime).port_has_output(NODE, PORT) is True


def test_rendered_plots_only_reports_the_readers_own_workflow(runtime: ApiRuntime, two_workflows: Path) -> None:
    previews = two_workflows / ".scistudio" / "previews"
    for workflow_id in ("current", "finished"):
        plot_dir = previews / workflow_id / NODE / PORT / f"{workflow_id}_plot"
        plot_dir.mkdir(parents=True, exist_ok=True)
        (plot_dir / "current.svg").write_text("<svg/>", encoding="utf-8")
        (plot_dir / "current.json").write_text("{}", encoding="utf-8")

    runtime.active_workflow_id = "current"
    rendered = _state(runtime).rendered_plots()

    assert rendered == (("current", NODE, PORT, "current_plot"),)


def test_rendered_plots_still_ignores_a_record_with_no_figure(runtime: ApiRuntime, two_workflows: Path) -> None:
    """A run that produced nothing is not a rendered figure (unchanged)."""
    plot_dir = two_workflows / ".scistudio" / "previews" / "current" / NODE / PORT / "attempted"
    plot_dir.mkdir(parents=True, exist_ok=True)
    (plot_dir / "current.json").write_text("{}", encoding="utf-8")

    runtime.active_workflow_id = "current"
    assert _state(runtime).rendered_plots() == ()


def test_a_workflow_without_an_id_is_scoped_by_its_filename(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    """``WorkflowDefinition.id`` defaults to ``""``; runs and previews then use the filename stem."""
    response = client.post(
        "/api/projects/",
        json={"name": "Tutorial", "description": "", "path": str(project_parent)},
    )
    assert response.status_code == 200, response.text
    project = Path(response.json()["path"])
    _write_workflow(project, "untitled", declare_id=False)
    runtime.open_project(response.json()["id"])
    runtime.active_workflow_id = "untitled"
    assert runtime.load_workflow("untitled").id == ""

    runtime.workflow_runs["untitled"] = _StubRun({NODE: {PORT: {"path": "/tmp/x.parquet"}}})
    plot_dir = project / ".scistudio" / "previews" / "untitled" / NODE / PORT / "plot"
    plot_dir.mkdir(parents=True, exist_ok=True)
    (plot_dir / "current.svg").write_text("<svg/>", encoding="utf-8")

    state = _state(runtime)
    assert state.port_has_output(NODE, PORT) is True
    assert state.rendered_plots() == (("untitled", NODE, PORT, "plot"),)
