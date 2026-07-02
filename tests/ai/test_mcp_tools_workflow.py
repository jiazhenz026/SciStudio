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
from scistudio.engine.events import WORKFLOW_CHANGED

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


class _StubEventBus:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def emit(self, event: Any) -> None:
        self.events.append(event)


class _VersionedStubRuntime(_StubRuntime):
    def __init__(self, project_dir: Path) -> None:
        super().__init__(_project_dir=project_dir)
        self.event_bus = _StubEventBus()
        self.event_bus.runtime = self
        self._versions: dict[str, int] = {}
        self.first_party_writes: list[dict[str, Any]] = []
        self.pending_first_party_writes: list[dict[str, Any]] = []
        self.self_writes: list[Path] = []

    def bump_workflow_version(self, workflow_id: str) -> int:
        version = self._versions.get(workflow_id, 0) + 1
        self._versions[workflow_id] = version
        return version

    def mark_workflow_first_party_write(
        self,
        workflow_id: str,
        version: int,
        *,
        path: Path | None = None,
        kind: str | None = None,
    ) -> None:
        self.first_party_writes.append(
            {
                "workflow_id": workflow_id,
                "version": version,
                "path": path,
                "kind": kind,
            }
        )

    def mark_workflow_self_write(self, path: Path) -> None:
        # #1591: the MCP write tool now routes the FS-watcher self-write through
        # the injected runtime instead of importing api.routes.workflow_watcher.
        self.self_writes.append(path)

    def mark_entity_first_party_write(
        self,
        entity_class: str,
        entity_id: str,
        version: int,
        *,
        path: Path | None = None,
        kind: str | None = None,
        pending: bool = False,
    ) -> None:
        if pending:
            self.pending_first_party_writes.append(
                {
                    "entity_class": entity_class,
                    "entity_id": entity_id,
                    "version": version,
                    "path": path,
                    "kind": kind,
                    "pending": pending,
                }
            )

    def versioned_change_payload(
        self,
        *,
        entity_class: str,
        entity_id: str,
        version: int,
        source: str,
        source_id: str | None,
        kind: str,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "entity_class": entity_class,
            "entity_id": entity_id,
            "version": version,
            "source": source,
            "source_id": source_id,
            "kind": kind,
            **extra,
        }


class _RuntimeAdapterStub(_StubRuntime):
    """Matches the API lifespan adapter shape used by the MCP context."""

    def __init__(self, runtime: _VersionedStubRuntime) -> None:
        super().__init__(
            block_registry=runtime.block_registry,
            type_registry=runtime.type_registry,
            workflow_runs=runtime.workflow_runs,
            _project_dir=runtime.project_dir,
        )
        self.event_bus = runtime.event_bus
        self._runtime = runtime

    def start_workflow(self, workflow_id: str) -> dict[str, Any]:
        return self._runtime.start_workflow(workflow_id)


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
    result = _run(tools_workflow.list_blocks())
    # Lean progressive-disclosure catalog: a ListBlocksResult envelope.
    assert result.blocks, "expected at least one registered block"
    assert result.count == len(result.blocks)
    # next_step must route the agent to the detail tool for full schemas.
    assert "get_block_schema" in result.next_step
    # io_block_guidance steers the agent to the core Load/Save block + core_type
    # rather than a package-specific IO block, for GUI consistency (#1890).
    assert result.io_block_guidance
    assert "core_type" in result.io_block_guidance
    assert "load_data" in result.io_block_guidance and "save_data" in result.io_block_guidance
    names = {b.name for b in result.blocks}
    assert any(isinstance(n, str) and n for n in names)
    sample = result.blocks[0]
    # Catalog entries carry a one-line I/O signature with the arrow separator.
    assert sample.signature and "→" in sample.signature
    # The heavy per-block config_schema must NOT be inlined in the catalog
    # (that is exactly what this change removed; fetch it via get_block_schema).
    assert not hasattr(sample, "config_schema")
    assert not hasattr(sample, "input_ports")
    sigs = [b.signature for b in result.blocks]
    # Signatures must surface concrete accepted_types, not collapse every typed
    # port to ``Any`` (regression guard: types live on ``accepted_types``, not a
    # ``.type`` attribute — see PR #1863 Codex review).
    assert any(":DataObject" in s for s in sigs), "expected a concrete port type in some signature"
    # Variadic blocks must advertise expandability with a ``*:`` marker even
    # when they declare fixed seed ports (e.g. Data Router / Merge Collection).
    variadic = [b for b in result.blocks if b.signature and "*:" in b.signature]
    assert variadic, "expected at least one variadic block to expose a '*:' marker"


def test_list_blocks_no_context_raises() -> None:
    _context.set_context(None)
    with pytest.raises(RuntimeError, match="without an active runtime context"):
        _run(tools_workflow.list_blocks())


# --- get_block_schema ------------------------------------------------------


def test_get_block_schema_happy(ctx: _StubRuntime) -> None:
    specs = ctx.block_registry.all_specs()
    # The ctx fixture calls block_registry.scan(); a regression that registers
    # no blocks must FAIL here rather than silently skip the schema contract
    # under test (#1559).
    assert specs, "ctx fixture scanned the registry but no blocks were registered"
    name = next(iter(specs))
    schema = _run(tools_workflow.get_block_schema(name))
    # get_block_schema returns the canonical type_name (the string that goes
    # into a workflow node's block_type), not the display name (#1900).
    assert schema.type_name == specs[name].type_name
    assert schema.metadata["display_name"] == specs[name].name
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
    # #1910: the file-name stem must equal the workflow's internal id.
    result = _run(tools_workflow.write_workflow(str(target), _WF_YAML.replace("test_wf", "out")))
    assert target.exists()
    assert result.bytes_written > 0
    assert "lines" in result.diff_summary
    # ADR-040 §3.2: write-class envelope must carry next_step.
    assert result.next_step and "validate_workflow" in result.next_step


def test_write_workflow_emits_agent_versioned_change_event(tmp_path: Path) -> None:
    runtime = _VersionedStubRuntime(tmp_path)
    _context.set_context(runtime)
    try:
        target = tmp_path / "workflows" / "agent_edit.yaml"
        # #1910: id must match the file-name stem.
        result = _run(tools_workflow.write_workflow(str(target), _WF_YAML.replace("test_wf", "agent_edit")))
    finally:
        _context.set_context(None)

    assert target.exists()
    assert result.bytes_written > 0
    assert runtime.pending_first_party_writes == [
        {
            "entity_class": "workflow",
            "entity_id": "agent_edit",
            "version": 1,
            "path": target,
            "kind": "created",
            "pending": True,
        }
    ]
    assert runtime.first_party_writes == [
        {
            "workflow_id": "agent_edit",
            "version": 1,
            "path": target,
            "kind": "created",
        }
    ]
    assert len(runtime.event_bus.events) == 1
    event = runtime.event_bus.events[0]
    assert event.event_type == WORKFLOW_CHANGED
    assert event.data["entity_class"] == "workflow"
    assert event.data["entity_id"] == "agent_edit"
    assert event.data["workflow_id"] == "agent_edit"
    assert event.data["version"] == 1
    assert event.data["source"] == "agent"
    assert event.data["source_id"] is None
    assert event.data["kind"] == "created"
    assert event.data["path"] == "workflows/agent_edit.yaml"
    assert event.data["changed_by"] == "mcp.write_workflow"


def test_write_workflow_emits_versioned_event_through_runtime_adapter(tmp_path: Path) -> None:
    runtime = _VersionedStubRuntime(tmp_path)
    adapter = _RuntimeAdapterStub(runtime)
    _context.set_context(adapter)
    try:
        target = tmp_path / "workflows" / "agent_adapter_edit.yaml"
        # #1910: id must match the file-name stem.
        result = _run(tools_workflow.write_workflow(str(target), _WF_YAML.replace("test_wf", "agent_adapter_edit")))
    finally:
        _context.set_context(None)

    assert target.exists()
    assert result.bytes_written > 0
    assert runtime.pending_first_party_writes == [
        {
            "entity_class": "workflow",
            "entity_id": "agent_adapter_edit",
            "version": 1,
            "path": target,
            "kind": "created",
            "pending": True,
        }
    ]
    assert runtime.first_party_writes == [
        {
            "workflow_id": "agent_adapter_edit",
            "version": 1,
            "path": target,
            "kind": "created",
        }
    ]
    assert len(runtime.event_bus.events) == 1
    event = runtime.event_bus.events[0]
    assert event.event_type == WORKFLOW_CHANGED
    assert event.data["entity_id"] == "agent_adapter_edit"
    assert event.data["version"] == 1
    assert event.data["source"] == "agent"
    assert event.data["path"] == "workflows/agent_adapter_edit.yaml"


def test_write_workflow_rejects_unparseable_yaml(ctx: _StubRuntime, tmp_path: Path) -> None:
    target = tmp_path / "broken.yaml"
    with pytest.raises(ValueError, match=r"YAML parse failure"):
        _run(tools_workflow.write_workflow(str(target), "workflow:\n  id: [unterminated"))
    assert not target.exists()


def test_write_workflow_rejects_filename_id_mismatch(ctx: _StubRuntime, tmp_path: Path) -> None:
    """#1910: the file-name stem must exactly equal the workflow's internal id.

    Reproduces the collagen-project failure: a file written as
    ``collagen_srs_pipeline.yaml`` (underscores) while its internal id is
    ``collagen-srs-pipeline`` (hyphens). The runtime resolves a workflow by its
    id to ``workflows/{id}.yaml``, so the divergence breaks run ("Workflow not
    found") and save/import (duplicate-id conflict). The write is refused with an
    actionable message rather than persisted.
    """
    target = tmp_path / "collagen_srs_pipeline.yaml"
    yaml_text = _WF_YAML.replace("test_wf", "collagen-srs-pipeline")
    with pytest.raises(ValueError, match=r"must exactly equal the workflow's internal id"):
        _run(tools_workflow.write_workflow(str(target), yaml_text))
    # Nothing is written when the invariant is violated.
    assert not target.exists()


# --- edit_workflow (#1912) -------------------------------------------------

# A workflow that carries user-set block config + a structural comment. The
# partial-edit tool must preserve everything the edits do not touch.
_WF_WITH_CONFIG = """\
# user comment: do not lose me
workflow:
  id: edit_wf
  version: 1.0.0
  description: original description
  nodes:
    - id: b1
      block_type: load_data
      config:
        core_type: DataFrame
        path: data/raw/in.csv   # user-tuned inline value
  edges: []
"""


def test_edit_workflow_partial_edit_preserves_config_and_comments(ctx: _StubRuntime, tmp_path: Path) -> None:
    target = tmp_path / "workflows" / "edit_wf.yaml"
    _run(tools_workflow.write_workflow(str(target), _WF_WITH_CONFIG))

    result = _run(
        tools_workflow.edit_workflow(
            workflow_path=str(target),
            edits=[{"old_string": "original description", "new_string": "updated description"}],
        )
    )

    text = target.read_text(encoding="utf-8")
    # The targeted edit landed.
    assert "updated description" in text
    assert "original description" not in text
    # Everything untouched survives verbatim: comment, block config, inline note.
    assert "# user comment: do not lose me" in text
    assert "core_type: DataFrame" in text
    assert "path: data/raw/in.csv   # user-tuned inline value" in text
    # Envelope contract.
    assert result.edits_applied == 1
    assert result.bytes_written > 0
    assert Path(result.path).resolve() == target.resolve()
    assert "validate_workflow" in result.next_step


def test_edit_workflow_zero_match_rejected_no_write(ctx: _StubRuntime, tmp_path: Path) -> None:
    target = tmp_path / "workflows" / "edit_wf.yaml"
    _run(tools_workflow.write_workflow(str(target), _WF_WITH_CONFIG))
    before = target.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match=r"not found"):
        _run(
            tools_workflow.edit_workflow(
                workflow_path=str(target),
                edits=[{"old_string": "no such text anywhere", "new_string": "x"}],
            )
        )
    # File is unchanged.
    assert target.read_text(encoding="utf-8") == before


def test_edit_workflow_non_unique_match_rejected(ctx: _StubRuntime, tmp_path: Path) -> None:
    target = tmp_path / "workflows" / "edit_wf.yaml"
    _run(tools_workflow.write_workflow(str(target), _WF_WITH_CONFIG))
    before = target.read_text(encoding="utf-8")

    # "id:" appears more than once (workflow id + node id).
    with pytest.raises(ValueError, match=r"matched .* times"):
        _run(
            tools_workflow.edit_workflow(
                workflow_path=str(target),
                edits=[{"old_string": "id:", "new_string": "id: "}],
            )
        )
    assert target.read_text(encoding="utf-8") == before


def test_edit_workflow_replace_all(ctx: _StubRuntime, tmp_path: Path) -> None:
    target = tmp_path / "workflows" / "edit_wf.yaml"
    _run(tools_workflow.write_workflow(str(target), _WF_WITH_CONFIG))

    # DataFrame -> Series everywhere it appears (schema still valid).
    result = _run(
        tools_workflow.edit_workflow(
            workflow_path=str(target),
            edits=[{"old_string": "DataFrame", "new_string": "Series", "replace_all": True}],
        )
    )
    text = target.read_text(encoding="utf-8")
    assert "DataFrame" not in text
    assert "core_type: Series" in text
    assert result.edits_applied == 1


def test_edit_workflow_multi_edit_atomic_rejects_on_invalid_result(ctx: _StubRuntime, tmp_path: Path) -> None:
    target = tmp_path / "workflows" / "edit_wf.yaml"
    _run(tools_workflow.write_workflow(str(target), _WF_WITH_CONFIG))
    before = target.read_text(encoding="utf-8")

    # First edit is fine, second breaks the schema (removes the required
    # top-level `workflow:` key). The whole batch must roll back — no write.
    with pytest.raises(ValueError, match=r"schema|parse"):
        _run(
            tools_workflow.edit_workflow(
                workflow_path=str(target),
                edits=[
                    {"old_string": "original description", "new_string": "new description"},
                    {"old_string": "workflow:", "new_string": "not_workflow:"},
                ],
            )
        )
    # Atomicity: neither edit persisted.
    assert target.read_text(encoding="utf-8") == before


def test_edit_workflow_missing_file_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=r"not found"):
        _run(
            tools_workflow.edit_workflow(
                workflow_path=str(tmp_path / "workflows" / "nope.yaml"),
                edits=[{"old_string": "a", "new_string": "b"}],
            )
        )


def test_edit_workflow_emits_agent_versioned_change_event(tmp_path: Path) -> None:
    runtime = _VersionedStubRuntime(tmp_path)
    _context.set_context(runtime)
    try:
        target = tmp_path / "workflows" / "edit_wf.yaml"
        _run(tools_workflow.write_workflow(str(target), _WF_WITH_CONFIG))
        # Reset write_workflow's create event so we assert only the edit event.
        runtime.event_bus.events.clear()
        runtime.first_party_writes.clear()
        runtime.pending_first_party_writes.clear()

        result = _run(
            tools_workflow.edit_workflow(
                workflow_path=str(target),
                edits=[{"old_string": "original description", "new_string": "edited"}],
            )
        )
    finally:
        _context.set_context(None)

    assert result.edits_applied == 1
    # The edit bumps the version and emits one modified event.
    assert len(runtime.event_bus.events) == 1
    event = runtime.event_bus.events[0]
    assert event.event_type == WORKFLOW_CHANGED
    assert event.data["entity_id"] == "edit_wf"
    assert event.data["kind"] == "modified"
    assert event.data["source"] == "agent"
    assert event.data["path"] == "workflows/edit_wf.yaml"


def test_edit_workflow_headless_context_still_edits(ctx: _StubRuntime, tmp_path: Path) -> None:
    """A minimal context with no versioned runtime still edits (degrade to no event)."""
    target = tmp_path / "workflows" / "edit_wf.yaml"
    _run(tools_workflow.write_workflow(str(target), _WF_WITH_CONFIG))
    result = _run(
        tools_workflow.edit_workflow(
            workflow_path=str(target),
            edits=[{"old_string": "original description", "new_string": "headless edit"}],
        )
    )
    assert "headless edit" in target.read_text(encoding="utf-8")
    assert result.edits_applied == 1


def test_edit_workflow_empty_edits_rejected(ctx: _StubRuntime, tmp_path: Path) -> None:
    target = tmp_path / "workflows" / "edit_wf.yaml"
    _run(tools_workflow.write_workflow(str(target), _WF_WITH_CONFIG))
    with pytest.raises(ValueError, match=r"at least one edit"):
        _run(tools_workflow.edit_workflow(workflow_path=str(target), edits=[]))


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
