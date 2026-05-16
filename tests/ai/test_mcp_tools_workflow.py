"""T-ECA-202: unit tests for the 10 workflow tools.

One happy-path + one error-path per tool. The tests inject a
lightweight MCPContext stub rather than instantiating ``ApiRuntime``,
so they run quickly and isolate the tools from FastAPI startup.

# TODO(#1012): module-level skip during ADR-040 §3.1 FastMCP skeleton
#   phase. The workflow tool bodies are NotImplementedError stubs in
#   S40a; I40a Phase 2a restores behavior. Out of scope per ADR-040
#   §3.1 / phase: 2a I40a. Followup: #1012.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.skip(
    reason="S40a skeleton — tool bodies are NotImplementedError stubs. TODO(#1012): I40a Phase 2a restores."
)

from scieasy.ai.agent.mcp import _context, tools_workflow  # noqa: E402
from scieasy.blocks.registry import BlockRegistry  # noqa: E402
from scieasy.core.types.registry import TypeRegistry  # noqa: E402

# --- Stub MCPContext -------------------------------------------------------


@dataclass
class _StubRuntime:
    """Minimal MCPContext stub good enough for the workflow tools."""

    block_registry: BlockRegistry = field(default_factory=BlockRegistry)
    type_registry: TypeRegistry = field(default_factory=TypeRegistry)
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    _project_dir: Path | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir

    def start_workflow(self, workflow_id: str) -> dict[str, Any]:
        # Stub: record the call and return a synthetic queued run.
        self.workflow_runs[workflow_id] = _StubRun()
        return {"workflow_id": workflow_id, "status": "started"}


@dataclass
class _StubRun:
    task: Any = None
    scheduler: Any = None


@pytest.fixture
def ctx(tmp_path: Path) -> _StubRuntime:
    runtime = _StubRuntime(_project_dir=tmp_path)
    runtime.block_registry.scan()
    runtime.type_registry.scan_builtins()
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


# --- list_blocks -----------------------------------------------------------


def test_list_blocks_returns_registered_blocks(ctx: _StubRuntime) -> None:
    blocks = tools_workflow.list_blocks()
    names = {b["name"] for b in blocks}
    assert "LoadData" in names or any("Block" in n for n in names)


def test_list_blocks_no_context_raises() -> None:
    _context.set_context(None)
    with pytest.raises(RuntimeError, match="without an active runtime context"):
        tools_workflow.list_blocks()


# --- get_block_schema ------------------------------------------------------


def test_get_block_schema_happy(ctx: _StubRuntime) -> None:
    # Pick the first registered block.
    specs = ctx.block_registry.all_specs()
    assert specs, "no blocks registered for test"
    name = next(iter(specs))
    schema = tools_workflow.get_block_schema(name)
    assert schema["type_name"] == specs[name].name
    assert "ports" in schema and "config_schema" in schema


def test_get_block_schema_unknown_raises(ctx: _StubRuntime) -> None:
    with pytest.raises(KeyError, match="not registered"):
        tools_workflow.get_block_schema("DoesNotExist_X")


# --- list_types ------------------------------------------------------------


def test_list_types_happy(ctx: _StubRuntime) -> None:
    types = tools_workflow.list_types()
    assert types["count"] >= 1
    assert any(entry["name"] == "DataObject" for entry in types["types"])


def test_list_types_empty_registry() -> None:
    runtime = _StubRuntime(type_registry=TypeRegistry())  # empty
    _context.set_context(runtime)
    try:
        types = tools_workflow.list_types()
        assert types["count"] == 0
        assert types["types"] == []
    finally:
        _context.set_context(None)


# --- get_workflow ----------------------------------------------------------


_WF_YAML = """\
workflow:
  id: test_wf
  version: 1.0.0
  nodes: []
  edges: []
"""


def test_get_workflow_happy(ctx: _StubRuntime, tmp_path: Path) -> None:
    wf = tmp_path / "wf.yaml"
    wf.write_text(_WF_YAML, encoding="utf-8")
    data = tools_workflow.get_workflow(str(wf))
    assert data["id"] == "test_wf"


def test_get_workflow_missing_path_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        tools_workflow.get_workflow(str(tmp_path / "nope.yaml"))


# --- validate_workflow -----------------------------------------------------


def test_validate_workflow_inline_yaml(ctx: _StubRuntime) -> None:
    result = tools_workflow.validate_workflow(_WF_YAML)
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_workflow_bad_yaml(ctx: _StubRuntime) -> None:
    result = tools_workflow.validate_workflow("name: bad\n  bad indent: -")
    assert result["valid"] is False
    assert result["errors"]


# --- write_workflow --------------------------------------------------------


def test_write_workflow_creates_file(ctx: _StubRuntime, tmp_path: Path) -> None:
    target = tmp_path / "out.yaml"
    result = tools_workflow.write_workflow(str(target), _WF_YAML)
    assert target.exists()
    assert result["bytes_written"] > 0
    assert "lines" in result["diff_summary"]


def test_write_workflow_overwrites_existing(ctx: _StubRuntime, tmp_path: Path) -> None:
    target = tmp_path / "out.yaml"
    target.write_text("# placeholder\n", encoding="utf-8")
    tools_workflow.write_workflow(str(target), _WF_YAML)
    assert "# placeholder" not in target.read_text(encoding="utf-8")


def test_write_workflow_rejects_malformed_yaml(ctx: _StubRuntime, tmp_path: Path) -> None:
    """A YAML that fails ``WorkflowFileModel`` validation must NOT be written.

    Regression for the agent → 4-field-edges → GUI 500 chain. With
    pre-write validation in place, the agent now receives the structured
    pydantic error immediately and the bad file never reaches disk.
    """
    target = tmp_path / "bad.yaml"
    bad_yaml = """\
workflow:
  id: bad-edges
  version: "1.0.0"
  nodes:
    - id: a
      block_type: io_block
    - id: b
      block_type: process_block
  edges:
    - source: a
      source_port: out
      target: b
      target_port: in
"""
    with pytest.raises(ValueError, match=r"refusing to write"):
        tools_workflow.write_workflow(str(target), bad_yaml)
    assert not target.exists(), "Malformed YAML must not be persisted"


def test_write_workflow_rejects_unparseable_yaml(ctx: _StubRuntime, tmp_path: Path) -> None:
    """A YAML that isn't even parseable produces a structured error,
    not an opaque server exception."""
    target = tmp_path / "broken.yaml"
    with pytest.raises(ValueError, match=r"YAML parse failure"):
        tools_workflow.write_workflow(str(target), "workflow:\n  id: [unterminated")
    assert not target.exists()


# --- run_workflow ----------------------------------------------------------


def test_run_workflow_delegates_to_runtime(ctx: _StubRuntime, tmp_path: Path) -> None:
    wf = tmp_path / "test_wf.yaml"
    wf.write_text(_WF_YAML, encoding="utf-8")
    result = tools_workflow.run_workflow(str(wf))
    assert result["status"] == "queued"
    assert result["run_id"] == "test_wf"
    assert "test_wf" in ctx.workflow_runs


def test_run_workflow_no_start_method_raises() -> None:
    class _PoorRuntime:
        block_registry = BlockRegistry()
        type_registry = TypeRegistry()

        @property
        def project_dir(self) -> Path | None:
            return None

    _context.set_context(_PoorRuntime())
    try:
        with pytest.raises(RuntimeError, match="start_workflow"):
            tools_workflow.run_workflow("any.yaml")
    finally:
        _context.set_context(None)


# --- cancel_run + get_run_status ------------------------------------------


def test_cancel_run_unknown_raises(ctx: _StubRuntime) -> None:
    with pytest.raises(KeyError, match="Unknown run"):
        tools_workflow.cancel_run("missing-run")


def test_cancel_run_happy(ctx: _StubRuntime) -> None:
    # Inject a fake run with a cancellable task.
    async def _dummy() -> None:
        await asyncio.sleep(60)

    async def _cancel() -> None:
        task = asyncio.create_task(_dummy())
        ctx.workflow_runs["r1"] = _StubRun(task=task, scheduler=None)
        result = tools_workflow.cancel_run("r1")
        assert result["cancel_requested"] is True
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(_cancel())


def test_get_run_status_unknown_raises(ctx: _StubRuntime) -> None:
    with pytest.raises(KeyError):
        tools_workflow.get_run_status("nope")


def test_get_run_status_running(ctx: _StubRuntime) -> None:
    async def _check() -> None:
        async def _dummy() -> None:
            await asyncio.sleep(60)

        task = asyncio.create_task(_dummy())
        ctx.workflow_runs["live"] = _StubRun(task=task, scheduler=None)
        result = tools_workflow.get_run_status("live")
        assert result["run_id"] == "live"
        assert result["state"] == "running"
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(_check())
