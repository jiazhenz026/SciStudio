"""ADR-044 integration — flattened DAG reaches the scheduler; lineage snapshot.

Covers SC-001 (no SubWorkflowBlock reaches the scheduler — the dispatched DAG
contains only the prefixed inner nodes) and SC-002 (``RunRecord.workflow_yaml_
snapshot`` equals the *flattened* YAML, not the authored on-disk file that still
holds the SubWorkflowBlock reference).
"""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from scistudio.api.runtime import ApiRuntime
from scistudio.blocks.base.state import BlockState
from scistudio.engine.events import EventBus
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.flatten import SUBWORKFLOW_TYPE, flatten_subworkflows
from scistudio.workflow.serializer import dump_yaml_str, load_yaml

_CHILD = """
workflow:
  id: child
  nodes:
    - id: load
      block_type: mock_block
      config: {}
    - id: proc
      block_type: mock_block
      config: {}
  edges:
    - source: "load:out"
      target: "proc:in"
  exposed_ports:
    inputs:
      - name: raw_in
        internal: load.in
    outputs:
      - name: report
        internal: proc.out
"""

_PARENT = """
workflow:
  id: parent
  nodes:
    - id: sw1
      block_type: subworkflow_block
      config:
        ref:
          path: subworkflows/child.yaml
  edges: []
"""


def _seed(project: Path) -> None:
    (project / "subworkflows").mkdir(parents=True, exist_ok=True)
    (project / "subworkflows" / "child.yaml").write_text(textwrap.dedent(_CHILD), encoding="utf-8")
    (project / "workflows").mkdir(parents=True, exist_ok=True)
    (project / "workflows" / "parent.yaml").write_text(textwrap.dedent(_PARENT), encoding="utf-8")


def test_scheduler_only_sees_flattened_nodes(tmp_path: Path) -> None:
    """SC-001: the flattened DAG that reaches the real scheduler has no SubWorkflowBlock."""
    _seed(tmp_path)
    parent = load_yaml(tmp_path / "workflows" / "parent.yaml")
    flat = flatten_subworkflows(parent, base_dir=tmp_path, self_path=tmp_path / "workflows" / "parent.yaml")

    assert {n.id for n in flat.nodes} == {"sw1__load", "sw1__proc"}
    assert all(n.block_type != SUBWORKFLOW_TYPE for n in flat.nodes)

    dispatched_ids: list[str] = []

    async def mock_run(block: Any, inputs: dict, config: dict) -> dict:
        dispatched_ids.append(block.id)
        return {"out": "ok"}

    runner = MagicMock()
    runner.run = AsyncMock(side_effect=mock_run)
    resource_mgr = MagicMock()
    resource_mgr.can_dispatch.return_value = True
    proc_reg = MagicMock()
    proc_reg.get_handle.return_value = None

    scheduler = DAGScheduler(
        workflow=flat,
        event_bus=EventBus(),
        resource_manager=resource_mgr,
        process_registry=proc_reg,
        runner=runner,
    )
    asyncio.run(scheduler.execute())

    assert sorted(dispatched_ids) == ["sw1__load", "sw1__proc"]
    assert scheduler._block_states["sw1__load"] == BlockState.DONE
    assert scheduler._block_states["sw1__proc"] == BlockState.DONE


def test_lineage_snapshot_uses_flattened_yaml(runtime: ApiRuntime, opened_project: Path) -> None:
    """SC-002: the snapshot for a flattened run is the flat YAML, not the on-disk parent."""
    _seed(opened_project)
    parent = runtime.load_workflow("parent")
    flat = flatten_subworkflows(parent, base_dir=opened_project, self_path=runtime.workflow_path("parent"))
    expected = dump_yaml_str(flat)

    # Flattened path: serialise the in-memory flat DAG.
    flattened_snapshot = runtime._serialise_workflow_snapshot("parent", flat, prefer_inmemory=True)
    assert flattened_snapshot == expected
    assert "subworkflow_block" not in flattened_snapshot
    assert "sw1__load" in flattened_snapshot and "sw1__proc" in flattened_snapshot

    # Non-flattened path still reads the authored on-disk file (which DOES hold
    # the SubWorkflowBlock reference) — proving the flag is what makes SC-002 hold.
    disk_snapshot = runtime._serialise_workflow_snapshot("parent", parent, prefer_inmemory=False)
    assert "subworkflow_block" in disk_snapshot


def test_lineage_recorder_persists_flattened_snapshot(runtime: ApiRuntime, opened_project: Path) -> None:
    """SC-002 end-to-end: the RunRecord written by the recorder holds the flat YAML."""
    if runtime.lineage_store is None:
        pytest.skip("lineage store unavailable in this runtime")
    _seed(opened_project)
    parent = runtime.load_workflow("parent")
    flat = flatten_subworkflows(parent, base_dir=opened_project, self_path=runtime.workflow_path("parent"))

    recorder = runtime._build_lineage_recorder(
        workflow_id="parent",
        workflow=flat,
        execute_from=None,
        flattened=True,
    )
    assert recorder is not None

    runs = runtime.lineage_store.list_runs(workflow_id="parent")
    assert runs, "expected a runs row to be recorded"
    snapshot = runs[0]["workflow_yaml_snapshot"]
    assert "subworkflow_block" not in snapshot
    assert "sw1__load" in snapshot and "sw1__proc" in snapshot
