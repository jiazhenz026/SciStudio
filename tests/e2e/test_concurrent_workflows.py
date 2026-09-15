"""Concurrent runs of different workflows must not share state (#2472).

Every scenario here starts real runs on a real ``scistudio serve`` and checks
what a user sees for each run: its lineage record, its events, its log, its
outputs on disk, its previews and plots, and its interactive prompt. The
expectations are the concurrency rules the owner set:

- different workflows may run at the same time; the same workflow may not run
  twice at once, and the second start is refused;
- switching project, once confirmed, ends every run of the project being left;
- run from here refuses, naming each upstream block, when an upstream output is
  missing or stale, and never backfills it from somewhere else;
- an AI block's default outputs live under ``data/ai_outputs/<workflow>/<block>/``.

The workflows are built from small project blocks written by this module, and
they all use the same node ids (``src``, ``hold``, ``save``), so anything keyed
by the node id alone would collide. The ``e2e_barrier`` block waits for a gate
file the test creates: that is how a run is made slow, so the order of events
is set by the test and never by a sleep.
"""

from __future__ import annotations

import csv
import re
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import psutil
import pytest

from tests.e2e.harness import Backend, EventStream, Project, ServeProcess, requires_e2e

pytestmark = [requires_e2e, pytest.mark.timeout(300)]

# ---------------------------------------------------------------------------
# Project blocks
# ---------------------------------------------------------------------------

EMIT_MARKER_BLOCK = '''"""Emit a one-row table naming the marker and the run context it was made in."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

import pyarrow as pa

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import Collection, DataFrame

logger = logging.getLogger(__name__)


class EmitMarkerBlock(ProcessBlock):
    """A source block: one row carrying ``marker`` and the workflow and run it ran in."""

    name: ClassVar[str] = "E2E Emit Marker"
    type_name: ClassVar[str] = "e2e_emit_marker"
    description: ClassVar[str] = "Emit a one-row marker table."
    input_ports: ClassVar[list[InputPort]] = []
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="table", accepted_types=[DataFrame], description="The marker row"),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"marker": {"type": "string", "default": "unset", "description": "Marker text."}},
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        marker = str(config.get("marker", "unset"))
        logger.warning("e2e-marker emitted <%s>", marker)
        table = pa.table(
            {
                "marker": [marker],
                "made_in_workflow": [str(config.get("workflow_id"))],
                "made_in_run": [str(config.get("run_id"))],
            }
        )
        return {"table": Collection(items=[DataFrame(data=table)], item_type=DataFrame)}
'''

BARRIER_BLOCK = '''"""Hold a table until the test opens this block's gate, then pass it on stamped."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, ClassVar

import pyarrow as pa

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import DataFrame


class BarrierBlock(ProcessBlock):
    """Write ``gates/<gate>.entered``, wait for ``gates/<gate>.open``, stamp the table, pass it on."""

    name: ClassVar[str] = "E2E Barrier"
    type_name: ClassVar[str] = "e2e_barrier"
    description: ClassVar[str] = "Wait for a gate file, then pass the table through."
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="table", accepted_types=[DataFrame], description="Table to hold"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="table", accepted_types=[DataFrame], description="The same table, stamped"),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"gate": {"type": "string", "default": "none", "description": "Gate file stem."}},
    }

    def process_item(self, item: DataFrame, config: BlockConfig, state: Any = None) -> DataFrame:
        gates = Path(str(config.get("project_dir"))) / "gates"
        gates.mkdir(parents=True, exist_ok=True)
        gate = str(config.get("gate", "none"))
        (gates / f"{gate}.pid").write_text(str(os.getpid()), encoding="utf-8")
        (gates / f"{gate}.entered").write_text(str(config.get("run_id")), encoding="utf-8")
        deadline = time.monotonic() + 240
        while not (gates / f"{gate}.open").exists():
            if time.monotonic() > deadline:
                raise TimeoutError(f"gate {gate} was never opened")
            time.sleep(0.05)
        table = item.to_memory()
        stamp = f"{config.get('workflow_id')}/{config.get('run_id')}/{config.get('block_id')}"
        table = table.append_column("held_by", pa.array([stamp] * table.num_rows))
        return DataFrame(data=table)
'''

CONFIRM_BLOCK = '''"""An interactive block: show the markers, wait for a decision, record it."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pyarrow as pa

from scistudio.blocks.base import (
    BlockConfig,
    ExecutionMode,
    InputPort,
    InteractiveMixin,
    InteractivePrompt,
    OutputPort,
    PanelManifest,
)
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import Collection, DataFrame


class ConfirmMarkerBlock(InteractiveMixin, ProcessBlock):
    """Pause with the markers on screen; output them with the decision the person sent."""

    name: ClassVar[str] = "E2E Confirm Marker"
    type_name: ClassVar[str] = "e2e_confirm_marker"
    description: ClassVar[str] = "Ask a person to confirm the marker."
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(
        panel_id="e2e.confirm_marker",
        module_url="/api/blocks/panels/e2e.confirm_marker/panel.mjs",
        version="1",
        asset_root=str(Path(__file__).resolve().parent / "e2e_confirm_marker_panel"),
    )
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="table", accepted_types=[DataFrame], description="Marker table"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="table", accepted_types=[DataFrame], description="Markers with the decision"),
    ]

    def _markers(self, inputs: dict[str, Any]) -> list[str]:
        value = inputs["table"]
        items = list(value) if isinstance(value, Collection) else [value]
        return [str(marker) for item in items for marker in item.to_memory().column("marker").to_pylist()]

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        return InteractivePrompt(panel_payload={"markers": self._markers(inputs)})

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        response = config.get("interactive_response", {}) or {}
        markers = self._markers(inputs)
        table = pa.table({"marker": markers, "decision": [str(response.get("decision"))] * len(markers)})
        return {"table": Collection(items=[DataFrame(data=table)], item_type=DataFrame)}
'''

CONFIRM_PANEL = "export default function mount(root) { root.textContent = 'confirm'; }\n"

#: A real AI block whose agent is a stand-in: instead of opening a terminal, the
#: "agent" reads the manifest the block wrote, the way a real agent is told to,
#: and writes the marker to every expected output path. Everything else, from the
#: default output path to reuse and loading the result, is the product's code.
FAKE_AGENT_BLOCK = '''"""An AI block whose agent is replaced by a function that follows the manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import scistudio.engine.pty_control as pty_control
from scistudio.blocks.ai.ai_block import AIBlock
from scistudio.blocks.base import BlockConfig


class FakeAgentBlock(AIBlock):
    """AI Agent block with a scripted agent that writes ``marker`` to each declared output."""

    name: ClassVar[str] = "E2E Fake Agent"
    type_name: ClassVar[str] = "e2e_fake_agent"
    description: ClassVar[str] = "AI block whose agent writes a marker table."

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        project = Path(str(config.get("project_dir")))
        gates = project / "gates"
        gates.mkdir(parents=True, exist_ok=True)
        label = f"{config.get('workflow_id')}-{config.get('block_id')}"
        marker = str(config.get("marker", "unset"))

        def scripted_agent(spec: Any) -> str:
            manifest = json.loads((Path(spec.run_dir_path) / "manifest.json").read_text(encoding="utf-8"))
            (gates / f"{label}.invoked").write_text(str(config.get("run_id")), encoding="utf-8")
            for port, output in manifest["outputs"].items():
                target = Path(output["expected_path"])
                if not target.is_absolute():
                    target = project / target
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f"marker\\n{marker}\\n", encoding="utf-8")
                (gates / f"{label}.{port}.path").write_text(str(target.resolve()), encoding="utf-8")
            return "scripted-agent"

        pty_control.request_pty_tab = scripted_agent
        pty_control.notify_block_pty_event = lambda *args, **kwargs: None
        return super().run(inputs, config)
'''

#: A plot render script that writes what it was given into the SVG as text.
MARKER_PLOT = '''"""Render the markers and run ids of the bound output as the figure title."""

from __future__ import annotations


def render(collection):
    import matplotlib

    matplotlib.rcParams["svg.fonttype"] = "none"
    import matplotlib.pyplot as plt

    frames = collection.items.open()
    markers = [str(value) for frame in frames for value in frame["marker"]]
    runs = [str(value) for frame in frames for value in frame["made_in_run"]]
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_title("markers=[" + ",".join(markers) + "] runs=[" + ",".join(runs) + "]")
    return fig
'''


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_project(backend: Backend, parent: Path, name: str) -> Project:
    """Create a project holding this module's blocks and make it the active one."""
    created = backend.create_project(name, parent)
    project = Project(id=str(created["id"]), path=Path(created["path"]))
    blocks = project.path / "blocks"
    blocks.mkdir(parents=True, exist_ok=True)
    (blocks / "e2e_emit_marker.py").write_text(EMIT_MARKER_BLOCK, encoding="utf-8")
    (blocks / "e2e_barrier.py").write_text(BARRIER_BLOCK, encoding="utf-8")
    (blocks / "e2e_confirm_marker.py").write_text(CONFIRM_BLOCK, encoding="utf-8")
    (blocks / "e2e_fake_agent.py").write_text(FAKE_AGENT_BLOCK, encoding="utf-8")
    panel = blocks / "e2e_confirm_marker_panel"
    panel.mkdir(exist_ok=True)
    (panel / "panel.mjs").write_text(CONFIRM_PANEL, encoding="utf-8")
    backend.reload_registries()
    return project


def node(node_id: str, block_type: str, x: int, **params: Any) -> dict[str, Any]:
    return {"id": node_id, "block_type": block_type, "config": {"params": params}, "layout": {"x": x, "y": 200}}


def marker_workflow(
    workflow_id: str, marker: str, *, gate: str | None = None, interactive: bool = False
) -> dict[str, Any]:
    """``src`` -> ``hold`` -> ``save``, with the same node ids in every workflow.

    ``hold`` is a gate named ``gate`` (default ``<workflow>-<marker>``), or the
    interactive confirm block when ``interactive`` is set.
    """
    if interactive:
        hold = node("hold", "e2e_confirm_marker", 380)
    else:
        hold = node("hold", "e2e_barrier", 380, gate=gate or f"{workflow_id}-{marker}")
    return {
        "id": workflow_id,
        "version": "1.0.0",
        "description": f"Emit marker {marker}, hold it, and save it.",
        "nodes": [
            node("src", "e2e_emit_marker", 80, marker=marker),
            hold,
            node(
                "save",
                "save_data",
                680,
                core_type="DataFrame",
                path="data/processed",
                filename=f"{workflow_id}.csv",
                overwrite=True,
            ),
        ],
        "edges": [
            {"source": "src:table", "target": "hold:table"},
            {"source": "hold:table", "target": "save:data"},
        ],
    }


def agent_workflow(workflow_id: str, marker: str) -> dict[str, Any]:
    """One AI block ``ai`` with a ``summary`` table output on its default path, reusing its last output."""
    ai = node(
        "ai",
        "e2e_fake_agent",
        80,
        user_prompt="Write the marker table.",
        marker=marker,
        reuse_last_output=True,
        output_ports=[{"name": "summary", "types": ["DataFrame"]}],
    )
    return {
        "id": workflow_id,
        "version": "1.0.0",
        "description": "Ask the agent for a marker.",
        "nodes": [ai],
        "edges": [],
    }


class Gates:
    """The files an ``e2e_barrier`` block and the scripted agent write and wait on."""

    def __init__(self, project: Project) -> None:
        self.dir = project.path / "gates"
        self.dir.mkdir(parents=True, exist_ok=True)

    def entered(self, gate: str, timeout: float = 120.0) -> str:
        """Wait until a block is inside the gate's wait; return the run id it wrote."""
        path = self.dir / f"{gate}.entered"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.is_file() and (text := path.read_text(encoding="utf-8")):
                return text
            time.sleep(0.05)
        raise AssertionError(f"no block reached gate {gate!r} within {timeout:.0f}s")

    def open(self, gate: str) -> None:
        (self.dir / f"{gate}.open").touch()

    def read(self, name: str) -> str | None:
        path = self.dir / name
        return path.read_text(encoding="utf-8") if path.is_file() else None


def start(backend: Backend, workflow_id: str) -> str:
    started = backend.call("POST", f"/api/workflows/{workflow_id}/execute")
    assert started["status"] == "started", started
    assert started["workflow_id"] == workflow_id, started
    return str(started["run_id"])


def terminations(record: dict[str, Any]) -> dict[str, str]:
    return {be["block_id"]: be["termination"] for be in record["block_executions"]}


def recorded_runs(backend: Backend, workflow_id: str) -> list[str]:
    return sorted(backend.run_ids(workflow_id))


def live_runs(backend: Backend) -> dict[str, str]:
    """``{workflow_id: run_id}`` of every run the active project still has going."""
    return {row["workflow_id"]: row["run_id"] for row in backend.call("GET", "/api/projects/active/runs")["runs"]}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def find_event(
    events: EventStream, predicate: Callable[[dict[str, Any]], bool], what: str, timeout: float = 180.0
) -> dict[str, Any]:
    """The first GUI message, already received or still to come, that matches."""
    for message in events.seen:
        if predicate(message):
            return message
    return events.wait_for(predicate, what=what, timeout=timeout)


def run_event(events: EventStream, run_id: str, event_type: str, block_id: str | None = None) -> dict[str, Any]:
    return find_event(
        events,
        lambda m: (
            m.get("type") == event_type
            and m.get("run_id") == run_id
            and (block_id is None or m.get("block_id") == block_id)
        ),
        what=f"{event_type} {block_id or ''} of run {run_id}",
    )


def drain(events: EventStream) -> None:
    """Receive everything the server has sent so far: send a ping, wait for its pong."""
    events.send({"type": "ping"})
    events.wait_for(lambda m: m.get("type") == "pong", what="pong", timeout=30)


def output_ref(done: dict[str, Any], port: str = "table") -> str:
    payload = done["data"]["outputs"][port]
    if payload.get("kind") == "collection":
        assert payload["count"] == 1, payload
        return str(payload["items"][0]["data_ref"])
    return str(payload["data_ref"])


def preview_rows(backend: Backend, ref: str) -> list[dict[str, Any]]:
    """The rows a preview of ``ref`` shows, read through the table panel the GUI mounts."""
    envelope = backend.open_preview(ref)
    assert envelope["kind"] == "panel", envelope
    context = backend.open_panel(ref)
    page = backend.panel_read(context, ref, "table.page", {"page": 1, "page_size": 50})
    names = [column["name"] if isinstance(column, dict) else str(column) for column in page["columns"]]
    return [dict(zip(names, row, strict=True)) if isinstance(row, list) else dict(row) for row in page["rows"]]


def run_log(serve: ServeProcess, project: Project, run_id: str) -> str:
    for directory in (serve.home / "logs", project.path / ".scistudio" / "logs"):
        path = directory / f"run-{run_id}.log"
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")
    raise AssertionError(f"no run log for run {run_id}")


def cancel(events: EventStream, workflow_id: str) -> None:
    events.send({"type": "cancel_workflow", "workflow_id": workflow_id})


def end_all_runs(backend: Backend) -> None:
    """Leave the server with no live run, so the next test can open its own project."""
    active = backend.call("GET", "/api/projects/active/runs")
    if active["runs"] and active["project_id"]:
        backend.call("POST", "/api/projects/active/end-runs", json={"project_id": active["project_id"]})


@pytest.fixture(autouse=True)
def no_runs_left_behind(backend: Backend) -> Iterator[None]:
    end_all_runs(backend)
    yield
    end_all_runs(backend)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def test_three_workflows_with_the_same_node_ids_run_together_and_keep_their_own_state(
    backend: Backend, events: EventStream, projects_dir: Path, serve: ServeProcess
) -> None:
    """Lineage, outputs, run state, events, logs and previews stay with the run that made them."""
    project = make_project(backend, projects_dir, "three-at-once")
    gates = Gates(project)
    markers = {"alpha": "A", "beta": "B", "gamma": "C"}
    for workflow_id, marker in markers.items():
        backend.put_workflow(marker_workflow(workflow_id, marker))

    runs = {workflow_id: start(backend, workflow_id) for workflow_id in markers}
    assert len(set(runs.values())) == 3, runs
    # All three are inside their ``hold`` block at the same time.
    for workflow_id, marker in markers.items():
        assert gates.entered(f"{workflow_id}-{marker}") == runs[workflow_id]
    assert live_runs(backend) == runs

    # Finish them in the reverse of the order they started.
    records: dict[str, dict[str, Any]] = {}
    for workflow_id in ("gamma", "alpha", "beta"):
        gates.open(f"{workflow_id}-{markers[workflow_id]}")
        records[workflow_id] = backend.wait_for_run(runs[workflow_id])
    drain(events)

    object_ids: dict[str, set[str]] = {}
    for workflow_id, marker in markers.items():
        run_id = runs[workflow_id]
        record = records[workflow_id]
        others = {other: value for other, value in runs.items() if other != workflow_id}

        # Lineage: the record, every block execution in it, and every object it names belong to this run.
        assert record["run"]["run_id"] == run_id
        assert record["run"]["workflow_id"] == workflow_id
        assert record["run"]["status"] == "completed", record["run"]
        assert terminations(record) == {"src": "completed", "hold": "completed", "save": "completed"}
        assert {be["run_id"] for be in record["block_executions"]} == {run_id}
        executions = {be["block_execution_id"] for be in record["block_executions"]}
        object_ids[workflow_id] = set()
        for be in record["block_executions"]:
            for entry in be["inputs"]:
                assert entry["produced_by_execution"] in executions, (workflow_id, be["block_id"], entry)
            for entry in be["outputs"]:
                object_ids[workflow_id].add(entry["object_id"])
                assert entry["produced_by_execution"] == be["block_execution_id"]
                storage = Path(entry["storage_path"]).resolve()
                # Outputs are filed under the workflow that produced them.
                assert storage.is_relative_to((project.path / "data" / "zarr" / workflow_id).resolve()), entry
        assert recorded_runs(backend, workflow_id) == [run_id]

        # Events: everything stamped with this run names this workflow, and covers exactly its blocks.
        mine = [m for m in events.seen if m.get("run_id") == run_id]
        assert {m["workflow_id"] for m in mine} == {workflow_id}
        done = {m["block_id"] for m in mine if m["type"] == "block_done"}
        assert done == {"src", "hold", "save"}
        assert [m["type"] for m in mine].count("workflow_completed") == 1
        for m in mine:
            if isinstance(m.get("data"), dict) and isinstance(m["data"].get("config"), dict):
                assert m["data"]["config"]["run_id"] == run_id, m["type"]
                assert m["data"]["config"]["workflow_id"] == workflow_id, m["type"]

        # Preview of the held output shows this run's row, made and held in this run.
        rows = preview_rows(backend, output_ref(run_event(events, run_id, "block_done", "hold")))
        assert rows == [
            {
                "marker": marker,
                "made_in_workflow": workflow_id,
                "made_in_run": run_id,
                "held_by": f"{workflow_id}/{run_id}/hold",
            }
        ]

        # The file the workflow saved holds this run's row.
        saved = read_csv(project.path / "data" / "processed" / f"{workflow_id}.csv")
        assert [(row["marker"], row["made_in_run"], row["held_by"]) for row in saved] == [
            (marker, run_id, f"{workflow_id}/{run_id}/hold")
        ]

        # The run's log is this run's alone.
        log = run_log(serve, project, run_id)
        assert f"e2e-marker emitted <{marker}>" in log
        for other, other_run in others.items():
            assert f"e2e-marker emitted <{markers[other]}>" not in log, other
            assert other_run not in log, other

    assert not (object_ids["alpha"] & object_ids["beta"] or object_ids["alpha"] & object_ids["gamma"])
    assert not object_ids["beta"] & object_ids["gamma"]
    assert live_runs(backend) == {}


def test_cancelling_one_run_leaves_the_fast_and_the_slow_runs_beside_it_untouched(
    backend: Backend, events: EventStream, projects_dir: Path
) -> None:
    """A fast run finishes past two slow ones; cancelling one slow run changes neither of the others."""
    project = make_project(backend, projects_dir, "fast-slow-cancel")
    gates = Gates(project)
    backend.put_workflow(marker_workflow("slow_a", "A"))
    backend.put_workflow(marker_workflow("fast_b", "B"))
    backend.put_workflow(marker_workflow("slow_c", "C"))
    gates.open("fast_b-B")

    run_a = start(backend, "slow_a")
    run_c = start(backend, "slow_c")
    gates.entered("slow_a-A")
    gates.entered("slow_c-C")
    run_b = start(backend, "fast_b")
    record_b = backend.wait_for_run(run_b)
    assert record_b["run"]["status"] == "completed", record_b["run"]
    assert live_runs(backend) == {"slow_a": run_a, "slow_c": run_c}
    assert backend.run(run_a)["run"]["status"] == "running"
    assert backend.run(run_c)["run"]["status"] == "running"

    cancel(events, "slow_a")
    record_a = backend.wait_for_run(run_a)
    assert record_a["run"]["status"] == "cancelled", record_a["run"]
    drain(events)

    # The other slow run is still going, and nothing about the cancel reached it.
    assert live_runs(backend) == {"slow_c": run_c}
    assert backend.run(run_c)["run"]["status"] == "running"
    run_c_types = {m["type"] for m in events.seen if m.get("run_id") == run_c}
    assert not run_c_types & {"block_cancelled", "block_skipped", "workflow_completed", "cancel_workflow_request"}
    # The finished fast run is exactly as it was.
    assert backend.run(run_b) == record_b

    gates.open("slow_c-C")
    record_c = backend.wait_for_run(run_c)
    assert record_c["run"]["status"] == "completed", record_c["run"]
    assert terminations(record_c) == {"src": "completed", "hold": "completed", "save": "completed"}
    rows = preview_rows(backend, output_ref(run_event(events, run_c, "block_done", "hold")))
    assert [(row["marker"], row["made_in_run"]) for row in rows] == [("C", run_c)]
    assert read_csv(project.path / "data" / "processed" / "slow_c.csv")[0]["marker"] == "C"

    # The cancelled run saved nothing, and the fast run's file is its own.
    assert terminations(backend.run(run_a)).get("save") != "completed"
    assert not (project.path / "data" / "processed" / "slow_a.csv").exists()
    assert read_csv(project.path / "data" / "processed" / "fast_b.csv")[0]["made_in_run"] == run_b
    assert backend.run(run_b) == record_b


def test_the_same_workflow_cannot_start_twice_while_a_different_one_can(
    backend: Backend, events: EventStream, projects_dir: Path
) -> None:
    """A second start of a running workflow is refused and records nothing; another workflow starts."""
    project = make_project(backend, projects_dir, "start-twice")
    gates = Gates(project)
    backend.put_workflow(marker_workflow("alpha", "A"))
    backend.put_workflow(marker_workflow("beta", "B"))
    gates.open("beta-B")

    run_a = start(backend, "alpha")
    gates.entered("alpha-A")

    again = backend.http.post("/api/workflows/alpha/execute")
    assert again.status_code == 409, again.text
    from_here = backend.http.post("/api/workflows/alpha/execute-from", json={"block_id": "hold"})
    assert from_here.status_code == 409, from_here.text

    run_b = start(backend, "beta")
    assert backend.wait_for_run(run_b)["run"]["status"] == "completed"
    assert live_runs(backend) == {"alpha": run_a}
    assert recorded_runs(backend, "alpha") == [run_a]

    gates.open("alpha-A")
    record_a = backend.wait_for_run(run_a)
    assert record_a["run"]["status"] == "completed", record_a["run"]
    drain(events)
    started = {
        m["run_id"] for m in events.seen if m.get("type") == "workflow_started" and m.get("workflow_id") == "alpha"
    }
    assert started == {run_a}
    assert recorded_runs(backend, "alpha") == [run_a]
    assert read_csv(project.path / "data" / "processed" / "alpha.csv")[0]["made_in_run"] == run_a


def test_run_from_here_uses_only_its_own_workflows_upstream_while_another_workflow_runs(
    backend: Backend, events: EventStream, projects_dir: Path
) -> None:
    """Run from here reuses its own earlier output, and refuses rather than borrow a twin workflow's."""
    project = make_project(backend, projects_dir, "run-from-here")
    gates = Gates(project)
    shared_gate = "open-for-alpha-and-twin"
    backend.put_workflow(marker_workflow("alpha", "A", gate=shared_gate))
    # ``twin`` is alpha node for node, config for config; it has simply never run.
    backend.put_workflow(marker_workflow("twin", "A", gate=shared_gate))
    backend.put_workflow(marker_workflow("beta", "B"))
    gates.open(shared_gate)

    first_a = start(backend, "alpha")
    assert backend.wait_for_run(first_a)["run"]["status"] == "completed"

    run_b = start(backend, "beta")
    gates.entered("beta-B")

    # The twin has no output of its own to reuse, whatever alpha and beta produced under the same node ids.
    refused = backend.http.post("/api/workflows/twin/execute-from", json={"block_id": "hold"})
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["error"] == "run_from_here_unmet", detail
    assert [item["node_id"] for item in detail["unmet"]] == ["src"], detail
    assert all(item["reason"] and item["detail"] for item in detail["unmet"]), detail
    assert recorded_runs(backend, "twin") == []

    # Alpha reuses its own ``src`` output from its own earlier run.
    resumed = backend.call("POST", "/api/workflows/alpha/execute-from", json={"block_id": "hold"})
    assert resumed["status"] == "started", resumed
    assert resumed["reused_blocks"] == ["src"], resumed
    second_a = str(resumed["run_id"])
    record = backend.wait_for_run(second_a)
    assert record["run"]["status"] == "completed", record["run"]
    assert record["run"]["workflow_id"] == "alpha"
    assert record["run"]["parent_run_id"] == first_a
    assert record["run"]["execute_from_block_id"] == "hold"
    rows = preview_rows(backend, output_ref(run_event(events, second_a, "block_done", "hold")))
    assert rows == [
        {"marker": "A", "made_in_workflow": "alpha", "made_in_run": first_a, "held_by": f"alpha/{second_a}/hold"}
    ]

    # Beta ran through all of it untouched.
    assert live_runs(backend) == {"beta": run_b}
    gates.open("beta-B")
    record_b = backend.wait_for_run(run_b)
    assert record_b["run"]["status"] == "completed"
    assert record_b["run"]["parent_run_id"] is None
    rows_b = preview_rows(backend, output_ref(run_event(events, run_b, "block_done", "hold")))
    assert [(row["marker"], row["made_in_run"]) for row in rows_b] == [("B", run_b)]

    # A changed upstream definition makes alpha's own output stale: refused, naming the block.
    backend.put_workflow(marker_workflow("alpha", "A-changed", gate=shared_gate))
    stale = backend.http.post("/api/workflows/alpha/execute-from", json={"block_id": "hold"})
    assert stale.status_code == 409, stale.text
    assert [item["node_id"] for item in stale.json()["detail"]["unmet"]] == ["src"], stale.text
    assert recorded_runs(backend, "alpha") == sorted([first_a, second_a])


def test_a_prompt_waiting_in_one_workflow_is_answered_only_by_that_workflow(
    backend: Backend, events: EventStream, projects_dir: Path
) -> None:
    """An interactive block waits in one workflow while another with the same node ids completes."""
    project = make_project(backend, projects_dir, "prompt-scope")
    gates = Gates(project)
    backend.put_workflow(marker_workflow("asks", "A", interactive=True))
    backend.put_workflow(marker_workflow("flows", "B"))
    gates.open("flows-B")

    run_a = start(backend, "asks")
    prompt = run_event(events, run_a, "interactive_prompt", "hold")
    assert prompt["workflow_id"] == "asks"
    assert prompt["data"]["panel_payload"] == {"markers": ["A"]}

    run_b = start(backend, "flows")
    record_b = backend.wait_for_run(run_b)
    assert record_b["run"]["status"] == "completed", record_b["run"]
    drain(events)
    prompts = [m for m in events.seen if m.get("type") == "interactive_prompt"]
    assert [(m["workflow_id"], m["run_id"], m["block_id"]) for m in prompts] == [("asks", run_a, "hold")]
    assert live_runs(backend) == {"asks": run_a}
    assert backend.run(run_a)["run"]["status"] == "running"

    # A decision addressed to the other workflow's node of the same id does not answer this prompt.
    events.send(
        {"type": "interactive_complete", "workflow_id": "flows", "block_id": "hold", "data": {"decision": "from-flows"}}
    )
    drain(events)
    events.send(
        {"type": "interactive_complete", "workflow_id": "asks", "block_id": "hold", "data": {"decision": "from-asks"}}
    )
    record_a = backend.wait_for_run(run_a)
    assert record_a["run"]["status"] == "completed", record_a["run"]

    rows = preview_rows(backend, output_ref(run_event(events, run_a, "block_done", "hold")))
    assert rows == [{"marker": "A", "decision": "from-asks"}]
    assert read_csv(project.path / "data" / "processed" / "asks.csv") == [{"marker": "A", "decision": "from-asks"}]
    # The completed workflow was not touched by either decision.
    assert backend.run(run_b) == record_b
    saved_b = read_csv(project.path / "data" / "processed" / "flows.csv")
    assert [(row["marker"], row["made_in_run"]) for row in saved_b] == [("B", run_b)]
    assert "decision" not in saved_b[0]


def test_switching_project_ends_every_run_and_nothing_reaches_the_new_project(
    backend: Backend, events: EventStream, projects_dir: Path
) -> None:
    """Runs in flight block a switch until ended; once ended, nothing of them shows up in the next project."""
    first = make_project(backend, projects_dir, "leaving")
    gates = Gates(first)
    backend.put_workflow(marker_workflow("alpha", "A"))
    backend.put_workflow(marker_workflow("beta", "B", interactive=True))

    run_a = start(backend, "alpha")
    run_b = start(backend, "beta")
    gates.entered("alpha-A")
    run_event(events, run_b, "interactive_prompt", "hold")
    drain(events)
    worker = int(str(gates.read("alpha-A.pid")))
    assert psutil.pid_exists(worker)
    assert live_runs(backend) == {"alpha": run_a, "beta": run_b}

    # Leaving is refused while the runs are live, and names them.
    refused = backend.http.post(
        "/api/projects/", json={"name": "arriving", "description": "headless e2e", "path": str(projects_dir)}
    )
    assert refused.status_code == 409, refused.text
    assert sorted(refused.json()["detail"]["run_ids"]) == sorted([run_a, run_b])

    # The user confirms: both runs end, and are recorded as cancelled.
    ended = backend.call(
        "POST", "/api/projects/active/end-runs", json={"project_id": first.id, "run_ids": [run_a, run_b]}
    )
    assert sorted(ended["ended_run_ids"]) == sorted([run_a, run_b])
    assert backend.run(run_a)["run"]["status"] == "cancelled"
    assert backend.run(run_b)["run"]["status"] == "cancelled"
    drain(events)
    after_switch = len(events.seen)
    # The worker that was holding alpha is gone, so nothing of that run can write anything any more.
    assert not psutil.pid_exists(worker) or psutil.Process(worker).status() == psutil.STATUS_ZOMBIE

    second = make_project(backend, projects_dir, "arriving")
    backend.put_workflow(marker_workflow("alpha", "A"))
    backend.put_workflow(marker_workflow("beta", "B", interactive=True))
    # What would have let the old runs continue now arrives: the gate opens, a decision is sent.
    gates.open("alpha-A")
    events.send(
        {"type": "interactive_complete", "workflow_id": "beta", "block_id": "hold", "data": {"decision": "late"}}
    )
    drain(events)

    assert live_runs(backend) == {}
    assert recorded_runs(backend, "alpha") == []
    assert recorded_runs(backend, "beta") == []
    # The old prompt is not shown in the new project.
    waiting = backend.http.post(
        "/api/panels/contexts",
        json={"kind": "interactive", "workflow_id": "beta", "block_id": "hold", "panel_id": "e2e.confirm_marker"},
    )
    assert waiting.status_code >= 400, waiting.text
    late = [
        m
        for m in events.seen[after_switch:]
        if m.get("run_id") in {run_a, run_b} and m.get("type") in {"block_done", "workflow_completed"}
    ]
    assert late == []
    for project in (first, second):
        assert not list((project.path / "data" / "processed").glob("*.csv")), project.path
    assert not (second.path / "data" / "zarr" / "alpha").exists()
    assert not (second.path / "data" / "zarr" / "beta").exists()


def test_a_sequential_rerun_after_concurrent_runs_shows_only_the_new_run(
    backend: Backend, events: EventStream, projects_dir: Path
) -> None:
    """After two workflows ran together, re-running one shows its new run everywhere and leaves the other alone."""
    project = make_project(backend, projects_dir, "rerun")
    gates = Gates(project)
    backend.put_workflow(marker_workflow("alpha", "A-first"))
    backend.put_workflow(marker_workflow("beta", "B"))

    first_a = start(backend, "alpha")
    run_b = start(backend, "beta")
    gates.entered("alpha-A-first")
    gates.entered("beta-B")
    gates.open("alpha-A-first")
    gates.open("beta-B")
    first_record = backend.wait_for_run(first_a)
    record_b = backend.wait_for_run(run_b)

    plots = {workflow_id: plot_for(backend, project, workflow_id) for workflow_id in ("alpha", "beta")}
    assert plot_text(backend, plots["alpha"], "alpha") == ("A-first", first_a)
    assert plot_text(backend, plots["beta"], "beta") == ("B", run_b)
    # Asking beta's plot for alpha's run does not draw alpha's output.
    foreign_markers, foreign_runs = plot_text(backend, plots["beta"], "beta", first_a)
    assert "A-first" not in foreign_markers and first_a not in foreign_runs

    backend.put_workflow(marker_workflow("alpha", "A-second"))
    gates.open("alpha-A-second")
    second_a = start(backend, "alpha")
    record = backend.wait_for_run(second_a)
    drain(events)

    assert record["run"]["status"] == "completed", record["run"]
    assert second_a != first_a
    assert recorded_runs(backend, "alpha") == sorted([first_a, second_a])
    assert recorded_runs(backend, "beta") == [run_b]
    assert {m["workflow_id"] for m in events.seen if m.get("run_id") == second_a} == {"alpha"}
    rows = preview_rows(backend, output_ref(run_event(events, second_a, "block_done", "hold")))
    assert [(row["marker"], row["made_in_run"], row["held_by"]) for row in rows] == [
        ("A-second", second_a, f"alpha/{second_a}/hold")
    ]
    saved = read_csv(project.path / "data" / "processed" / "alpha.csv")
    assert [(row["marker"], row["made_in_run"]) for row in saved] == [("A-second", second_a)]

    # Plots follow the new run for alpha and stay on beta's own run for beta.
    assert plot_text(backend, plots["alpha"], "alpha") == ("A-second", second_a)
    assert plot_text(backend, plots["beta"], "beta") == ("B", run_b)

    # The earlier runs keep their own records.
    assert backend.run(first_a) == first_record
    assert backend.run(run_b) == record_b


def plot_for(backend: Backend, project: Project, workflow_id: str) -> str:
    """Create a plot bound to ``<workflow>:hold.table`` whose SVG names the markers and runs it drew."""
    targets = backend.call("GET", "/api/plots/targets")["targets"]
    matching = [
        t for t in targets if t["workflow_id"] == workflow_id and t["node_id"] == "hold" and t["output_port"] == "table"
    ]
    assert len(matching) == 1, [(t["workflow_id"], t["node_id"], t["output_port"]) for t in targets]
    plot_id = f"{workflow_id}_markers"
    created = backend.call("POST", "/api/plots", json={"plot_id": plot_id, "target_id": matching[0]["target_id"]})
    (project.path / created["script_path"]).write_text(MARKER_PLOT, encoding="utf-8")
    return plot_id


def plot_text(backend: Backend, plot_id: str, workflow_id: str, run_id: str | None = None) -> tuple[str, str]:
    """Run the plot (on ``run_id``'s output when given) and return the ``(markers, runs)`` it drew."""
    body: dict[str, Any] = {"plot_id": plot_id}
    if run_id is not None:
        body["run_id"] = run_id
    result = backend.call("POST", "/api/plots/run", json=body)
    assert result["status"] == "succeeded", result
    assert result["source"]["workflow_id"] == workflow_id, result
    assert result["data_ref"], result
    svg = Path(result["artifact_paths"][0]).read_text(encoding="utf-8")
    drawn: list[tuple[str, str]] = re.findall(r"markers=\[([^\]]*)\] runs=\[([^\]]*)\]", svg)
    assert len(drawn) == 1, svg[:2000]
    return drawn[0]


@pytest.mark.xfail(
    strict=True,
    reason="#2474: POST /api/plots/run matches run_id against workflow identities, so a plot's own run id "
    "draws an empty figure",
)
def test_a_plot_asked_for_its_own_run_draws_that_run(backend: Backend, events: EventStream, projects_dir: Path) -> None:
    """A plot run on a named run of its own workflow draws that run, while another workflow runs beside it."""
    project = make_project(backend, projects_dir, "plot-run-id")
    gates = Gates(project)
    backend.put_workflow(marker_workflow("alpha", "A"))
    backend.put_workflow(marker_workflow("beta", "B"))
    run_a = start(backend, "alpha")
    run_b = start(backend, "beta")
    gates.entered("alpha-A")
    gates.entered("beta-B")
    gates.open("alpha-A")
    gates.open("beta-B")
    assert backend.wait_for_run(run_a)["run"]["status"] == "completed"
    assert backend.wait_for_run(run_b)["run"]["status"] == "completed"

    plot = plot_for(backend, project, "beta")
    assert plot_text(backend, plot, "beta", run_b) == ("B", run_b)


def test_ai_block_outputs_are_filed_per_workflow_and_never_reused_across_workflows(
    backend: Backend, events: EventStream, projects_dir: Path
) -> None:
    """Workflows with an AI node of the same id each ask their own agent and keep their own output file."""
    project = make_project(backend, projects_dir, "ai-outputs")
    gates = Gates(project)
    markers = {"alpha": "A", "beta": "B", "gamma": "C"}
    for workflow_id, marker in markers.items():
        backend.put_workflow(agent_workflow(workflow_id, marker))

    # alpha leaves an output behind; then beta and gamma, with reuse on, run together.
    runs = {"alpha": start(backend, "alpha")}
    assert backend.wait_for_run(runs["alpha"])["run"]["status"] == "completed"
    runs["beta"] = start(backend, "beta")
    runs["gamma"] = start(backend, "gamma")
    for run_id in runs.values():
        assert backend.wait_for_run(run_id)["run"]["status"] == "completed"

    for workflow_id, run_id in runs.items():
        assert gates.read(f"{workflow_id}-ai.invoked") == run_id, f"{workflow_id} did not ask its agent"
        rows = preview_rows(backend, output_ref(run_event(events, run_id, "block_done", "ai"), "summary"))
        assert [row["marker"] for row in rows] == [markers[workflow_id]], workflow_id
    for workflow_id in runs:
        written = Path(str(gates.read(f"{workflow_id}-ai.summary.path")))
        assert written.is_relative_to((project.path / "data" / "ai_outputs" / workflow_id / "ai").resolve()), written
