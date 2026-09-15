"""#2401 / #2433 — the MCP run tools agree on what a run id is.

``run_workflow`` returned the workflow id as ``run_id``, so ``get_block_logs``
could never find ``run-<uuid>.log``, ``get_run_status`` refused the id the run
history records, and ``cancel_run`` acted on whatever run of the workflow was
latest — including the user's own GUI run. ``get_project_info.recent_runs``
stayed empty. The run tools now take the real run id (and still accept a
workflow id as "that workflow's latest run").
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scistudio.ai.agent.mcp import _context, tools_inspection, tools_qa, tools_workflow
from scistudio.ai.agent.mcp.tools_workflow import _errors
from scistudio.core.lineage.record import RunRecord
from scistudio.core.lineage.store import LineageStore
from scistudio.engine.events import CANCEL_WORKFLOW_REQUEST
from scistudio.engine.run_logging import run_log_context

_WF_YAML = """\
workflow:
  id: main
  version: 1.0.0
  nodes: []
  edges: []
"""


class _DoneTask:
    def done(self) -> bool:
        return True

    def cancelled(self) -> bool:
        return False

    def exception(self) -> BaseException | None:
        return None


class _RecordingBus:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def emit(self, event: Any) -> None:
        self.events.append(event)


@dataclass
class _Run:
    run_id: str
    task: Any = field(default_factory=_DoneTask)
    scheduler: Any = None


@dataclass
class _Runtime:
    _project_dir: Path
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    block_registry: Any = None
    type_registry: Any = None
    started: int = 0

    @property
    def project_dir(self) -> Path:
        return self._project_dir

    def start_workflow(self, workflow_id: str) -> dict[str, Any]:
        self.started += 1
        run_id = f"run-{self.started}"
        self.workflow_runs[workflow_id] = _Run(run_id=run_id)
        return {"workflow_id": workflow_id, "run_id": run_id, "status": "started"}


@pytest.fixture
def ctx(tmp_path: Path) -> Iterator[_Runtime]:
    runtime = _Runtime(_project_dir=tmp_path)
    _context.set_context(runtime)
    _errors._run_block_errors.clear()
    yield runtime
    _errors._run_block_errors.clear()
    _context.set_context(None)


def _write_workflow(project: Path) -> None:
    (project / "workflows").mkdir(exist_ok=True)
    (project / "workflows" / "main.yaml").write_text(_WF_YAML, encoding="utf-8")


def test_run_workflow_returns_the_runs_own_id(ctx: _Runtime, tmp_path: Path) -> None:
    _write_workflow(tmp_path)

    first = asyncio.run(tools_workflow.run_workflow("workflows/main.yaml"))
    second = asyncio.run(tools_workflow.run_workflow("workflows/main.yaml"))

    assert first.run_id == "run-1"
    assert second.run_id == "run-2"
    assert "run_id=run-2" in second.poll_hint


def test_get_run_status_accepts_the_run_id_and_the_workflow_id(ctx: _Runtime) -> None:
    ctx.workflow_runs["main"] = _Run(run_id="run-9")

    by_run = asyncio.run(tools_workflow.get_run_status("run-9"))
    by_workflow = asyncio.run(tools_workflow.get_run_status("main"))

    assert by_run.run_id == by_workflow.run_id == "run-9"
    assert by_run.state == "succeeded"
    with pytest.raises(KeyError, match="Unknown run"):
        asyncio.run(tools_workflow.get_run_status("run-8"))


def test_get_run_status_reports_only_this_runs_errors(ctx: _Runtime) -> None:
    ctx.workflow_runs["main"] = _Run(run_id="run-9")
    _errors._run_block_errors[("run-8", "load")] = {"error": "old", "summary": None, "workflow_id": "main"}
    _errors._run_block_errors[("run-9", "load")] = {"error": "new", "summary": None, "workflow_id": "main"}

    status = asyncio.run(tools_workflow.get_run_status("run-9"))

    assert [entry.error for entry in status.errors] == ["new"]


def test_cancel_run_is_addressed_to_exactly_that_run(ctx: _Runtime) -> None:
    bus = _RecordingBus()

    class _Scheduler:
        _event_bus = bus

    ctx.workflow_runs["main"] = _Run(run_id="run-9", scheduler=_Scheduler())

    async def cancel() -> Any:
        result = await tools_workflow.cancel_run("run-9")
        await asyncio.sleep(0)
        return result

    result = asyncio.run(cancel())

    assert result.run_id == "run-9"
    (event,) = bus.events
    assert event.event_type == CANCEL_WORKFLOW_REQUEST
    assert event.data == {"workflow_id": "main", "run_id": "run-9"}


def test_get_block_output_resolves_the_run_id(ctx: _Runtime) -> None:
    scheduler = SimpleNamespace(
        _block_outputs={"load": {"out": {"path": "/x", "metadata": {"type_chain": ["DataObject", "Text"]}}}}
    )
    ctx.workflow_runs["main"] = _Run(run_id="run-9", scheduler=scheduler)

    output = asyncio.run(tools_inspection.get_block_output(run_id="run-9", block_id="load", port="out"))

    assert output.type.type_name == "Text"
    with pytest.raises(KeyError, match="Unknown run"):
        asyncio.run(tools_inspection.get_block_output(run_id="run-1", block_id="load", port="out"))


def test_get_block_logs_reads_the_run_log_run_workflow_named(ctx: _Runtime, tmp_path: Path) -> None:
    """The chain run_workflow -> get_block_logs works with the returned id or the workflow id."""
    ctx.workflow_runs["main"] = _Run(run_id="5ba1f3df")
    with run_log_context("5ba1f3df", project_root=tmp_path):
        logging.getLogger("scistudio.test").warning("worker[%s] %s", "norm", "normalised 12 rows")

    by_run = asyncio.run(tools_inspection.get_block_logs(run_id="5ba1f3df", block_id="norm"))
    by_workflow = asyncio.run(tools_inspection.get_block_logs(run_id="main", block_id="norm"))

    assert "normalised 12 rows" in by_run.stderr
    assert by_workflow.stderr == by_run.stderr


def test_get_block_logs_filters_by_the_exact_block_id(ctx: _Runtime, tmp_path: Path) -> None:
    with run_log_context("run-exact", project_root=tmp_path):
        log = logging.getLogger("scistudio.test")
        log.warning("worker[%s] %s", "load", "from load")
        log.warning("worker[%s] %s", "load_2", "from load_2")
        log.warning("block_done block_id=%s workflow_id=main", "load_2")

    logs = asyncio.run(tools_inspection.get_block_logs(run_id="run-exact", block_id="load"))

    assert "from load" in logs.stderr
    assert "load_2" not in logs.stderr


def test_get_block_logs_finds_a_code_blocks_exchange_folder_by_run_id(ctx: _Runtime, tmp_path: Path) -> None:
    """The scheduler hands the run id to the block, so its exchange folder is named by it."""
    from scistudio.blocks.base.config import BlockConfig
    from scistudio.blocks.code.code_block import CodeBlock

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "chatty.py").write_text("print('rows: 12')\n", encoding="utf-8")
    config = BlockConfig(
        params={"script_path": "scripts/chatty.py", "project_dir": str(tmp_path)},
        block_id="code_block-1",
        workflow_id="main",
        run_id="run-code",  # injected by the scheduler beside block_id / workflow_id
    )
    CodeBlock().run({}, config)
    ctx.workflow_runs["main"] = _Run(run_id="run-code")

    logs = asyncio.run(tools_inspection.get_block_logs(run_id="main", block_id="code_block-1"))

    assert logs.source == "codeblock_exchange"
    assert "rows: 12" in logs.stdout


def test_get_project_info_lists_recent_runs(ctx: _Runtime, tmp_path: Path) -> None:
    (tmp_path / "project.yaml").write_text("project:\n  name: Demo\n", encoding="utf-8")
    (tmp_path / ".scistudio").mkdir()
    store = LineageStore(str(tmp_path / ".scistudio" / "lineage.db"))
    try:
        for run_id, started, status in (
            ("run-a", "2026-09-15T01:00:00", "completed"),
            ("run-b", "2026-09-15T02:00:00", "failed"),
        ):
            store.insert_run(
                RunRecord(
                    run_id=run_id,
                    workflow_id="main",
                    workflow_yaml_snapshot="",
                    started_at=started,
                    status="running",
                    environment_snapshot={},
                )
            )
            store.finalize_run(run_id, finished_at=started, status=status)
    finally:
        store.close()

    info = asyncio.run(tools_qa.get_project_info())

    assert [(entry.run_id, entry.state) for entry in info.recent_runs] == [("run-b", "failed"), ("run-a", "succeeded")]
