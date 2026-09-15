"""#2433 — a run is identified by its run id across the API layer.

The 2026-09-15 identity audits reproduced, among others:

* outputs of a run that finished after a project switch registered against the
  next project (a relative Artifact path resolved under the wrong root);
* an interactive prompt of one run answering for a later run of the same
  workflow;
* an AI terminal started in one project still acting after the switch.

Each test here pins the fix for one of them.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scistudio.api.routes import ai_pty
from scistudio.api.runtime import ApiRuntime
from scistudio.api.runtime._stop_request import terminate_project_terminal_sessions
from scistudio.api.runtime.models import WorkflowRun
from scistudio.api.ws import _run_scope, serialise_event
from scistudio.blocks.base.state import BlockState
from scistudio.engine.events import BLOCK_DONE, INTERACTIVE_PROMPT, EngineEvent, EventBus
from scistudio.engine.run_logging import run_log_path
from scistudio.panels.targets import PanelError
from tests.api.helpers import build_linear_workflow, wait_for_workflow_completion
from tests.panels.conftest import make_runtime


class _DoneTask:
    def done(self) -> bool:
        return True


def _make_project(client: TestClient, parent: Path, name: str) -> dict[str, Any]:
    response = client.post("/api/projects/", json={"name": name, "description": "", "path": str(parent)})
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_a_started_run_reports_one_id_everywhere(client: TestClient, runtime: ApiRuntime, opened_project: Path) -> None:
    """The execute response, the registry, the lineage row and the run log share the run id."""
    payload = build_linear_workflow(opened_project, workflow_id="ident-flow")
    assert client.post("/api/workflows/", json=payload).status_code == 200

    started = client.post("/api/workflows/ident-flow/execute")
    assert started.status_code == 200
    run_id = started.json()["run_id"]
    assert run_id

    run = wait_for_workflow_completion(runtime, "ident-flow", timeout=60)
    assert run.run_id == run_id
    assert run.project_id == runtime.active_project.id
    assert runtime.find_run(run_id) is run
    assert runtime.find_run("ident-flow") is run
    assert runtime.lineage_store.get_run(run_id)["workflow_id"] == "ident-flow"
    assert run_log_path(run_id, project_root=opened_project).is_file()


def test_outputs_of_a_run_the_project_does_not_hold_are_not_registered(
    client: TestClient, runtime: ApiRuntime, project_parent: Path
) -> None:
    """Audit repro ``repro_detached_output_registration``, adapted."""
    import asyncio

    alpha = _make_project(client, project_parent, "Alpha")
    (Path(alpha["path"]) / "results").mkdir(exist_ok=True)
    (Path(alpha["path"]) / "results" / "plot.png").write_bytes(b"png")
    beta = _make_project(client, project_parent, "Beta")
    assert runtime.active_project.id == beta["id"]

    def artifact_output() -> dict[str, Any]:
        return {
            "figure": {
                "backend": None,
                "path": None,
                "format": None,
                "metadata": {"type_chain": ["DataObject", "Artifact"], "file_path": "results/plot.png"},
            }
        }

    stale = EngineEvent(
        event_type=BLOCK_DONE,
        block_id="render",
        data={"workflow_id": "main", "run_id": "run-of-alpha", "outputs": artifact_output()},
    )
    asyncio.run(runtime.event_bus.emit(stale))
    assert "data_ref" not in stale.data["outputs"]["figure"]
    assert runtime.data_catalog == {}

    runtime.workflow_runs["main"] = WorkflowRun(
        scheduler=object(),  # type: ignore[arg-type]
        task=_DoneTask(),  # type: ignore[arg-type]
        checkpoint_manager=object(),  # type: ignore[arg-type]
        run_id="run-of-beta",
    )
    current = EngineEvent(
        event_type=BLOCK_DONE,
        block_id="render",
        data={"workflow_id": "main", "run_id": "run-of-beta", "outputs": artifact_output()},
    )
    asyncio.run(runtime.event_bus.emit(current))
    assert current.data["outputs"]["figure"]["data_ref"] in runtime.data_catalog


def test_websocket_frames_and_requests_carry_the_run_id() -> None:
    event = EngineEvent(event_type=BLOCK_DONE, block_id="load", data={"workflow_id": "main", "run_id": "run-1"})
    frame = serialise_event(event)
    assert frame["run_id"] == "run-1"
    assert frame["workflow_id"] == "main"

    bus = EventBus()
    bus.runtime = SimpleNamespace(workflow_runs={"main": SimpleNamespace(run_id="run-live")})  # type: ignore[attr-defined]
    # A request naming only the workflow addresses the run the project holds.
    assert _run_scope(bus, {"workflow_id": "main"}) == {"workflow_id": "main", "run_id": "run-live"}
    # A request naming a run addresses exactly that run.
    assert _run_scope(bus, {"workflow_id": "main", "run_id": "run-old"}) == {"workflow_id": "main", "run_id": "run-old"}
    assert _run_scope(bus, {"workflow_id": "unknown"}) == {"workflow_id": "unknown"}


def test_a_prompt_of_an_earlier_run_is_not_waiting_for_the_current_run(tmp_path: Path) -> None:
    """Audit repro ``repro_panel_prompt_project_switch``, adapted to run identity."""
    runtime, store = make_runtime(tmp_path)
    future = SimpleNamespace(done=lambda: False)

    def hold(run_id: str) -> None:
        runtime.workflow_runs["wf"] = SimpleNamespace(
            run_id=run_id,
            scheduler=SimpleNamespace(
                _interactive_futures={"block": future}, _block_states={"block": BlockState.PAUSED}
            ),
        )

    def prompt(run_id: str) -> EngineEvent:
        return EngineEvent(
            event_type=INTERACTIVE_PROMPT,
            block_id="block",
            data={
                "workflow_id": "wf",
                "run_id": run_id,
                "panel_manifest": {"panel_id": "lab.text", "module_url": ""},
                "panel_payload": {"answer": 42},
            },
        )

    hold("run-1")
    store.on_event(prompt("run-1"))
    assert store._waiting("wf", "block")["run_id"] == "run-1"

    # A later run of the same workflow now holds the block; the old prompt is stale.
    hold("run-2")
    with pytest.raises(PanelError) as stale:
        store._waiting("wf", "block")
    assert stale.value.code == "not_waiting"

    # A terminal event of the old run does not drop the new run's prompt.
    store.on_event(prompt("run-2"))
    store.on_event(EngineEvent(event_type=BLOCK_DONE, block_id="block", data={"workflow_id": "wf", "run_id": "run-1"}))
    assert store._waiting("wf", "block")["run_id"] == "run-2"


class _FakePty:
    def __init__(self, cwd: Path) -> None:
        self._cwd = cwd
        self.killed = False

    def kill_tree(self) -> None:
        self.killed = True


def test_leaving_a_project_closes_only_its_terminals(
    client: TestClient, runtime: ApiRuntime, project_parent: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    alpha = _make_project(client, project_parent, "Alpha")
    beta_dir = project_parent / "beta-elsewhere"
    beta_dir.mkdir()
    chat = _FakePty(Path(alpha["path"]))
    ai_block = _FakePty(Path(alpha["path"]) / ".scistudio" / "ai-runs" / "r1")
    foreign = _FakePty(beta_dir)
    ptys = {"chat": chat, "ai-block": ai_block, "foreign": foreign}
    monkeypatch.setattr(ai_pty, "_active_ptys", ptys)
    monkeypatch.setattr(ai_pty, "_engine_tab_to_run", {"ai-block": "block-run-1"})
    monkeypatch.setattr(ai_pty, "_engine_run_to_run_dir", {"block-run-1": Path(alpha["path"])})

    assert terminate_project_terminal_sessions(Path(alpha["path"])) == 2
    for session in (chat, ai_block):
        _wait_until(lambda session=session: session.killed)
    assert list(ptys) == ["foreign"]
    assert not foreign.killed
    assert ai_pty._engine_tab_to_run == {}
    assert ai_pty._engine_run_to_run_dir == {}


def test_a_project_switch_closes_the_previous_projects_terminals(
    client: TestClient, runtime: ApiRuntime, project_parent: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    alpha = _make_project(client, project_parent, "Alpha")
    chat = _FakePty(Path(alpha["path"]))
    monkeypatch.setattr(ai_pty, "_active_ptys", {"chat": chat})

    # Re-opening the active project is not a switch.
    assert client.get(f"/api/projects/{alpha['id']}").status_code == 200
    assert "chat" in ai_pty._active_ptys

    _make_project(client, project_parent, "Beta")
    assert ai_pty._active_ptys == {}
    _wait_until(lambda: chat.killed)


def _wait_until(condition: Any, timeout: float = 5.0) -> None:
    import time

    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.01)
