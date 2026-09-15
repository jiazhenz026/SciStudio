"""MCP tool results that disagreed with their contracts (found by the MCP e2e suite).

One regression per issue:

- #2402 ``get_lineage`` walks a block output back to the inputs its execution read.
- #2403 node config saved under ``config.params`` is read as the block's params.
- #2404 ``list_plot_targets`` offers only real output ports.
- #2405 ``reload_blocks`` reports block type names.
- #2406 ``validate_workflow`` is invalid whenever it reports errors.
- #2408 ``get_run_status`` reports failed and cancelled runs as such.

#2407 (``run_command`` background flag) lives with the other execution tests in
``tests/ai/test_mcp_execution_tools.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from scistudio.ai.agent.mcp import _context, tools_authoring, tools_inspection, tools_workflow
from scistudio.blocks.base.state import BlockState
from scistudio.blocks.registry import BlockRegistry
from scistudio.core import metadata_store as metadata_store_module
from scistudio.core.lineage.record import BlockExecutionRecord, BlockIORow, DataObjectRow, RunRecord
from scistudio.core.lineage.store import LineageStore
from scistudio.core.types.registry import TypeRegistry
from scistudio.plot.targets import discover_targets


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


@dataclass
class _StubRuntime:
    block_registry: Any = field(default_factory=BlockRegistry)
    type_registry: Any = field(default_factory=TypeRegistry)
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    lineage_store: Any = None
    active_workflow_id: str | None = None
    _project_dir: Path | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir

    def start_workflow(self, workflow_id: str) -> dict[str, Any]:  # pragma: no cover - presence only
        return {"workflow_id": workflow_id, "status": "started"}


@pytest.fixture
def ctx(tmp_path: Path) -> Iterator[_StubRuntime]:
    runtime = _StubRuntime(_project_dir=tmp_path)
    runtime.block_registry.scan()
    runtime.type_registry.scan_builtins()
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


# ---------------------------------------------------------------------------
# #2408 get_run_status
# ---------------------------------------------------------------------------


class _Scheduler:
    def __init__(self, states: dict[str, BlockState]) -> None:
        self._states = states

    def block_states(self) -> dict[str, BlockState]:
        return dict(self._states)


@dataclass
class _Run:
    task: Any
    scheduler: Any


async def _finished_task() -> asyncio.Task[None]:
    async def _noop() -> None:
        return None

    task = asyncio.create_task(_noop())
    await task
    return task


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        ({"load": BlockState.DONE, "norm": BlockState.ERROR, "save": BlockState.SKIPPED}, "failed"),
        ({"load": BlockState.DONE, "hold": BlockState.CANCELLED}, "cancelled"),
        ({"load": BlockState.DONE, "save": BlockState.DONE}, "succeeded"),
    ],
)
def test_get_run_status_reads_the_outcome_from_the_block_states(
    ctx: _StubRuntime, states: dict[str, BlockState], expected: str
) -> None:
    async def scenario() -> Any:
        ctx.workflow_runs["run"] = _Run(task=await _finished_task(), scheduler=_Scheduler(states))
        return await tools_workflow.get_run_status("run")

    result = _run(scenario())
    assert result.state == expected
    assert result.progress["block_states"] == {block: state.name for block, state in states.items()}


# ---------------------------------------------------------------------------
# #2406 validate_workflow
# ---------------------------------------------------------------------------


_UNREGISTERED = """
workflow:
  name: unregistered
  nodes:
    - id: norm
      block_type: no_such_block
  edges: []
"""


def test_validate_workflow_is_invalid_for_an_unregistered_block_type(ctx: _StubRuntime) -> None:
    result = _run(tools_workflow.validate_workflow(_UNREGISTERED))
    assert result.valid is False
    assert any("no_such_block" in error for error in result.errors), result.errors
    assert not any(error.startswith("Warning:") for error in result.errors), result.errors


def test_validate_workflow_never_returns_errors_on_a_valid_result(ctx: _StubRuntime) -> None:
    result = _run(tools_workflow.validate_workflow("workflow:\n  id: empty\n  nodes: []\n  edges: []\n"))
    assert result.valid is True
    assert result.errors == []


# ---------------------------------------------------------------------------
# #2403 GUI-saved node config under config.params
# ---------------------------------------------------------------------------


_GUI_SAVED = """\
workflow:
  id: main
  version: 1.0.0
  nodes:
    - id: load
      block_type: load_data
      config:
        params:
          core_type: DataFrame
          path: data/table.csv
    - id: save
      block_type: save_data
      config:
        params:
          core_type: DataFrame
          path: data/out.csv
  edges: []
"""


def _write_main(project: Path, text: str) -> str:
    (project / "workflows").mkdir(exist_ok=True)
    (project / "workflows" / "main.yaml").write_text(text, encoding="utf-8")
    return "workflows/main.yaml"


def test_core_type_under_config_params_is_not_reported_missing(ctx: _StubRuntime, tmp_path: Path) -> None:
    path = _write_main(tmp_path, _GUI_SAVED)
    result = _run(tools_workflow.validate_workflow(path))
    assert not [warning for warning in result.warnings if "no core_type" in warning], result.warnings


def test_a_core_node_without_core_type_is_still_reported(ctx: _StubRuntime, tmp_path: Path) -> None:
    without_core_type = _GUI_SAVED.replace(
        "          core_type: DataFrame\n          path: data/t", "          path: data/t"
    )
    path = _write_main(tmp_path, without_core_type)
    result = _run(tools_workflow.validate_workflow(path))
    assert [warning for warning in result.warnings if "node 'load'" in warning and "no core_type" in warning]


def test_get_block_config_returns_the_params_the_block_reads(ctx: _StubRuntime, tmp_path: Path) -> None:
    path = _write_main(tmp_path, _GUI_SAVED)
    result = _run(tools_inspection.get_block_config(workflow_path=path, block_id="load"))
    assert result.params == {"core_type": "DataFrame", "path": "data/table.csv"}


def test_update_block_config_patches_nested_params_in_place(ctx: _StubRuntime, tmp_path: Path) -> None:
    path = _write_main(tmp_path, _GUI_SAVED)
    _run(tools_inspection.update_block_config(workflow_path=path, block_id="load", params={"path": "data/b.csv"}))
    result = _run(tools_inspection.get_block_config(workflow_path=path, block_id="load"))
    assert result.params == {"core_type": "DataFrame", "path": "data/b.csv"}
    saved = yaml.safe_load((tmp_path / path).read_text(encoding="utf-8"))
    load = next(node for node in saved["workflow"]["nodes"] if node["id"] == "load")
    assert load["config"] == {"params": {"core_type": "DataFrame", "path": "data/b.csv"}}


# ---------------------------------------------------------------------------
# #2404 list_plot_targets
# ---------------------------------------------------------------------------


def test_a_registered_sink_block_contributes_no_plot_target(ctx: _StubRuntime, tmp_path: Path) -> None:
    _write_main(tmp_path, _GUI_SAVED)
    targets = discover_targets(ctx)
    assert [target for target in targets if target.node_id == "save"] == []
    assert all("not registered" not in note for target in targets for note in target.diagnostics)
    assert {target.output_port for target in targets if target.node_id == "load"} == {"data"}


def test_an_unregistered_block_is_still_diagnosed(ctx: _StubRuntime, tmp_path: Path) -> None:
    _write_main(tmp_path, _GUI_SAVED.replace("block_type: save_data", "block_type: not_installed_block"))
    targets = [target for target in discover_targets(ctx) if target.node_id == "save"]
    assert len(targets) == 1
    assert any("not registered" in note for note in targets[0].diagnostics)


# ---------------------------------------------------------------------------
# #2405 reload_blocks
# ---------------------------------------------------------------------------


@dataclass
class _Spec:
    name: str
    type_name: str


class _ReloadingRegistry:
    """Keyed by display name, like ``BlockRegistry``; a reload adds one block."""

    def __init__(self) -> None:
        self._specs = {"Load Data": _Spec("Load Data", "load_data")}

    def all_specs(self) -> dict[str, _Spec]:
        return dict(self._specs)

    def hot_reload(self) -> None:
        self._specs["Scale Activity"] = _Spec("Scale Activity", "scaleactivity_block")
        self._specs.pop("Load Data")


class _Types:
    def rescan(self) -> None:
        return None


def test_reload_blocks_reports_type_names() -> None:
    _context.set_context(_StubRuntime(block_registry=_ReloadingRegistry(), type_registry=_Types()))
    try:
        result = _run(tools_authoring.reload_blocks())
    finally:
        _context.set_context(None)
    assert result.added == ["scaleactivity_block"]
    assert result.removed == ["load_data"]


# ---------------------------------------------------------------------------
# #2402 get_lineage
# ---------------------------------------------------------------------------


@pytest.fixture
def lineage(ctx: _StubRuntime) -> Iterator[LineageStore]:
    store = LineageStore(":memory:")
    store.insert_run(
        RunRecord(
            run_id="r1",
            workflow_id="main",
            workflow_yaml_snapshot="id: main\n",
            started_at="2026-09-15T00:00:00Z",
            status="completed",
            environment_snapshot={},
        )
    )
    for execution, block in (("be-load", "load"), ("be-norm", "norm")):
        store.insert_block_execution(
            BlockExecutionRecord(
                block_execution_id=execution,
                run_id="r1",
                block_id=block,
                block_type=block,
                block_version="0.1.0",
                block_config_resolved={},
                started_at="2026-09-15T00:00:01Z",
                termination="completed",
            )
        )
    for object_id, producer in (("obj-loaded", "be-load"), ("obj-normalized", "be-norm")):
        store.upsert_data_object(
            DataObjectRow(
                object_id=object_id,
                type_name="DataFrame",
                wire_payload={"backend": "arrow", "path": f"/p/{object_id}"},
                created_at="2026-09-15T00:00:02Z",
                produced_by_execution=producer,
            )
        )
    store.insert_block_io(BlockIORow("be-load", "output", "data", "obj-loaded"))
    store.insert_block_io(BlockIORow("be-norm", "input", "table", "obj-loaded"))
    store.insert_block_io(BlockIORow("be-norm", "output", "normalized", "obj-normalized"))
    ctx.lineage_store = store
    metadata_store_module.set_metadata_store(metadata_store_module.MetadataStore())
    yield store
    metadata_store_module.set_metadata_store(None)
    store.close()


def test_get_lineage_reaches_the_input_the_block_read(ctx: _StubRuntime, lineage: LineageStore) -> None:
    ref = {"backend": "arrow", "path": "/p/obj-normalized", "metadata": {"framework": {"object_id": "obj-normalized"}}}
    result = _run(tools_inspection.get_lineage(ref=ref))
    by_id = {node.object_id: node for node in result.nodes}
    assert set(by_id) == {"obj-normalized", "obj-loaded"}
    assert by_id["obj-normalized"].block_id == "norm"
    assert by_id["obj-loaded"].block_id == "load"
    assert [(edge.source, edge.target) for edge in result.edges] == [("obj-loaded", "obj-normalized")]
    assert result.note is None
