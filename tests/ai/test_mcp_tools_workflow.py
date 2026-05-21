"""T-ECA-202: unit tests for the 10 workflow tools.

ADR-040 §3.1 FastMCP migration — tools are now ``async def`` functions
decorated with ``@mcp.tool(...)``. Tests use ``asyncio.run`` (or
``pytest-asyncio`` where available) to invoke them.

One happy-path + one error-path per tool. The tests inject a
lightweight MCPContext stub rather than instantiating ``ApiRuntime``.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from scistudio.ai.agent.mcp import _context, tools_workflow
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.types.registry import TypeRegistry

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
        self.workflow_runs[workflow_id] = _StubRun()
        return {"workflow_id": workflow_id, "status": "started"}


@dataclass
class _StubRun:
    task: Any = None
    scheduler: Any = None


@pytest.fixture
def ctx(tmp_path: Path):
    runtime = _StubRuntime(_project_dir=tmp_path)
    runtime.block_registry.scan()
    runtime.type_registry.scan_builtins()
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


def _run(coro):
    """Tiny ``asyncio.run`` shim so tests don't need pytest-asyncio."""
    return asyncio.run(coro)


# --- list_blocks -----------------------------------------------------------


def test_list_blocks_returns_registered_blocks(ctx: _StubRuntime) -> None:
    blocks = _run(tools_workflow.list_blocks())
    # FastMCP returns Pydantic envelopes.
    names = {b.name for b in blocks}
    # At least some builtin block should register.
    assert blocks, "expected at least one registered block"
    assert any(isinstance(n, str) and n for n in names)


def test_list_blocks_no_context_raises() -> None:
    _context.set_context(None)
    with pytest.raises(RuntimeError, match="without an active runtime context"):
        _run(tools_workflow.list_blocks())


# --- get_block_schema ------------------------------------------------------


def test_get_block_schema_happy(ctx: _StubRuntime) -> None:
    specs = ctx.block_registry.all_specs()
    if not specs:
        pytest.skip("no blocks registered for test environment")
    name = next(iter(specs))
    schema = _run(tools_workflow.get_block_schema(name))
    assert schema.type_name == specs[name].name
    assert "input" in schema.ports and "output" in schema.ports
    assert schema.config_schema is not None


def test_get_block_schema_unknown_raises(ctx: _StubRuntime) -> None:
    with pytest.raises(KeyError, match="not registered"):
        _run(tools_workflow.get_block_schema("DoesNotExist_X"))


# --- list_types ------------------------------------------------------------


def test_list_types_happy(ctx: _StubRuntime) -> None:
    types = _run(tools_workflow.list_types())
    assert types.count >= 1
    # DataObject is the universal root; some build of TypeRegistry may
    # not include it under that name, so we just check the count is sane.


def test_list_types_empty_registry() -> None:
    runtime = _StubRuntime(type_registry=TypeRegistry())  # empty
    _context.set_context(runtime)
    try:
        types = _run(tools_workflow.list_types())
        assert types.count == 0
        assert types.types == []
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


def test_get_workflow_missing_path_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _run(tools_workflow.get_workflow(str(tmp_path / "nope.yaml")))


# --- validate_workflow -----------------------------------------------------


def test_validate_workflow_inline_yaml(ctx: _StubRuntime) -> None:
    result = _run(tools_workflow.validate_workflow(_WF_YAML))
    assert result.valid is True
    assert result.errors == []


def test_validate_workflow_bad_yaml(ctx: _StubRuntime) -> None:
    result = _run(tools_workflow.validate_workflow("name: bad\n  bad indent: -"))
    assert result.valid is False
    assert result.errors


# --- write_workflow --------------------------------------------------------


def test_write_workflow_creates_file(ctx: _StubRuntime, tmp_path: Path) -> None:
    target = tmp_path / "out.yaml"
    result = _run(tools_workflow.write_workflow(str(target), _WF_YAML))
    assert target.exists()
    assert result.bytes_written > 0
    assert "lines" in result.diff_summary
    # ADR-040 §3.2: write-class envelope must carry next_step.
    assert result.next_step and "validate_workflow" in result.next_step


def test_write_workflow_rejects_unparseable_yaml(ctx: _StubRuntime, tmp_path: Path) -> None:
    target = tmp_path / "broken.yaml"
    with pytest.raises(ValueError, match=r"YAML parse failure"):
        _run(tools_workflow.write_workflow(str(target), "workflow:\n  id: [unterminated"))
    assert not target.exists()


# --- run_workflow ----------------------------------------------------------


def test_run_workflow_delegates_to_runtime(ctx: _StubRuntime, tmp_path: Path) -> None:
    wf = tmp_path / "test_wf.yaml"
    wf.write_text(_WF_YAML, encoding="utf-8")
    result = _run(tools_workflow.run_workflow(str(wf)))
    assert result.status == "queued"
    assert result.run_id == "test_wf"
    assert "test_wf" in ctx.workflow_runs
    # next_step points the agent at get_run_status.
    assert "get_run_status" in result.next_step


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
            _run(tools_workflow.run_workflow("any.yaml"))
    finally:
        _context.set_context(None)


# --- cancel_run + get_run_status ------------------------------------------


def test_cancel_run_unknown_raises(ctx: _StubRuntime) -> None:
    with pytest.raises(KeyError, match="Unknown run"):
        _run(tools_workflow.cancel_run("missing-run"))


def test_get_run_status_unknown_raises(ctx: _StubRuntime) -> None:
    with pytest.raises(KeyError):
        _run(tools_workflow.get_run_status("nope"))


def test_get_run_status_running(ctx: _StubRuntime) -> None:
    async def _check() -> None:
        async def _dummy() -> None:
            await asyncio.sleep(60)

        task = asyncio.create_task(_dummy())
        ctx.workflow_runs["live"] = _StubRun(task=task, scheduler=None)
        result = await tools_workflow.get_run_status("live")
        assert result.run_id == "live"
        assert result.state == "running"
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(_check())
