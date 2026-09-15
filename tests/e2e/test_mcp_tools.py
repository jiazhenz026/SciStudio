"""Every agent MCP tool, end to end, against a real server and a tutorial project (#2398).

An external agent reaches SciStudio through the WebMCP HTTP bridge of a running
``scistudio serve``: it reads the tool catalogue, then calls tools that act on
the project the backend has open. This module does exactly that. It builds a
project from the *Welcome to SciStudio* core tutorial (a plate-reader CSV, the
``normalize_fluorescence`` project block, and the Load -> Normalize -> Save
workflow the tutorial has the reader assemble), then works through it the way
the bundled agent skills tell an agent to: orient, run the workflow, inspect
what it produced, edit and re-run it, author a block, draw a plot, use the
workspace and command tools, and hit each documented refusal on the way.

Expectations come from each tool's own contract (its MCP description and result
model), the bundled skills, and the agent reference docs. Where the product does
not meet a documented contract, the expectation is kept as written and marked
``xfail(strict=True)`` with the issue that tracks it, so the suite turns red
when the behavior changes either way.

The last test is a coverage guard: it fails when the server registers a tool
that no test here dispatched. ``test_mcp_transports.py`` covers the stdio
processes (``scistudio mcp-bridge`` and ``scistudio webmcp-adapter``).
"""

from __future__ import annotations

import csv
import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any

import httpx
import psutil
import pytest

from tests.e2e.harness import Backend, EventStream, Project, ServeProcess, build_tutorial_project, requires_e2e
from tests.e2e.mcp_clients import TOKEN_HEADER, ToolLedger, WebMcpClient, read_loopback_token
from tests.e2e.test_tutorial_workflows import WELCOME_WORKFLOW

pytestmark = [requires_e2e, pytest.mark.timeout(300)]

TUTORIAL = "welcome-to-scistudio"
TUTORIAL_ASSETS = Path(__file__).resolve().parents[2] / "src" / "scistudio" / "tutorials" / "core" / TUTORIAL / "assets"
TERMINAL_STATES = {"succeeded", "failed", "cancelled"}

#: The tutorial's own plot script (the Learning Center writes it into plots/).
RENDER_SCRIPT = (TUTORIAL_ASSETS / "code" / "normalized_activity_render.py").read_text(encoding="utf-8")

#: A project block that holds its input long enough for a run to be cancelled mid-block.
HOLD_BLOCK = '''"""Hold a table for a while, then pass it on unchanged."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import DataFrame


class HoldTableBlock(ProcessBlock):
    """Wait before passing the table through, so a run can be cancelled mid-block."""

    name: ClassVar[str] = "Hold Table"
    type_name: ClassVar[str] = "hold_table"
    description: ClassVar[str] = "Wait, then pass the table through unchanged."
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="table", accepted_types=[DataFrame], description="Table to hold"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="table", accepted_types=[DataFrame], description="The same table"),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "seconds": {"type": "number", "default": 120, "title": "Seconds", "description": "How long to wait."},
        },
    }

    def process_item(self, item: DataFrame, config: BlockConfig, state: Any = None) -> DataFrame:
        time.sleep(float(config.get("seconds", 120)))
        return item
'''

HOLD_WORKFLOW = """workflow:
  id: hold
  version: "1.0.0"
  description: Load the plate and hold it.
  nodes:
    - id: load
      block_type: load_data
      config:
        core_type: DataFrame
        path: data/raw/cell_viability_fluorescence.csv
    - id: hold
      block_type: hold_table
      config:
        seconds: 120
  edges:
    - source: "load:data"
      target: "hold:table"
"""

#: The tutorial pipeline written by the agent in the flat node-config shape of the agent reference.
REVIEW_WORKFLOW = """workflow:
  id: review
  version: "1.0.0"
  description: Normalize the plate again for review
  nodes:
    - id: load
      block_type: load_data
      config:
        core_type: DataFrame
        path: data/raw/cell_viability_fluorescence.csv
    # Controls chosen with the bench scientist; keep this note.
    - id: norm
      block_type: normalize_fluorescence
      config:
        negative_control: neg_control
        positive_control: pos_control
    - id: save
      block_type: save_data
      config:
        core_type: DataFrame
        path: data/processed
        filename: review.csv
  edges:
    - source: "load:data"
      target: "norm:table"
    - source: "norm:normalized"
      target: "save:data"
"""


# ---------------------------------------------------------------------------
# Fixtures: one server (session), one tutorial project and agent (module).
# ---------------------------------------------------------------------------


@dataclass
class Agent:
    """What a test needs to act as an agent and to check the effects of what it did."""

    mcp: WebMcpClient
    backend: Backend
    project: Project
    serve: ServeProcess
    #: Facts recorded by earlier tests that the contract-gap tests below read back.
    observed: dict[str, Any] = field(default_factory=dict)

    def call(self, name: str, arguments: dict[str, Any] | None = None, /, **kwargs: Any) -> Any:
        return self.mcp.call(name, arguments, **kwargs)

    def poll_run(self, run_id: str, timeout: float = 180.0, until: set[str] = TERMINAL_STATES) -> list[dict[str, Any]]:
        """Poll ``get_run_status`` until ``state`` is in ``until``; return every status seen."""
        seen: list[dict[str, Any]] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.call("get_run_status", run_id=run_id).ok()
            seen.append(status)
            if status["state"] in until:
                return seen
            time.sleep(0.25)
        raise AssertionError(f"run {run_id} never reached {until}; last status {seen[-1] if seen else None}")

    def latest_lineage_run(self, workflow_id: str) -> dict[str, Any]:
        """The newest run the backend recorded for ``workflow_id`` (the GUI's run history)."""
        runs = self.backend.call("GET", "/api/runs", params={"workflow_id": workflow_id, "limit": 500})["runs"]
        assert runs, f"no recorded run of {workflow_id}"
        newest = max(runs, key=lambda row: row["started_at"])
        return self.backend.run(str(newest["run_id"]))

    def path(self, relative: str) -> Path:
        return self.project.path / relative


@pytest.fixture(scope="session")
def tool_ledger() -> ToolLedger:
    return ToolLedger()


@pytest.fixture(scope="module")
def agent(serve: ServeProcess, tmp_path_factory: pytest.TempPathFactory, tool_ledger: ToolLedger) -> Iterator[Agent]:
    backend = Backend(serve.base_url)
    project = build_tutorial_project(
        backend,
        tmp_path_factory.mktemp("mcp-projects"),
        name="mcp-agent",
        tutorial=TUTORIAL,
        copies=[
            ("assets/data", "data/raw"),
            ("assets/code/normalize_fluorescence.py", "blocks/normalize_fluorescence.py"),
        ],
    )
    # The workflow the tutorial has the reader assemble on the canvas, saved the way the GUI saves it.
    backend.put_workflow(WELCOME_WORKFLOW)
    client = WebMcpClient(serve.base_url, read_loopback_token(serve.home, serve.port), tool_ledger)
    client.catalogue()
    try:
        yield Agent(mcp=client, backend=backend, project=project, serve=serve)
    finally:
        client.close()
        backend.close()


@pytest.fixture(autouse=True)
def _dump_server_log_on_failure(serve: ServeProcess, request: pytest.FixtureRequest) -> Iterator[None]:
    yield
    report = getattr(request.node, "rep_call", None)
    if report is not None and report.failed:
        print(f"\n--- scistudio serve log (tail) ---\n{serve.log_tail(120)}")


@pytest.fixture(scope="module")
def tutorial_run(agent: Agent) -> dict[str, Any]:
    """Validate and run the tutorial workflow through MCP, as the build-workflow skill prescribes."""
    validation = agent.call("validate_workflow", yaml_or_path="workflows/main.yaml").ok()
    assert validation["valid"] is True, validation
    started = agent.call("run_workflow", path="workflows/main.yaml").ok()
    statuses = agent.poll_run(started["run_id"])
    return {"started": started, "statuses": statuses, "validation": validation}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def assert_controls_normalized(rows: list[dict[str, Any]]) -> None:
    by_condition: dict[str, list[float]] = {}
    for row in rows:
        by_condition.setdefault(str(row["condition"]), []).append(float(row["normalized_activity"]))
    assert mean(by_condition["neg_control"]) == pytest.approx(0.0, abs=1e-9)
    assert mean(by_condition["pos_control"]) == pytest.approx(1.0, abs=1e-9)
    assert 0.0 < mean(by_condition["treated_1uM"]) < mean(by_condition["treated_5uM"]) < 1.0


# ---------------------------------------------------------------------------
# The bridge itself.
# ---------------------------------------------------------------------------


def test_catalogue_describes_every_tool_and_the_bridge_guards_its_calls(agent: Agent) -> None:
    catalogue = agent.mcp.catalogue()

    assert catalogue["context"]["projectId"] == agent.project.id
    names = [tool["name"] for tool in catalogue["tools"]]
    assert len(names) == len(set(names)), names
    for tool in catalogue["tools"]:
        assert tool["description"].strip(), tool["name"]
        assert tool["inputSchema"]["type"] == "object", tool["name"]
        assert tool["mutation"] in {"read", "write"}, tool
        assert tool["category"] != "uncategorised", tool

    # Both endpoints require the per-launch loopback token.
    anonymous = httpx.get(f"{agent.serve.base_url}/api/webmcp/tools")
    assert anonymous.status_code == 401
    forged = httpx.post(
        f"{agent.serve.base_url}/api/webmcp/call",
        headers={TOKEN_HEADER: "not-the-token"},
        json={"name": "get_project_info", "arguments": {}, "projectId": agent.project.id},
    )
    assert forged.status_code == 401

    unknown = agent.mcp.post_call("no_such_tool", {}, agent.project.id)
    assert unknown.status_code == 404

    # A write bound to a project that is no longer active is rejected before it runs.
    stale = agent.mcp.post_call("write_file", {"path": "stale.txt", "content": "x"}, "project-not-open")
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["error"] == "stale_project_context"
    assert stale.json()["detail"]["activeProjectId"] == agent.project.id
    assert not agent.path("stale.txt").exists()
    # A read is dispatched anyway and observes the current project.
    read = agent.mcp.post_call("get_project_info", {}, "project-not-open")
    assert read.status_code == 200
    assert read.json()["structuredContent"]["project"]["id"] == agent.project.id


def test_block_files_are_refused_until_the_agent_has_called_list_blocks(agent: Agent) -> None:
    # The rule is tracked once per backend lifetime, so it is only observable
    # before anything in this session has called list_blocks.
    if "list_blocks" in agent.mcp.ledger.called:
        pytest.fail("list_blocks was already called on this server; this test must run first in the module")

    refused = agent.call("write_file", path="blocks/early_block.py", content="VALUE = 1\n")
    refusal = refused.refused("list_blocks_required")
    assert "list_blocks" in refusal["refusal"]["use_instead"]
    assert not agent.path("blocks/early_block.py").exists()

    scaffold = agent.call("scaffold_block", {"name": "early_block", "category": "process"})
    assert scaffold.is_error, scaffold.structured
    assert not agent.path("blocks/early_block.py").exists()


# ---------------------------------------------------------------------------
# Orientation: project, docs, catalogues.
# ---------------------------------------------------------------------------


def test_agent_orients_itself_in_the_tutorial_project(agent: Agent) -> None:
    context = agent.call("get_agent_context").ok()
    assert context["status"] == "ok", context
    assert context["project"]["id"] == agent.project.id
    assert Path(context["project"]["path"]) == agent.project.path
    assert "main" in context["project"]["workflows"]
    assert context["guidance_summary"], context
    assert context["asset_classes"], context
    assert context["index"], context
    for entry in context["index"]:
        # Each indexed asset exists and names the tool that retrieves it.
        assert agent.path(entry["path"]).exists(), entry
        assert entry["retrieval"]["tool"] in {"get_doc", "read_file"}, entry
    # Following the index retrieves the asset it names, with each retrieval tool.
    by_tool = {entry["retrieval"]["tool"]: entry for entry in context["index"]}
    for tool, entry in by_tool.items():
        fetched = agent.call(tool, entry["retrieval"].get("arguments") or {"path": entry["path"]}).ok()
        assert fetched["content"] == agent.path(entry["path"]).read_text(encoding="utf-8"), entry

    info = agent.call("get_project_info").ok()
    assert info["project"]["name"] == "mcp-agent"
    assert Path(info["path"]) == agent.project.path
    assert info["workflows"] == ["main"]

    # Nothing is open in an editor yet; then the GUI reports the workflow it opened.
    assert agent.call("get_active_workflow_context").ok() == {"workflow_id": None, "workflow_name": None}
    agent.backend.call("POST", "/api/ai/active-context", json={"workflow_id": "main"})
    active = agent.call("get_active_workflow_context").ok()
    assert active == {"workflow_id": "main", "workflow_name": "main"}  # no metadata title: falls back to the id

    gui = agent.call("open_gui").ok()
    assert gui["base_url"] == agent.serve.base_url
    link = httpx.URL(gui["url"])
    assert str(link).startswith(agent.serve.base_url)
    assert Path(link.params["project"]) == agent.project.path
    assert link.params["workflow"] == "main"
    assert "scistudio-use-gui" in gui["hint"]
    # The address is real: the backend answers on it.
    assert httpx.get(f"{gui['base_url']}/api/version").status_code == 200

    types = agent.call("list_types").ok()
    type_names = {row["name"] for row in types["types"]}
    assert {"DataObject", "DataFrame", "Array", "Series", "Text", "Artifact"} <= type_names
    assert types["count"] == len(types["types"])

    catalog = agent.call("list_blocks").ok()
    blocks = {row["type_name"]: row for row in catalog["blocks"]}
    assert {"load_data", "save_data", "normalize_fluorescence"} <= set(blocks)
    assert blocks["normalize_fluorescence"]["name"] == "Normalize Fluorescence"
    assert blocks["normalize_fluorescence"]["base_category"] == "process"
    assert "get_block_schema" in catalog["next_step"]

    schema = agent.call("get_block_schema", type_name="normalize_fluorescence").ok()
    assert [port["name"] for port in schema["ports"]["input"]] == ["table"]
    assert [port["name"] for port in schema["ports"]["output"]] == ["normalized"]
    assert set(schema["config_schema"]["required"]) == {"negative_control", "positive_control"}
    # #2435: only IO-capable blocks list format capabilities.
    assert schema["format_capabilities"] == [] and schema["format_capability_usage"] is None
    agent.call("get_block_schema", type_name="no_such_block").raised()

    # Core Save lists the save formats it can pick by capability_id; a Code Block
    # port can pick either direction.
    save_schema = agent.call("get_block_schema", type_name="save_data").ok()
    save_formats = {entry["capability_id"]: entry for entry in save_schema["format_capabilities"]}
    assert save_formats["core.dataframe.csv.save"]["extensions"] == [".csv"]
    assert save_formats["core.dataframe.csv.save"]["data_type"] == "DataFrame"
    assert {entry["direction"] for entry in save_formats.values()} == {"save"}
    assert "capability_id" in save_schema["format_capability_usage"]
    code_schema = agent.call("get_block_schema", type_name="code_block").ok()
    assert {entry["direction"] for entry in code_schema["format_capabilities"]} == {"load", "save"}

    examples = agent.call("list_block_examples", category="process").ok()
    assert examples, "no curated process examples"
    for example in examples:
        assert Path(example["path"]).is_file(), example
    agent.call("list_block_examples", category="not_a_category").raised()

    source = agent.call("read_block_source", type_name="normalize_fluorescence").ok()
    assert Path(source["path"]) == agent.path("blocks/normalize_fluorescence.py")
    assert "class NormalizeFluorescenceBlock" in source["source"]
    agent.call("read_block_source", type_name="no_such_block").raised()


def test_agent_finds_and_reads_the_provisioned_docs(agent: Agent) -> None:
    hits = agent.call("search_docs", query="get_run_status").ok()
    assert hits, "search_docs found no page mentioning get_run_status"
    assert len(hits) <= 20
    assert [hit["score"] for hit in hits] == sorted((hit["score"] for hit in hits), reverse=True)
    for hit in hits:
        assert not Path(hit["path"]).is_absolute(), hit
        assert Path(hit["path"]).suffix in {".md", ".rst", ".txt"}, hit
        assert not hit["path"].startswith("data/"), hit

    scoped = agent.call("search_docs", query="workflow", scope=".scistudio/agent-reference").ok()
    assert scoped, "nothing under .scistudio/agent-reference mentions workflows"
    assert all(hit["path"].startswith(".scistudio/agent-reference/") for hit in scoped), scoped

    page = agent.call("get_doc", path=hits[0]["path"]).ok()
    assert "get_run_status" in page["content"]
    assert page["bytes"] == len(page["content"].encode("utf-8"))
    assert page["content"] == agent.path(hits[0]["path"]).read_text(encoding="utf-8")

    agent.call("get_doc", path="../../../../etc/hosts").raised()  # escapes the project
    agent.call("get_doc", path="blocks/normalize_fluorescence.py").raised()  # not a doc file
    agent.call("get_doc", path="docs/does-not-exist.md").raised()


# ---------------------------------------------------------------------------
# Run the tutorial workflow and inspect what it produced.
# ---------------------------------------------------------------------------


def test_tutorial_workflow_runs_to_completion(agent: Agent, tutorial_run: dict[str, Any]) -> None:
    workflow = agent.call("get_workflow", path="workflows/main.yaml").ok()
    assert Path(workflow["path"]) == agent.path("workflows/main.yaml")
    assert [node["id"] for node in workflow["nodes"]] == ["load", "norm", "save"]
    assert {(edge["source"], edge["target"]) for edge in workflow["edges"]} == {
        ("load:data", "norm:table"),
        ("norm:normalized", "save:data"),
    }

    assert tutorial_run["validation"]["errors"] == []
    started = tutorial_run["started"]
    assert started["status"] == "queued"
    assert started["run_id"]
    assert "get_run_status" in started["next_step"] and "get_run_status" in started["poll_hint"]

    statuses = tutorial_run["statuses"]
    final = statuses[-1]
    assert final["run_id"] == started["run_id"]
    assert final["state"] == "succeeded", final
    assert final["errors"] == []
    assert final["progress"]["block_states"] == {"load": "DONE", "norm": "DONE", "save": "DONE"}
    assert all(status["state"] in {"queued", "running", "succeeded"} for status in statuses), statuses

    # The backend's run history agrees, and the workflow's Save wrote the table.
    record = agent.latest_lineage_run("main")
    assert record["run"]["status"] == "completed"
    rows = read_csv(agent.path("data/processed/result.csv"))
    assert len(rows) == 12
    assert_controls_normalized(rows)

    agent.call("get_run_status", run_id="no-such-run").raised()

    listing = agent.call("list_data", project_dir=str(agent.project.path)).ok()
    listed = [entry for group in ("zarr", "parquet", "artifacts") for entry in listing[group]]
    assert listed, listing
    for entry in listed:
        assert Path(entry["path"]).exists(), entry
        assert Path(entry["path"]).is_relative_to(agent.project.path / "data"), entry


def test_block_outputs_are_inspectable_without_loading_them(agent: Agent, tutorial_run: dict[str, Any]) -> None:
    run_id = tutorial_run["started"]["run_id"]
    output = agent.call("get_block_output", run_id=run_id, block_id="norm", port="normalized").ok()
    ref = output["ref"]
    assert output["type"]["type_name"] == "DataFrame"
    assert output["type"]["type_chain"][-1] == "DataFrame"
    assert Path(ref["path"]).exists(), ref
    agent.observed["normalized_ref"] = ref

    loaded = agent.call("get_block_output", run_id=run_id, block_id="load", port="data").ok()
    agent.observed["loaded_ref"] = loaded["ref"]

    meta = agent.call("inspect_data", ref=ref).ok()
    assert meta["path"] == ref["path"]
    assert meta["backend"] == ref["backend"]
    assert meta["size"] == Path(ref["path"]).stat().st_size
    assert meta["type_chain"][-1] == "DataFrame"
    stored = meta["metadata_store"]["metadata"]
    assert stored["row_count"] == 12
    assert "normalized_activity" in stored["columns"]

    preview = agent.call("preview_data", ref=ref, fmt="table").ok()
    assert preview["fmt"] == "table"
    assert preview["truncated"] is False
    assert preview["payload"]["columns"] == ["condition", "replicate", "fluorescence", "normalized_activity"]
    assert len(preview["payload"]["rows"]) == 12
    assert_controls_normalized(preview["payload"]["rows"])
    # fmt is advisory: the ref's type decides the shape.
    assert agent.call("preview_data", ref=ref, fmt="png_base64").ok()["fmt"] == "table"

    agent.call("get_block_output", run_id=run_id, block_id="norm", port="no_such_port").raised()
    agent.call("get_block_output", run_id=run_id, block_id="no_such_block", port="normalized").raised()


def test_lineage_and_logs_trace_the_normalized_table(agent: Agent, tutorial_run: dict[str, Any]) -> None:
    ref = agent.observed["normalized_ref"]
    lineage = agent.call("get_lineage", ref=ref).ok()
    object_id = ref["metadata"]["framework"]["object_id"]
    assert object_id in {node["object_id"] for node in lineage["nodes"]}, lineage
    for edge in lineage["edges"]:
        assert {edge["source"], edge["target"]} <= {node["object_id"] for node in lineage["nodes"]}, lineage
    agent.observed["lineage"] = lineage

    unresolvable = agent.call("get_lineage", ref={"backend": "arrow", "path": "nowhere.parquet", "metadata": {}}).ok()
    assert unresolvable["nodes"] == [] and unresolvable["edges"] == []
    assert unresolvable["note"], unresolvable

    # The id the backend's run history records is the id run_workflow returned.
    lineage_run_id = agent.latest_lineage_run("main")["run"]["run_id"]
    logs = agent.call("get_block_logs", run_id=lineage_run_id, block_id="norm").ok()
    assert logs["source"] == "run_log"
    assert logs["stdout"] == ""  # the engine routes block output onto one stream
    assert "block_done block_id=norm" in logs["stderr"]
    assert "block_id=load" not in logs["stderr"]  # filtered to this block
    assert logs["truncated"] is False
    agent.call("get_block_logs", run_id="no-such-run", block_id="norm").raised()


# ---------------------------------------------------------------------------
# Edit, validate, and re-run.
# ---------------------------------------------------------------------------


def test_agent_writes_edits_and_reruns_a_workflow(agent: Agent) -> None:
    written = agent.call("write_workflow", path="workflows/review.yaml", yaml=REVIEW_WORKFLOW).ok()
    assert Path(written["path"]) == agent.path("workflows/review.yaml")
    assert written["bytes_written"] == agent.path("workflows/review.yaml").stat().st_size
    assert written["warnings"] == []
    assert "validate_workflow" in written["next_step"]
    assert agent.backend.call("GET", "/api/workflows/review")["id"] == "review"
    assert agent.call("get_project_info").ok()["workflows"] == ["main", "review"]

    assert agent.call("validate_workflow", yaml_or_path="workflows/review.yaml").ok() == {
        "valid": True,
        "errors": [],
        "warnings": [],
    }

    config = agent.call("get_block_config", workflow_path="workflows/review.yaml", block_id="norm").ok()
    assert config["type"] == "normalize_fluorescence"
    assert config["params"] == {"negative_control": "neg_control", "positive_control": "pos_control"}

    patched = agent.call(
        "update_block_config",
        workflow_path="workflows/review.yaml",
        block_id="save",
        params={"filename": "review2.csv"},
    ).ok()
    assert patched["block_id"] == "save"
    assert patched["bytes_written"] == agent.path("workflows/review.yaml").stat().st_size
    assert "validate_workflow" in patched["next_step"]
    save_config = agent.call("get_block_config", workflow_path="workflows/review.yaml", block_id="save").ok()
    assert save_config["params"] == {
        "core_type": "DataFrame",
        "path": "data/processed",
        "filename": "review2.csv",
    }
    # #2435: nothing is pinned, so the filename's extension decides the format.
    assert save_config["capability"] == {
        "direction": "save",
        "data_type": "DataFrame",
        "extension": ".csv",
        "selected_capability_id": None,
        "resolved_capability_id": "core.dataframe.csv.save",
        "status": "resolved",
    }
    assert save_config["port_capabilities"] == []
    # A capability that contradicts the .csv filename is refused and not written;
    # the matching one is pinned and the re-run below honours it.
    agent.call(
        "update_block_config",
        workflow_path="workflows/review.yaml",
        block_id="save",
        params={"capability_id": "core.dataframe.parquet.save"},
    ).raised()
    assert "capability_id" not in agent.path("workflows/review.yaml").read_text(encoding="utf-8")
    agent.call(
        "update_block_config",
        workflow_path="workflows/review.yaml",
        block_id="save",
        params={"capability_id": "core.dataframe.csv.save"},
    ).ok()
    pinned = agent.call("get_block_config", workflow_path="workflows/review.yaml", block_id="save").ok()["capability"]
    assert (pinned["status"], pinned["resolved_capability_id"]) == ("pinned", "core.dataframe.csv.save")

    edited = agent.call(
        "edit_workflow",
        workflow_path="workflows/review.yaml",
        edits=[
            {"old_string": "description: Normalize the plate again for review", "new_string": "description: Reviewed"}
        ],
    ).ok()
    assert edited["edits_applied"] == 1
    assert "validate_workflow" in edited["next_step"]
    text = agent.path("workflows/review.yaml").read_text(encoding="utf-8")
    # Both partial-edit tools preserve what they did not touch, comments included.
    assert "# Controls chosen with the bench scientist; keep this note." in text
    assert "description: Reviewed" in text
    assert "filename: review2.csv" in text
    assert agent.call("validate_workflow", yaml_or_path="workflows/review.yaml").ok()["valid"] is True

    started = agent.call("run_workflow", path="workflows/review.yaml").ok()
    final = agent.poll_run(started["run_id"])[-1]
    assert final["state"] == "succeeded", final
    assert final["progress"]["block_states"] == {"load": "DONE", "norm": "DONE", "save": "DONE"}
    assert len(read_csv(agent.path("data/processed/review2.csv"))) == 12

    # A config change that breaks the block surfaces the traceback in the run status.
    agent.call(
        "update_block_config",
        workflow_path="workflows/review.yaml",
        block_id="norm",
        params={"negative_control": "not_a_condition"},
    ).ok()
    started = agent.call("run_workflow", path="workflows/review.yaml").ok()
    failed = agent.poll_run(started["run_id"])[-1]
    agent.observed["failed_run_status"] = failed
    assert failed["progress"]["block_states"]["norm"] == "ERROR"
    assert failed["progress"]["block_states"]["save"] == "SKIPPED"
    [error] = failed["errors"]
    assert error["block_id"] == "norm"
    assert "Traceback (most recent call last)" in error["error"]
    assert "ValueError" in error["summary"]
    assert agent.latest_lineage_run("review")["run"]["status"] == "failed"


def test_workflow_tools_refuse_what_their_contracts_rule_out(agent: Agent) -> None:
    before = agent.path("workflows/main.yaml").read_text(encoding="utf-8")

    # write_workflow: the file stem must equal the workflow id.
    mismatch = REVIEW_WORKFLOW.replace("id: review", "id: other_name")
    agent.call("write_workflow", path="workflows/renamed.yaml", yaml=mismatch).raised()
    assert not agent.path("workflows/renamed.yaml").exists()
    # write_workflow: an unregistered block_type is a hard failure.
    unregistered = REVIEW_WORKFLOW.replace("id: review", "id: unregistered").replace(
        "block_type: normalize_fluorescence", "block_type: no_such_block"
    )
    agent.call("write_workflow", path="workflows/unregistered.yaml", yaml=unregistered).raised()
    assert not agent.path("workflows/unregistered.yaml").exists()
    # write_workflow / get_workflow: paths stay inside the project.
    escape = REVIEW_WORKFLOW.replace("id: review", "id: escape")
    agent.call("write_workflow", path="../escape.yaml", yaml=escape).raised()
    assert not (agent.project.path.parent / "escape.yaml").exists()
    agent.call("get_workflow", path="../../etc/hosts").raised()
    agent.call("get_workflow", path="workflows/missing.yaml").raised()

    # validate_workflow reports a structural error without writing anything.
    dotted = REVIEW_WORKFLOW.replace('source: "load:data"', 'source: "load.data"')
    result = agent.call("validate_workflow", yaml_or_path=dotted).ok()
    assert result["valid"] is False and result["errors"], result

    # edit_workflow applies atomically: a missing match leaves the file unchanged.
    agent.call(
        "edit_workflow",
        workflow_path="workflows/main.yaml",
        edits=[
            {"old_string": "id: norm", "new_string": "id: normalize"},
            {"old_string": "text that is not in the file", "new_string": "x"},
        ],
    ).raised()
    assert agent.path("workflows/main.yaml").read_text(encoding="utf-8") == before

    agent.call("get_block_config", workflow_path="workflows/main.yaml", block_id="no_such_node").raised()
    agent.call(
        "update_block_config", workflow_path="workflows/main.yaml", block_id="no_such_node", params={"x": 1}
    ).raised()
    # #2435: an unknown capability_id is refused before anything is written.
    agent.call(
        "update_block_config",
        workflow_path="workflows/main.yaml",
        block_id="save",
        params={"capability_id": "no.such.capability.save"},
    ).raised()
    assert agent.path("workflows/main.yaml").read_text(encoding="utf-8") == before


def test_a_running_block_can_be_cancelled(agent: Agent) -> None:
    assert "hold_table" not in {row["type_name"] for row in agent.call("list_blocks").ok()["blocks"]}
    written = agent.call("write_file", path="blocks/hold_table.py", content=HOLD_BLOCK).ok()
    assert written["registry_refreshed"] is True  # a lint-clean save under blocks/ reloads the registry
    assert agent.call("get_block_schema", type_name="hold_table").ok()["ports"]["input"][0]["name"] == "table"
    agent.call("write_workflow", path="workflows/hold.yaml", yaml=HOLD_WORKFLOW).ok()

    started = agent.call("run_workflow", path="workflows/hold.yaml").ok()
    running = agent.poll_run(started["run_id"], timeout=60, until={"running"})
    deadline = time.monotonic() + 60
    while running[-1]["progress"]["block_states"].get("hold") != "RUNNING":
        assert time.monotonic() < deadline, running[-1]
        time.sleep(0.25)
        running.append(agent.call("get_run_status", run_id=started["run_id"]).ok())

    cancelled = agent.call("cancel_run", run_id=started["run_id"]).ok()
    assert cancelled == {
        "run_id": started["run_id"],
        "cancel_requested": True,
        "next_step": cancelled["next_step"],
    }
    assert "get_run_status" in cancelled["next_step"]

    deadline = time.monotonic() + 60
    while agent.latest_lineage_run("hold")["run"]["status"] not in {"completed", "failed", "cancelled"}:
        assert time.monotonic() < deadline, "the cancelled run never finished"
        time.sleep(0.25)
    assert agent.latest_lineage_run("hold")["run"]["status"] == "cancelled"
    final = agent.poll_run(started["run_id"])[-1]
    agent.observed["cancelled_run_status"] = final
    assert final["progress"]["block_states"]["hold"] == "CANCELLED"

    agent.call("cancel_run", run_id="no-such-run").raised()


# ---------------------------------------------------------------------------
# Block authoring.
# ---------------------------------------------------------------------------


def test_agent_scaffolds_reloads_tests_and_promotes_a_block(agent: Agent) -> None:
    listed_before = {row["type_name"] for row in agent.call("list_blocks").ok()["blocks"]}

    scaffold = agent.call(
        "scaffold_block",
        {
            "name": "scale_activity",
            "category": "process",
            "input_ports": {"table": {"type": "DataFrame", "description": "Normalized activity table"}},
            "output_ports": {"scaled": {"type": "DataFrame", "description": "Activity in percent"}},
            "description": "Scale normalized activity to percent.",
        },
    ).ok()
    block_file = agent.path("blocks/scale_activity.py")
    assert Path(scaffold["path"]) == block_file
    assert scaffold["status"] == "ok"
    assert scaffold["bytes_written"] == block_file.stat().st_size
    assert scaffold["warnings"] == []
    assert "reload_blocks" in scaffold["next_step"]
    assert "class ScaleActivity" in block_file.read_text(encoding="utf-8")

    # An existing file is never overwritten; AI steps are not an authoring surface.
    agent.call("scaffold_block", {"name": "scale_activity", "category": "process"}).raised()
    ai = agent.call("scaffold_block", {"name": "ask_the_ai", "category": "ai"})
    assert ai.refused("ai_block_not_authored")["bytes_written"] == 0
    assert not agent.path("blocks/ask_the_ai.py").exists()
    agent.call("scaffold_block", {"name": "Not Snake Case", "category": "process"}).raised()

    # Soft validation: generic and unregistered port types warn but still write.
    loose = agent.call(
        "scaffold_block",
        {
            "name": "loose_ports",
            "category": "process",
            "input_ports": {"anything": {"type": "DataObject"}},
            "output_ports": {"mystery": {"type": "NotARegisteredType"}},
        },
    ).ok()
    assert agent.path("blocks/loose_ports.py").is_file()
    assert any("DataObject" in warning for warning in loose["warnings"]), loose["warnings"]
    assert any("NotARegisteredType" in warning for warning in loose["warnings"]), loose["warnings"]

    reload = agent.call("reload_blocks").ok()
    assert "list_blocks" in reload["next_step"]
    listed_after = {row["type_name"]: row for row in agent.call("list_blocks").ok()["blocks"]}
    assert reload["reloaded"] == len(listed_after)
    new_types = set(listed_after) - listed_before
    [scale_type] = [name for name in new_types if listed_after[name]["name"] == "Scale Activity"]
    agent.observed["reload"] = {"result": reload, "new_types": sorted(new_types)}

    source = agent.call("read_block_source", type_name=scale_type).ok()
    assert Path(source["path"]) == block_file

    tests_dir = agent.path("tests/blocks")
    missing = agent.call("run_block_tests", type_name=scale_type).ok()
    assert missing["found"] is False and missing["returncode"] == -1
    test_file = Path(missing["test_path"])
    assert test_file.parent == tests_dir
    assert test_file.name == f"test_{scale_type.lower()}.py"

    agent.call(
        "write_file",
        path=test_file.relative_to(agent.project.path).as_posix(),
        content="def test_percent():\n    assert round(0.5 * 100) == 50\n",
        create_parents=True,
    ).ok()
    passing = agent.call("run_block_tests", type_name=scale_type).ok()
    assert passing["found"] is True
    assert passing["returncode"] == 0, passing
    assert "1 passed" in passing["stdout"]

    agent.call(
        "write_file",
        path=test_file.relative_to(agent.project.path).as_posix(),
        content="def test_percent():\n    assert round(0.5 * 100) == 5\n",
    ).ok()
    failing = agent.call("run_block_tests", type_name=scale_type).ok()
    assert failing["returncode"] != 0
    assert "1 failed" in failing["stdout"]

    # Promotion moves a project block into the user library and keeps it registered.
    promoted = agent.call("promote_to_user_library", block_type=scale_type).ok()
    library_file = agent.serve.home / ".scistudio" / "blocks" / promoted["filename"]
    assert Path(promoted["path"]) == library_file
    assert library_file.is_file()
    assert Path(promoted["source_path"]) == block_file
    assert Path(promoted["moved_from"]) == block_file and promoted["move_error"] is None
    assert not block_file.exists()
    assert promoted["bytes_written"] == library_file.stat().st_size
    assert Path(agent.call("read_block_source", type_name=scale_type).ok()["path"]) == library_file
    # Its origin is no longer the project, and a built-in never was.
    agent.call("promote_to_user_library", block_type=scale_type).raised()
    agent.call("promote_to_user_library", block_type="load_data").raised()
    agent.call("promote_to_user_library", block_type="no_such_block").raised()


# ---------------------------------------------------------------------------
# Plots.
# ---------------------------------------------------------------------------


def test_agent_draws_the_tutorial_plot_from_the_run(agent: Agent, tutorial_run: dict[str, Any]) -> None:
    workflow_before = agent.path("workflows/main.yaml").read_text(encoding="utf-8")

    listing = agent.call("list_plot_targets", workflow_path="workflows/main.yaml").ok()
    assert listing["count"] == len(listing["targets"])
    assert "scaffold_plot" in listing["next_step"]
    agent.observed["plot_targets"] = listing["targets"]
    by_node = {(target["node_id"], target["output_port"]): target for target in listing["targets"]}
    target = by_node[("norm", "normalized")]
    assert target["workflow_path"] == "workflows/main.yaml"
    assert target["block_type"] == "normalize_fluorescence"
    assert target["output_type"] == "DataFrame"
    assert target["latest_output_available"] is True, target
    assert by_node[("load", "data")]["latest_output_available"] is True
    assert agent.call("list_plot_targets").ok()["count"] >= listing["count"]  # every workflow

    python_examples = agent.call("list_plot_examples", language="python", library="matplotlib").ok()
    assert python_examples["count"] == len(python_examples["examples"]) > 0
    assert all(ex["language"] == "python" and ex["library"] == "matplotlib" for ex in python_examples["examples"])
    assert all("def render(collection)" in ex["source"] for ex in python_examples["examples"])
    r_examples = agent.call("list_plot_examples", language="r").ok()
    assert r_examples["count"] > 0 and all(ex["language"] == "r" for ex in r_examples["examples"])

    scaffold = agent.call("scaffold_plot", plot_id="normalized_activity", target_id=target["target_id"]).ok()
    assert scaffold["manifest_path"] == "plots/normalized_activity/plot.yaml"
    assert agent.path(scaffold["manifest_path"]).is_file()
    assert agent.path(scaffold["script_path"]).is_file()
    assert "validate_plot" in scaffold["next_step"]
    # Never overwritten by default, and never bound by a node label.
    agent.call("scaffold_plot", plot_id="normalized_activity", target_id=target["target_id"]).raised()
    agent.call("scaffold_plot", plot_id="by_label", target_id="norm").raised()
    assert not agent.path("plots/by_label").exists()

    plot = agent.call("read_plot_source", plot_id="normalized_activity").ok()
    assert plot["manifest"]["target"]["node_id"] == "norm"
    assert plot["manifest"]["target"]["output_port"] == "normalized"
    assert plot["manifest"]["script"]["entrypoint"] == "render"
    assert plot["script_source"] == agent.path(scaffold["script_path"]).read_text(encoding="utf-8")
    agent.call("read_plot_source", plot_id="no_such_plot").raised()
    agent.call("read_plot_source").raised()  # exactly one of plot_id / path

    # The tutorial's own render script replaces the starter.
    agent.call("write_file", path=scaffold["script_path"], content=RENDER_SCRIPT).ok()
    validation = agent.call("validate_plot", path=scaffold["manifest_path"]).ok()
    assert validation["valid"] is True and validation["errors"] == [], validation
    agent.call("validate_plot").raised()
    agent.call("validate_plot", plot_id="normalized_activity", path=scaffold["manifest_path"]).raised()

    rendered = agent.call("run_plot_job", plot_id="normalized_activity").ok()
    assert rendered["status"] == "succeeded", rendered
    assert rendered["returncode"] == 0
    preview_dir = agent.path(".scistudio/previews/main/norm/normalized/normalized_activity")
    assert rendered["artifact_paths"], rendered
    for artifact in rendered["artifact_paths"]:
        assert Path(artifact).parent == preview_dir, artifact
        assert Path(artifact).stat().st_size > 0
        assert Path(artifact).stem == "current"
    assert (preview_dir / "current.json").is_file()
    # Preview-only: the workflow is untouched and gained no node.
    assert agent.path("workflows/main.yaml").read_text(encoding="utf-8") == workflow_before
    agent.call("run_plot_job", plot_id="no_such_plot").raised()


# ---------------------------------------------------------------------------
# Workspace files.
# ---------------------------------------------------------------------------


def test_workspace_tools_change_project_files_under_the_author_rules(agent: Agent) -> None:
    created = agent.call("create_directory", path="notes").ok()
    assert created["kind"] == "created" and agent.path("notes").is_dir()

    first = agent.call("write_file", path="notes/plan.md", content="normalize the plate\nthen plot\n", mode="create")
    first_env = first.ok()
    assert first_env["kind"] == "created"
    assert first_env["affected_paths"] == ["created:notes/plan.md"]
    assert agent.path("notes/plan.md").read_text(encoding="utf-8") == "normalize the plate\nthen plot\n"
    version = first_env["state_version"]
    agent.call("write_file", path="notes/plan.md", content="again", mode="create").refused("already_exists")

    info = agent.call("get_file_info", path="notes/plan.md").ok()
    assert info["exists"] and info["type"] == "file" and info["within_project"]
    assert info["size_bytes"] == agent.path("notes/plan.md").stat().st_size
    assert info["state_version"] == version
    assert info["writable_by_author_tools"] is True
    assert (
        agent.call("get_file_info", path="data/raw/cell_viability_fluorescence.csv").ok()["writable_by_author_tools"]
        is False
    )

    patched = agent.call(
        "patch_file", path="notes/plan.md", old_text="the plate", new_text="plate 7", expected_state_version=version
    ).ok()
    assert patched["replacements"] == 1 and patched["kind"] == "modified"
    assert agent.path("notes/plan.md").read_text(encoding="utf-8") == "normalize plate 7\nthen plot\n"
    # A write based on the old version is a conflict, not an overwrite.
    agent.call("write_file", path="notes/plan.md", content="clobber", expected_state_version=version).refused(
        "stale_version"
    )
    agent.call("patch_file", path="notes/plan.md", old_text="absent text", new_text="x").refused(
        "patch_target_not_found"
    )
    assert agent.path("notes/plan.md").read_text(encoding="utf-8") == "normalize plate 7\nthen plot\n"

    window = agent.call("read_file", path="notes/plan.md", offset=0, limit=9).ok()
    assert window["content"] == "normalize"
    assert window["truncated"] is True and window["next_offset"] == 9
    assert window["total_size_bytes"] == agent.path("notes/plan.md").stat().st_size
    rest = agent.call("read_file", path="notes/plan.md", offset=window["next_offset"]).ok()
    assert window["content"] + rest["content"] == "normalize plate 7\nthen plot\n"
    assert rest["truncated"] is False

    agent.path("notes/blob.bin").write_bytes(b"\x00\x01\x02binary\xff")
    agent.call("read_file", path="notes/blob.bin").refused("binary_content")
    raw = agent.call("read_file", path="notes/blob.bin", encoding="base64").ok()
    assert raw["encoding"] == "base64" and raw["content"]

    # Reads may go outside the project by absolute path; changes may not.
    outside = agent.serve.home / "outside-notes.txt"
    outside.write_text("shared dataset readme\n", encoding="utf-8")
    assert agent.call("read_file", path=str(outside)).ok()["content"] == "shared dataset readme\n"
    agent.call("write_file", path=str(outside), content="x").refused("outside_project")
    agent.call("write_file", path="../escape.txt", content="x").refused("outside_project")
    assert outside.read_text(encoding="utf-8") == "shared dataset readme\n"
    assert not (agent.project.path.parent / "escape.txt").exists()

    listing = agent.call("list_directory", path="notes").ok()
    assert [entry["name"] for entry in listing["entries"]] == ["blob.bin", "plan.md"]
    assert listing["total_entries"] == 2
    root = agent.call("list_directory").ok()
    names = [entry["name"] for entry in root["entries"]]
    assert {"blocks", "data", "notes", "workflows"} <= set(names)
    kinds = [entry["type"] for entry in root["entries"]]
    assert kinds == sorted(kinds, key=lambda kind: kind != "directory")  # directories first
    capped = agent.call("list_directory", max_entries=1).ok()
    assert len(capped["entries"]) == 1 and capped["truncated"] is True

    found = agent.call("search_files", path="notes", name_pattern="*.md", content="plate 7").ok()
    assert [hit["path"] for hit in found["hits"]] == ["notes/plan.md"]
    assert found["hits"][0]["line"] == 1
    by_name = agent.call("search_files", name_pattern="normalize_fluorescence.py").ok()
    assert "blocks/normalize_fluorescence.py" in [hit["path"] for hit in by_name["hits"]]

    moved = agent.call("move_path", path="notes/plan.md", destination="notes/archive/plan.md", create_parents=True)
    assert moved.ok()["affected_paths"] == ["deleted:notes/plan.md", "created:notes/archive/plan.md"]
    assert not agent.path("notes/plan.md").exists() and agent.path("notes/archive/plan.md").is_file()
    agent.path("notes/other.md").write_text("other\n", encoding="utf-8")
    assert agent.call("move_path", path="notes/other.md", destination="notes/archive/plan.md").is_error
    assert agent.path("notes/archive/plan.md").read_text(encoding="utf-8") == "normalize plate 7\nthen plot\n"

    assert agent.call("delete_path", path="notes/archive").is_error  # non-empty needs recursive
    assert agent.path("notes/archive/plan.md").exists()
    deleted = agent.call("delete_path", path="notes", recursive=True).ok()
    assert deleted["kind"] == "deleted"
    assert not agent.path("notes").exists()

    # data/ belongs to runs; workflows/*.yaml belong to the workflow tools.
    agent.call("write_file", path="data/raw/extra.csv", content="a,b\n").refused("protected_data_dir")
    agent.call("create_directory", path="data/manual").refused("protected_data_dir")
    agent.call("delete_path", path="data/raw/cell_viability_fluorescence.csv").refused("protected_data_dir")
    agent.call("move_path", path="data/raw", destination="raw").refused("protected_data_dir")
    agent.call("write_file", path="workflows/main.yaml", content="workflow: {}\n").refused("protected_workflow_yaml")
    agent.call("delete_path", path="workflows/main.yaml").refused("protected_workflow_yaml")
    agent.call("patch_file", path="workflows/main.yaml", old_text="norm", new_text="x").refused(
        "protected_workflow_yaml"
    )
    assert not agent.path("data/raw/extra.csv").exists() and not agent.path("data/manual").exists()
    assert agent.path("data/raw/cell_viability_fluorescence.csv").is_file()
    assert agent.path("workflows/main.yaml").is_file()


# ---------------------------------------------------------------------------
# Managed commands.
# ---------------------------------------------------------------------------


def test_managed_commands_run_report_and_cancel(agent: Agent) -> None:
    done = agent.call("run_command", command='echo "project=$SCISTUDIO_PROJECT_DIR"', label="where").ok()
    assert done["state"] == "exited" and done["exit_code"] == 0 and done["running"] is False
    assert done["stdout_tail"].strip() == f"project={agent.project.path}"
    assert Path(done["working_directory"]) == agent.project.path
    assert done["label"] == "where"

    # #2407: a command that started no background process reports none, immediately and later.
    assert done["background_processes_running"] is False, done
    settled = agent.call("get_command_status", job_id=done["job_id"], wait_seconds=10).ok()
    assert settled["state"] == "exited" and settled["exit_code"] == 0
    assert settled["background_processes_running"] is False, settled

    failing = agent.call("run_command", command="exit 3")
    assert failing.is_error  # a non-zero exit reaches the host as an error result
    assert failing.data["status"] == "ok"
    assert failing.data["state"] == "exited" and failing.data["exit_code"] == 3

    sleeper = agent.call("run_command", command="sleep 120", wait_seconds=0.5, label="sleeper").ok()
    assert sleeper["state"] == "running" and sleeper["running"] is True and sleeper["job_id"]
    assert "cancel_command" in sleeper["next_step"]
    assert agent.call("get_command_status", job_id=sleeper["job_id"]).ok()["state"] == "running"
    jobs = {job["job_id"]: job for job in agent.call("list_commands").ok()["jobs"]}
    assert jobs[sleeper["job_id"]]["label"] == "sleeper" and jobs[sleeper["job_id"]]["state"] == "running"
    assert jobs[done["job_id"]]["state"] == "exited"

    stopped = agent.call("cancel_command", job_id=sleeper["job_id"], grace_seconds=1).ok()
    assert stopped["state"] == "cancelled" and stopped["running"] is False
    assert agent.call("get_command_status", job_id=sleeper["job_id"]).ok()["state"] == "cancelled"
    deadline = time.monotonic() + 10
    while psutil.pid_exists(sleeper["pid"]) and psutil.Process(sleeper["pid"]).status() != psutil.STATUS_ZOMBIE:
        assert time.monotonic() < deadline, f"cancelled command pid {sleeper['pid']} is still running"
        time.sleep(0.2)
    # Cancelling a job with nothing left running just reports it.
    assert agent.call("cancel_command", job_id=done["job_id"]).ok()["state"] == "exited"

    agent.call("get_command_status", job_id="no-such-job").refused("unknown_job")
    agent.call("cancel_command", job_id="no-such-job").refused("unknown_job")
    denied = agent.call("run_command", command="scistudio --version").refused("scistudio_cli_denied")
    assert denied["job_id"] is None
    assert "run_workflow" in denied["refusal"]["use_instead"]


# ---------------------------------------------------------------------------
# MiniApps.
# ---------------------------------------------------------------------------

MINIAPP_ID = "table_explorer"

MINIAPP_DESCRIPTOR = {
    "id": MINIAPP_ID,
    "api_version": "1.0",
    "contexts": ["miniapp"],
    "types": ["DataFrame"],
    "name": "Table explorer",
    "description": "Page through the normalized plate table.",
    "entry": "index.html",
}

MINIAPP_PAGE = """<!doctype html>
<meta charset="utf-8">
<title>Table explorer</title>
<link rel="stylesheet" href="../../sdk/1/panel.css">
<script src="../../sdk/1/scistudio-panel.js"></script>
<p id="status" role="status">Loading...</p>
<script>
const api = window.scistudio;
api.ready().then(async () => {
  const page = await api.read("table.page", {page: 1, page_size: 50});
  document.getElementById("status").textContent = `${page.total} rows`;
}).catch(error => api.reportError(error.message || String(error)));
</script>
"""


def write_panel(agent: Agent, directory: str, descriptor: dict[str, Any], page: str | None = MINIAPP_PAGE) -> None:
    agent.call(
        "write_file", path=f"{directory}/panel.json", content=json.dumps(descriptor, indent=2), create_parents=True
    ).ok()
    if page is not None:
        agent.call("write_file", path=f"{directory}/index.html", content=page).ok()


def catalog_ids(agent: Agent) -> set[str]:
    """Panel ids the backend's discovery lists (the MiniApps tab reads this catalog)."""
    return {str(entry["id"]) for entry in agent.backend.call("GET", "/api/panels/catalog")["panels"]}


def test_agent_validates_a_miniapp_directory(agent: Agent) -> None:
    write_panel(agent, f"panels/{MINIAPP_ID}", MINIAPP_DESCRIPTOR)
    result = agent.call("validate_panel", path=f"panels/{MINIAPP_ID}").ok()
    assert Path(result["path"]) == agent.path(f"panels/{MINIAPP_ID}")
    assert result["valid"] is True and result["errors"] == [], result
    assert result["panel_id"] == MINIAPP_ID
    assert result["contexts"] == ["miniapp"]
    assert result["types"] == ["DataFrame"]
    assert result["entry"] == "index.html"
    assert result["has_python"] is False
    # The same directory given as an absolute path inside the project.
    assert agent.call("validate_panel", path=str(agent.path(f"panels/{MINIAPP_ID}"))).ok()["valid"] is True

    # A descriptor whose id differs from its directory is reported, not raised.
    write_panel(agent, "panels/misnamed", dict(MINIAPP_DESCRIPTOR, id="other_name"))
    misnamed = agent.call("validate_panel", path="panels/misnamed").ok()
    assert misnamed["valid"] is False and misnamed["errors"], misnamed
    # An entry page that does not exist.
    write_panel(agent, "panels/no_page", dict(MINIAPP_DESCRIPTOR, id="no_page"), page=None)
    no_page = agent.call("validate_panel", path="panels/no_page").ok()
    assert no_page["valid"] is False and no_page["errors"], no_page
    # A descriptor that is not JSON cannot be parsed at all.
    agent.call("write_file", path="panels/broken/panel.json", content="{not json", create_parents=True).ok()
    agent.call("write_file", path="panels/broken/index.html", content=MINIAPP_PAGE).ok()
    broken = agent.call("validate_panel", path="panels/broken").ok()
    assert broken["valid"] is False and broken["errors"], broken
    assert broken["panel_id"] is None and broken["contexts"] == [], broken
    # errors non-empty means discovery skips the directory; a valid one is discovered.
    # Discovery is checked after an explicit registry reload; that the lists update
    # without one is the separate contract-gap test below (#2421).
    agent.observed["miniapps_before_reload"] = agent.backend.call("GET", "/api/panels/miniapps")["miniapps"]
    agent.backend.reload_registries()
    listed = catalog_ids(agent)
    assert MINIAPP_ID in listed, sorted(listed)
    assert not {"misnamed", "other_name", "no_page", "broken"} & listed, sorted(listed)
    miniapps = {app["panel_id"]: app for app in agent.backend.call("GET", "/api/panels/miniapps")["miniapps"]}
    assert miniapps[MINIAPP_ID]["type"] == "DataFrame", miniapps

    # Raised, per the contract: a path outside the project, and a non-directory.
    agent.call("validate_panel", path=str(agent.serve.home)).raised()
    agent.call("validate_panel", path=f"panels/{MINIAPP_ID}/panel.json").raised()


def test_open_miniapp_reaches_a_connected_workspace_and_says_so_when_none_is(
    agent: Agent, serve: ServeProcess, tutorial_run: dict[str, Any]
) -> None:
    if not agent.path(f"panels/{MINIAPP_ID}/panel.json").is_file():
        write_panel(agent, f"panels/{MINIAPP_ID}", MINIAPP_DESCRIPTOR)
    target = {"panel_id": MINIAPP_ID, "workflow_id": "main", "block_id": "norm", "port": "normalized"}

    # No SciStudio window is connected: nothing opens, and the result says why.
    alone = agent.call("open_miniapp", target).ok()
    assert alone["opened"] is False, alone
    assert alone["reason"] == "no_workspace", alone
    assert {key: alone[key] for key in target} == target
    assert alone["detail"]
    assert "not claim" in alone["next_step"].lower()

    # A connected GUI session receives the request.
    events = EventStream(serve.base_url)
    try:
        opened = agent.call("open_miniapp", target).ok()
        assert opened["opened"] is True, opened
        assert opened["reason"] is None
        assert {key: opened[key] for key in target} == target
        message = events.wait_for(
            lambda m: MINIAPP_ID in json.dumps(m.get("data")),
            what="the open-MiniApp request on the workspace socket",
            timeout=30,
        )
        assert message["type"] == "panel.open_miniapp", message
        assert message["data"] == target, message
    finally:
        events.close()

    # Refusals: an unknown panel id, and a panel that is not a MiniApp.
    agent.call("open_miniapp", dict(target, panel_id="no_such_miniapp")).raised()
    write_panel(
        agent,
        "panels/plate_preview",
        dict(MINIAPP_DESCRIPTOR, id="plate_preview", contexts=["preview"], name="Plate preview"),
    )
    assert agent.call("validate_panel", path="panels/plate_preview").ok()["contexts"] == ["preview"]
    agent.call("open_miniapp", dict(target, panel_id="plate_preview")).raised()


def test_list_miniapps_lists_what_open_miniapp_opens(agent: Agent) -> None:
    write_panel(agent, f"panels/{MINIAPP_ID}", MINIAPP_DESCRIPTOR)
    write_panel(
        agent,
        "panels/plate_preview",
        dict(MINIAPP_DESCRIPTOR, id="plate_preview", contexts=["preview"], name="Plate preview"),
    )
    agent.call("write_file", path="panels/half_written/panel.json", content="{not json", create_parents=True).ok()

    # No registry reload: the tool reads discovery afresh, as open_miniapp does.
    listed = agent.call("list_miniapps").ok()
    apps = {app["panel_id"]: app for app in listed["miniapps"]}
    assert MINIAPP_ID in apps, listed
    assert "plate_preview" not in apps, listed
    app = apps[MINIAPP_ID]
    assert app["name"] == "Table explorer"
    assert app["tier"] == "project" and app["package"] is None
    assert app["types"] == ["DataFrame"]
    assert app["entry"] == "index.html"
    assert app["has_python"] is False
    assert app["path"] == f"panels/{MINIAPP_ID}"
    assert listed["data_type"] is None
    invalid = {entry["panel_id"]: entry for entry in listed["invalid"]}
    assert "half_written" in invalid, listed["invalid"]
    assert invalid["half_written"]["path"] == "panels/half_written"
    assert invalid["half_written"]["diagnostics"], invalid

    # Filtered by the type of the block output a MiniApp would open on.
    tables = agent.call("list_miniapps", data_type="DataFrame").ok()
    assert MINIAPP_ID in {app["panel_id"] for app in tables["miniapps"]}, tables
    assert tables["data_type"] == "DataFrame"
    collections = agent.call("list_miniapps", data_type="Collection[DataFrame]").ok()
    assert MINIAPP_ID not in {app["panel_id"] for app in collections["miniapps"]}, collections

    # Every listed MiniApp is one open_miniapp accepts (no workspace is connected here).
    target = {"workflow_id": "main", "block_id": "norm", "port": "normalized"}
    for panel_id in apps:
        opened = agent.call("open_miniapp", dict(target, panel_id=panel_id)).ok()
        assert opened["panel_id"] == panel_id, opened


def test_screenshot_gui_is_refused_over_the_text_only_webmcp_bridge(agent: Agent) -> None:
    # screenshot_gui needs a connected SciStudio desktop window and local MCP; the
    # external WebMCP host is documented as unsupported (it carries text, not
    # images), and CI has no desktop app. The unsupported contract is what is
    # observable here; test_mcp_transports.py checks the local-MCP refusal.
    for arguments in ({}, {"target": "workspace"}, {"target": "miniapp", "panel_id": MINIAPP_ID, "wait_ms": 0}):
        result = agent.call("screenshot_gui", arguments)
        result.raised()
        assert not [block for block in result.content if block.get("type") == "image"], result.content


# ---------------------------------------------------------------------------
# Tools whose deeper path needs context CI does not have.
# ---------------------------------------------------------------------------


def test_finish_ai_block_outside_an_ai_block_reports_it_is_not_in_one(agent: Agent) -> None:
    # The signal only exists inside a paused AI Agent block, which needs an agent
    # CLI (claude/codex/qoder) running in a PTY tab; CI has none, so the
    # documented not-in-an-AI-block contract is what is observable headlessly.
    result = agent.call("finish_ai_block", outputs={"result": "data/processed/result.csv"}).data
    assert result["status"] == "error"
    assert result["code"] == "not_in_ai_block_context"
    assert "AI Block" in result["message"]
    assert not list(agent.project.path.rglob("finish_ai_block.json"))


# ---------------------------------------------------------------------------
# Documented contracts fixed in #2413 (#2402-#2406, #2408).
# ---------------------------------------------------------------------------


def test_get_run_status_reports_the_outcome_of_failed_and_cancelled_runs(agent: Agent) -> None:
    failed = agent.observed["failed_run_status"]
    cancelled = agent.observed["cancelled_run_status"]
    assert failed["state"] == "failed", failed
    assert cancelled["state"] == "cancelled", cancelled


def test_get_lineage_reaches_the_table_the_block_read(agent: Agent) -> None:
    lineage = agent.observed["lineage"]
    upstream = agent.observed["loaded_ref"]["metadata"]["framework"]["object_id"]
    assert upstream in {node["object_id"] for node in lineage["nodes"]}, lineage
    assert lineage["edges"], lineage


def test_gui_saved_node_config_is_read_as_the_block_params(agent: Agent, tutorial_run: dict[str, Any]) -> None:
    # workflows/main.yaml was saved by the GUI's endpoint, which nests node config
    # under config.params; both core nodes set core_type there and the run used it.
    warnings = tutorial_run["validation"]["warnings"]
    assert not [warning for warning in warnings if "no core_type" in warning], warnings
    load = agent.call("get_block_config", workflow_path="workflows/main.yaml", block_id="load").ok()
    assert load["params"].get("core_type") == "DataFrame", load


def test_list_plot_targets_offers_only_real_output_ports(agent: Agent) -> None:
    registered = {row["type_name"] for row in agent.call("list_blocks").ok()["blocks"]}
    for target in agent.observed["plot_targets"]:
        assert not any("not registered" in note for note in target["diagnostics"]) or (
            target["block_type"] not in registered
        ), target
        schema = agent.call("get_block_schema", type_name=target["block_type"]).ok()
        assert target["output_port"] in [port["name"] for port in schema["ports"]["output"]], target


def test_reload_blocks_reports_the_type_names_it_added(agent: Agent) -> None:
    reload = agent.observed["reload"]
    assert set(reload["new_types"]) <= set(reload["result"]["added"]), reload


def test_validate_workflow_is_invalid_when_it_reports_errors(agent: Agent) -> None:
    unregistered = REVIEW_WORKFLOW.replace("block_type: normalize_fluorescence", "block_type: no_such_block")
    result = agent.call("validate_workflow", yaml_or_path=unregistered).ok()
    assert result["errors"], result
    assert result["valid"] is False, result


# ---------------------------------------------------------------------------
# Documented contracts the product does not meet yet.
# ---------------------------------------------------------------------------


def test_get_block_logs_accepts_the_run_id_run_workflow_returned(agent: Agent, tutorial_run: dict[str, Any]) -> None:
    logs = agent.call("get_block_logs", run_id=tutorial_run["started"]["run_id"], block_id="norm")
    assert not logs.is_error, logs.text
    assert "block_done block_id=norm" in logs.data["stderr"]


def test_get_project_info_lists_recent_runs(agent: Agent, tutorial_run: dict[str, Any]) -> None:
    recent = agent.call("get_project_info").ok()["recent_runs"]
    assert "main" in {row["workflow_id"] for row in recent}, recent


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="a validated MiniApp is missing from the MiniApps list until a manual reload — TODO(#2421)",
)
def test_a_new_miniapp_is_listed_without_a_manual_reload(agent: Agent) -> None:
    before = agent.observed["miniapps_before_reload"]
    assert MINIAPP_ID in [app["panel_id"] for app in before], before


# ---------------------------------------------------------------------------
# Coverage guard.
# ---------------------------------------------------------------------------


def test_every_registered_tool_was_exercised(agent: Agent, request: pytest.FixtureRequest) -> None:
    """Fail when the server registers a tool that nothing in this module dispatched."""
    module_tests = [item for item in request.session.items if item.path == Path(__file__)]
    defined = [name for name, value in globals().items() if name.startswith("test_") and callable(value)]
    if len(module_tests) != len(defined):
        pytest.skip("coverage is only meaningful when the whole module runs")

    catalogue = agent.mcp.catalogue()
    registered = {tool["name"] for tool in catalogue["tools"]}
    missing = sorted(registered - agent.mcp.ledger.called)
    assert not missing, f"registered MCP tools no e2e test exercised: {missing}"
