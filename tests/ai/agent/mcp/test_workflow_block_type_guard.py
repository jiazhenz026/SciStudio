"""Block-type surfacing + write-time guard for the agent workflow tools (#1900).

Two agent-authoring failure modes are covered:

* ``list_blocks`` / ``get_block_schema`` must surface the canonical
  ``type_name`` (the string that belongs in a node's ``block_type``) rather
  than only the display name, and must flag package-specific IO blocks with a
  ``use_instead`` redirect to the core Load/Save block.
* ``write_workflow`` must hard-fail a node whose ``block_type`` is not a
  registered ``type_name`` (the GUI resolves nodes by ``type_name``), and must
  emit a non-blocking warning — not a failure — when a node uses a
  package-specific IO block the core block already covers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from scistudio.ai.agent.mcp import _context, tools_workflow
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.registry import BlockRegistry, BlockSpec
from scistudio.core.types.array import Array
from scistudio.core.types.registry import TypeRegistry


def _run(coro):
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


def _register_fake_package_io(registry: BlockRegistry, *, type_name: str, name: str, direction: str = "input") -> None:
    """Inject a synthetic ``scistudio_blocks_*`` IO block into *registry*.

    CI has no plugin packages installed, so a package-specific IO block is
    fabricated here to make the redirect/warning behavior deterministic.
    """
    port = (
        OutputPort(name="data", accepted_types=[Array])
        if direction == "input"
        else InputPort(name="data", accepted_types=[Array])
    )
    spec = BlockSpec(
        name=name,
        type_name=type_name,
        base_category="io",
        module_path="scistudio_blocks_fake.io." + type_name.replace(".", "_"),
        direction=direction,
        input_ports=[port] if direction == "output" else [],
        output_ports=[port] if direction == "input" else [],
    )
    registry._registry[spec.name] = spec
    registry._aliases[spec.type_name] = spec.name


def _wf_yaml(block_type: str) -> str:
    return (
        "workflow:\n"
        "  id: guard_test\n"
        "  version: 1.0.0\n"
        "  nodes:\n"
        "    - id: n1\n"
        f"      block_type: {block_type}\n"
        "      config: {}\n"
        "  edges: []\n"
    )


# ---------------------------------------------------------------------------
# list_blocks / get_block_schema surfacing
# ---------------------------------------------------------------------------


def test_list_blocks_surfaces_canonical_type_name(ctx: _StubRuntime) -> None:
    result = _run(tools_workflow.list_blocks())
    by_type = {b.type_name: b for b in result.blocks}
    # Core Load: canonical type_name is 'load_data'; display name is 'Load'.
    assert "load_data" in by_type
    load = by_type["load_data"]
    assert load.name == "Load"
    assert load.type_name == "load_data"
    # Every entry's type_name is a real registered type_name, never a display name.
    specs = ctx.block_registry.all_specs()
    real_type_names = {s.type_name for s in specs.values()}
    for entry in result.blocks:
        assert entry.type_name in real_type_names


def test_core_load_block_is_not_flagged_use_instead(ctx: _StubRuntime) -> None:
    result = _run(tools_workflow.list_blocks())
    load = next(b for b in result.blocks if b.type_name == "load_data")
    assert load.use_instead is None


def test_list_blocks_flags_package_io_use_instead(ctx: _StubRuntime) -> None:
    _register_fake_package_io(ctx.block_registry, type_name="fake.load_thing", name="Load Thing")
    result = _run(tools_workflow.list_blocks())
    entry = next(b for b in result.blocks if b.type_name == "fake.load_thing")
    assert entry.use_instead is not None
    assert "load_data" in entry.use_instead
    assert "core_type" in entry.use_instead


# ---------------------------------------------------------------------------
# write_workflow guard: unresolvable block_type hard-fails
# ---------------------------------------------------------------------------


def test_write_workflow_accepts_canonical_core_type_name(ctx: _StubRuntime) -> None:
    result = _run(tools_workflow.write_workflow("workflows/guard_test.yaml", _wf_yaml("load_data")))
    assert result.bytes_written > 0
    assert result.warnings == []


def test_write_workflow_rejects_unknown_block_type(ctx: _StubRuntime) -> None:
    with pytest.raises(ValueError) as exc:
        _run(tools_workflow.write_workflow("workflows/bad.yaml", _wf_yaml("load_dataa")))
    msg = str(exc.value)
    assert "not a registered" in msg
    # Nearest-match suggestion points at the real type_name.
    assert "load_data" in msg


def test_write_workflow_rejects_display_name_as_block_type(ctx: _StubRuntime) -> None:
    # 'Load' is the display name; its canonical type_name is 'load_data'.
    with pytest.raises(ValueError) as exc:
        _run(tools_workflow.write_workflow("workflows/disp.yaml", _wf_yaml("Load")))
    msg = str(exc.value)
    assert "display name" in msg
    assert "load_data" in msg


def test_write_workflow_unknown_block_type_does_not_write_file(ctx: _StubRuntime) -> None:
    target = ctx.project_dir / "workflows" / "never.yaml"
    with pytest.raises(ValueError):
        _run(tools_workflow.write_workflow("workflows/never.yaml", _wf_yaml("nope_block")))
    assert not target.exists()


# ---------------------------------------------------------------------------
# write_workflow guard: package IO block warns but is not blocked
# ---------------------------------------------------------------------------


def test_write_workflow_warns_on_package_io_block(ctx: _StubRuntime) -> None:
    _register_fake_package_io(ctx.block_registry, type_name="fake.load_thing", name="Load Thing")
    result = _run(tools_workflow.write_workflow("workflows/guard_test.yaml", _wf_yaml("fake.load_thing")))
    # Write succeeds (non-blocking) ...
    assert result.bytes_written > 0
    # ... but a warning names the core equivalent.
    assert len(result.warnings) == 1
    assert "load_data" in result.warnings[0]
    assert "fake.load_thing" in result.warnings[0]
