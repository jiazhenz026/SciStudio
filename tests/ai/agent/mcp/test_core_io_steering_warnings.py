"""Core-IO steering warnings across the agent workflow MCP tools (#2376).

The agent must be told, without blocking, when a workflow bypasses the core
``load_data`` / ``save_data`` block:

1. a package-specific IO block (``scistudio_blocks_*``);
2. a custom (project drop-in / scaffolded) IO block whose data type the core
   block covers with a registered format capability;
3. a core ``load_data`` / ``save_data`` node without ``core_type``.

The warnings surface from ``write_workflow``, ``edit_workflow``,
``update_block_config``, ``validate_workflow``, and from ``scaffold_block``
for an ``io`` category scaffold.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from scistudio.ai.agent.mcp import _context, tools_authoring, tools_inspection, tools_workflow
from scistudio.ai.agent.mcp.tools_workflow._helpers import (
    _core_io_covered_types,
    _core_io_steering_warnings,
    _scaffold_io_steering_warning,
)
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.registry import BlockRegistry, BlockSpec
from scistudio.core.types.array import Array
from scistudio.core.types.base import DataObject
from scistudio.core.types.registry import TypeRegistry


class _UncoveredWidget(DataObject):
    """A data type with no core Load/Save format capability."""


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@dataclass
class _StubRuntime:
    block_registry: BlockRegistry = field(default_factory=BlockRegistry)
    type_registry: TypeRegistry = field(default_factory=TypeRegistry)
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    _project_dir: Path | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir

    def start_workflow(self, workflow_id: str) -> dict[str, Any]:
        self.workflow_runs[workflow_id] = object()
        return {"workflow_id": workflow_id, "status": "started"}


@pytest.fixture
def ctx(tmp_path: Path):
    root = (tmp_path / "proj").resolve()
    root.mkdir()
    (root / "workflows").mkdir()
    runtime = _StubRuntime(_project_dir=root)
    runtime.block_registry.scan()
    runtime.type_registry.scan_builtins()
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


def _register_io(
    registry: BlockRegistry,
    *,
    type_name: str,
    module_path: str,
    data_type: type[DataObject] = Array,
    direction: str = "input",
) -> None:
    """Inject a synthetic IO block spec (loader when direction='input')."""
    is_loader = direction == "input"
    port = (
        OutputPort(name="data", accepted_types=[data_type])
        if is_loader
        else InputPort(name="data", accepted_types=[data_type])
    )
    spec = BlockSpec(
        name=type_name,
        type_name=type_name,
        base_category="io",
        module_path=module_path,
        direction=direction,
        input_ports=[] if is_loader else [port],
        output_ports=[port] if is_loader else [],
    )
    registry._registry[spec.name] = spec
    registry._aliases[spec.type_name] = spec.name


def _wf_yaml(block_type: str, config: str = "{}", wf_id: str = "steer") -> str:
    return (
        "workflow:\n"
        f"  id: {wf_id}\n"
        "  version: 1.0.0\n"
        "  nodes:\n"
        "    - id: n1\n"
        f"      block_type: {block_type}\n"
        f"      config: {config}\n"
        "  edges: []\n"
    )


def _non_io_type_name(registry: BlockRegistry) -> str:
    return next(
        spec.type_name
        for spec in registry.all_specs().values()
        if spec.type_name and spec.base_category not in ("io", "")
    )


# ---------------------------------------------------------------------------
# Central helper: the three cases and their negatives
# ---------------------------------------------------------------------------


def test_covered_types_follow_core_capabilities(ctx: _StubRuntime) -> None:
    covered = _core_io_covered_types(ctx.block_registry, ctx.type_registry, direction="load")
    assert "Array" in covered
    assert "DataFrame" in covered
    # Registered but not loadable by the core block: not covered.
    assert "DataObject" not in covered


def test_package_io_block_warns(ctx: _StubRuntime) -> None:
    _register_io(ctx.block_registry, type_name="fake.load_thing", module_path="scistudio_blocks_fake.io.load_thing")
    warnings = _core_io_steering_warnings([{"id": "n1", "block_type": "fake.load_thing", "config": {}}])
    assert len(warnings) == 1
    assert warnings[0].startswith("node 'n1':")
    assert "package-specific" in warnings[0]
    assert "core_type='Array'" in warnings[0]


def test_custom_loader_for_covered_type_warns(ctx: _StubRuntime) -> None:
    _register_io(ctx.block_registry, type_name="my_load_array", module_path="blocks.my_load_array")
    warnings = _core_io_steering_warnings([{"id": "src", "block_type": "my_load_array", "config": {}}])
    assert len(warnings) == 1
    assert warnings[0].startswith("node 'src':")
    assert "custom IO block" in warnings[0]
    assert "'load_data'" in warnings[0]
    assert "core_type='Array'" in warnings[0]


def test_custom_saver_for_covered_type_points_at_save_data(ctx: _StubRuntime) -> None:
    _register_io(ctx.block_registry, type_name="my_save_array", module_path="blocks.my_save_array", direction="output")
    warnings = _core_io_steering_warnings([{"id": "out", "block_type": "my_save_array", "config": {}}])
    assert len(warnings) == 1
    assert "'save_data'" in warnings[0]
    assert "core_type='Array'" in warnings[0]


def test_custom_io_block_for_uncovered_type_does_not_warn(ctx: _StubRuntime) -> None:
    _register_io(
        ctx.block_registry,
        type_name="my_load_widget",
        module_path="blocks.my_load_widget",
        data_type=_UncoveredWidget,
    )
    assert _core_io_steering_warnings([{"id": "n1", "block_type": "my_load_widget", "config": {}}]) == []


@pytest.mark.parametrize("block_type", ["load_data", "save_data"])
@pytest.mark.parametrize("config", [{}, {"core_type": None}, {"core_type": "  "}, None])
def test_core_io_without_core_type_warns(ctx: _StubRuntime, block_type: str, config: Any) -> None:
    warnings = _core_io_steering_warnings([{"id": "n1", "block_type": block_type, "config": config}])
    assert len(warnings) == 1
    assert warnings[0].startswith("node 'n1':")
    assert "core_type" in warnings[0]
    assert f"get_block_schema('{block_type}')" in warnings[0]


def test_core_io_with_core_type_does_not_warn(ctx: _StubRuntime) -> None:
    nodes = [
        {"id": "a", "block_type": "load_data", "config": {"core_type": "Array"}},
        {"id": "b", "block_type": "save_data", "config": {"core_type": "DataFrame"}},
    ]
    assert _core_io_steering_warnings(nodes) == []


def test_non_io_block_does_not_warn(ctx: _StubRuntime) -> None:
    block_type = _non_io_type_name(ctx.block_registry)
    assert _core_io_steering_warnings([{"id": "n1", "block_type": block_type, "config": {}}]) == []


# ---------------------------------------------------------------------------
# Surfacing tools
# ---------------------------------------------------------------------------


def test_write_workflow_warns_on_core_load_without_core_type(ctx: _StubRuntime) -> None:
    result = _run(tools_workflow.write_workflow("workflows/steer.yaml", _wf_yaml("load_data")))
    assert result.bytes_written > 0
    assert len(result.warnings) == 1
    assert "core_type" in result.warnings[0]


def test_write_workflow_warns_on_custom_io_block(ctx: _StubRuntime) -> None:
    _register_io(ctx.block_registry, type_name="my_load_array", module_path="blocks.my_load_array")
    result = _run(tools_workflow.write_workflow("workflows/steer.yaml", _wf_yaml("my_load_array")))
    assert result.bytes_written > 0
    assert len(result.warnings) == 1
    assert "custom IO block" in result.warnings[0]


def test_edit_workflow_returns_warnings(ctx: _StubRuntime) -> None:
    _run(tools_workflow.write_workflow("workflows/steer.yaml", _wf_yaml("load_data", "{core_type: Array}")))
    _register_io(ctx.block_registry, type_name="fake.load_thing", module_path="scistudio_blocks_fake.io.load_thing")
    result = _run(
        tools_workflow.edit_workflow(
            "workflows/steer.yaml",
            [{"old_string": "block_type: load_data", "new_string": "block_type: fake.load_thing"}],
        )
    )
    assert result.edits_applied == 1
    assert len(result.warnings) == 1
    assert "package-specific" in result.warnings[0]


def test_edit_workflow_clean_edit_has_no_warnings(ctx: _StubRuntime) -> None:
    _run(tools_workflow.write_workflow("workflows/steer.yaml", _wf_yaml("load_data", "{core_type: Array}")))
    result = _run(
        tools_workflow.edit_workflow(
            "workflows/steer.yaml",
            [{"old_string": "core_type: Array", "new_string": "core_type: DataFrame"}],
        )
    )
    assert result.warnings == []


def test_update_block_config_warns_when_core_type_cleared(ctx: _StubRuntime) -> None:
    _run(tools_workflow.write_workflow("workflows/steer.yaml", _wf_yaml("load_data", "{core_type: Array}")))
    result = _run(tools_inspection.update_block_config("workflows/steer.yaml", "n1", {"core_type": ""}))
    assert len(result.warnings) == 1
    assert result.warnings[0].startswith("node 'n1':")
    assert "core_type" in result.warnings[0]


def test_update_block_config_with_core_type_has_no_warnings(ctx: _StubRuntime) -> None:
    _run(tools_workflow.write_workflow("workflows/steer.yaml", _wf_yaml("load_data")))
    result = _run(tools_inspection.update_block_config("workflows/steer.yaml", "n1", {"core_type": "Array"}))
    assert result.warnings == []


def test_validate_workflow_reports_warnings_without_changing_validity(ctx: _StubRuntime) -> None:
    inline = _wf_yaml("load_data", "{path: data.csv}")
    result = _run(tools_workflow.validate_workflow(inline))
    assert len(result.warnings) == 1
    assert "core_type" in result.warnings[0]
    assert not any("core_type" in err and "silently" in err for err in result.errors)


def test_validate_workflow_configured_load_has_no_warnings(ctx: _StubRuntime) -> None:
    result = _run(tools_workflow.validate_workflow(_wf_yaml("load_data", "{path: data.csv, core_type: DataFrame}")))
    assert result.warnings == []


# ---------------------------------------------------------------------------
# scaffold_block
# ---------------------------------------------------------------------------


def test_scaffold_io_warning_helper_cases(ctx: _StubRuntime) -> None:
    covered = _scaffold_io_steering_warning({}, {"data": {"type": "Array"}})
    assert covered is not None
    assert "'load_data'" in covered
    assert "core_type='Array'" in covered
    saver = _scaffold_io_steering_warning({"data": {"type": "DataFrame"}}, {})
    assert saver is not None
    assert "'save_data'" in saver
    assert _scaffold_io_steering_warning({}, {"data": {"type": "NotACoreType"}}) is None
    generic = _scaffold_io_steering_warning({}, {})
    assert generic is not None
    assert "core_type" in generic


def test_scaffold_block_io_category_warns(ctx: _StubRuntime) -> None:
    result = _run(
        tools_authoring.scaffold_block(
            name="my_array_loader",
            category="io",
            input_ports=None,
            output_ports={"data": {"type": "Array"}},
        )
    )
    assert any("core 'load_data'" in w and "core_type='Array'" in w for w in result.warnings)


def test_scaffold_block_process_category_has_no_io_warning(ctx: _StubRuntime) -> None:
    result = _run(
        tools_authoring.scaffold_block(
            name="my_array_filter",
            category="process",
            input_ports={"data": {"type": "Array"}},
            output_ports={"data": {"type": "Array"}},
        )
    )
    assert not any("load_data" in w or "save_data" in w for w in result.warnings)
