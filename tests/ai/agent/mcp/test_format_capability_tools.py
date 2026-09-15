"""Format capability ids across the MCP block tools (#2435).

- ``get_block_schema`` lists the capability ids a core Load/Save node or a
  Code/App Block port can pick, including package-provided ones.
- ``get_block_config`` reports the stored and the resolved capability, per node
  for core Load/Save and per port for Code/App Blocks.
- ``update_block_config`` refuses a ``capability_id`` that does not fit the
  node's direction, data type, and extension, and accepts clearing it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from scistudio.ai.agent.mcp import _context, tools_inspection, tools_workflow
from scistudio.blocks.io.capabilities import FormatCapability
from scistudio.blocks.registry import BlockRegistry, BlockSpec
from scistudio.core.types.base import DataObject
from scistudio.core.types.registry import TypeRegistry

_PACKAGE = "scistudio-blocks-widgets"


class Widget(DataObject):
    """A package data type with several save formats and no default."""


class Gadget(DataObject):
    """A package data type with a declared default save format."""


def _capability(
    capability_id: str,
    *,
    direction: str,
    data_type: type[DataObject],
    extension: str,
    block_type: str,
    is_default: bool = False,
) -> FormatCapability:
    return FormatCapability(
        id=capability_id,
        direction=direction,  # type: ignore[arg-type]
        data_type=data_type,
        format_id=extension.lstrip("."),
        extensions=(extension,),
        label=extension.lstrip(".").upper(),
        block_type=block_type,
        handler="save_file" if direction == "save" else "load_file",
        is_default=is_default,
    )


WIDGET_LOAD = "scistudio-blocks-widgets.widget.wdg.load"
WIDGET_SAVE_WDG = "scistudio-blocks-widgets.widget.wdg.save"
WIDGET_SAVE_WDGZ = "scistudio-blocks-widgets.widget.wdgz.save"
GADGET_SAVE_GDG = "scistudio-blocks-widgets.gadget.gdg.save"
GADGET_SAVE_GDGX = "scistudio-blocks-widgets.gadget.gdgx.save"


def _register_package(registry: BlockRegistry) -> None:
    specs = [
        BlockSpec(
            name="widgets.load_widget",
            type_name="widgets.load_widget",
            base_category="io",
            module_path="scistudio_blocks_widgets.io",
            package_name=_PACKAGE,
            direction="input",
            format_capabilities=[
                _capability(WIDGET_LOAD, direction="load", data_type=Widget, extension=".wdg", block_type="LoadWidget")
            ],
        ),
        BlockSpec(
            name="widgets.save_widget",
            type_name="widgets.save_widget",
            base_category="io",
            module_path="scistudio_blocks_widgets.io",
            package_name=_PACKAGE,
            direction="output",
            format_capabilities=[
                _capability(
                    WIDGET_SAVE_WDG, direction="save", data_type=Widget, extension=".wdg", block_type="SaveWidget"
                ),
                _capability(
                    WIDGET_SAVE_WDGZ, direction="save", data_type=Widget, extension=".wdgz", block_type="SaveWidget"
                ),
                _capability(
                    GADGET_SAVE_GDG,
                    direction="save",
                    data_type=Gadget,
                    extension=".gdg",
                    block_type="SaveWidget",
                    is_default=True,
                ),
                _capability(
                    GADGET_SAVE_GDGX, direction="save", data_type=Gadget, extension=".gdgx", block_type="SaveWidget"
                ),
            ],
        ),
    ]
    for spec in specs:
        registry._registry[spec.name] = spec
        registry._aliases[spec.type_name] = spec.name


@dataclass
class _StubRuntime:
    block_registry: BlockRegistry = field(default_factory=BlockRegistry)
    type_registry: TypeRegistry = field(default_factory=TypeRegistry)
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    _project_dir: Path | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@pytest.fixture
def ctx(tmp_path: Path):
    root = (tmp_path / "proj").resolve()
    (root / "workflows").mkdir(parents=True)
    runtime = _StubRuntime(_project_dir=root)
    runtime.block_registry.scan()
    runtime.type_registry.scan_builtins()
    _register_package(runtime.block_registry)
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _write_workflow(ctx: _StubRuntime, nodes: list[dict[str, Any]]) -> str:
    path = ctx.project_dir / "workflows" / "fmt.yaml"  # type: ignore[operator]
    document = {"workflow": {"id": "fmt", "version": "1.0.0", "nodes": nodes, "edges": []}}
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return "workflows/fmt.yaml"


def _config(ctx: _StubRuntime, workflow: str, block_id: str) -> Any:
    return _run(tools_inspection.get_block_config(workflow_path=workflow, block_id=block_id))


def _update(workflow: str, block_id: str, params: dict[str, Any]) -> Any:
    return _run(tools_inspection.update_block_config(workflow_path=workflow, block_id=block_id, params=params))


# ---------------------------------------------------------------------------
# get_block_schema
# ---------------------------------------------------------------------------


def test_schema_lists_core_io_capabilities_with_package_entries(ctx: _StubRuntime) -> None:
    load = _run(tools_workflow.get_block_schema("load_data"))
    save = _run(tools_workflow.get_block_schema("save_data"))

    load_ids = {entry["capability_id"] for entry in load.format_capabilities}
    save_ids = {entry["capability_id"] for entry in save.format_capabilities}
    assert {"core.dataframe.csv.load", WIDGET_LOAD} <= load_ids
    assert {"core.dataframe.csv.save", WIDGET_SAVE_WDG, WIDGET_SAVE_WDGZ} <= save_ids
    assert {entry["direction"] for entry in load.format_capabilities} == {"load"}
    assert {entry["direction"] for entry in save.format_capabilities} == {"save"}
    assert "capability_id" in (load.format_capability_usage or "")

    widget = next(entry for entry in save.format_capabilities if entry["capability_id"] == WIDGET_SAVE_WDGZ)
    assert widget == {
        "capability_id": WIDGET_SAVE_WDGZ,
        "direction": "save",
        "data_type": "Widget",
        "format_id": "wdgz",
        "extensions": [".wdgz"],
        "label": "WDGZ",
        "package": _PACKAGE,
        "priority": 0,
        "is_default": False,
        "pinnable": True,
    }
    csv = next(entry for entry in load.format_capabilities if entry["capability_id"] == "core.dataframe.csv.load")
    assert csv["package"] == "scistudio"

    # Every Artifact capability is folded into one display-only choice, as the
    # GUI Format dropdown shows it.
    artifact = [entry for entry in load.format_capabilities if entry["data_type"] == "Artifact"]
    assert [entry["capability_id"] for entry in artifact] == ["core.artifact.any.load"]
    assert artifact[0]["pinnable"] is False


@pytest.mark.parametrize(
    ("block_type", "input_key", "output_key"),
    [("code_block", "inputs", "outputs"), ("app_block", "input_ports", "output_ports")],
)
def test_schema_lists_port_capabilities_for_exchange_blocks(
    ctx: _StubRuntime, block_type: str, input_key: str, output_key: str
) -> None:
    schema = _run(tools_workflow.get_block_schema(block_type))
    ids = {(entry["direction"], entry["capability_id"]) for entry in schema.format_capabilities}
    assert ("load", WIDGET_LOAD) in ids
    assert ("save", WIDGET_SAVE_WDG) in ids
    assert ("save", "core.dataframe.csv.save") in ids
    usage = schema.format_capability_usage or ""
    assert f"config.{input_key}" in usage and f"config.{output_key}" in usage


def test_schema_has_no_capabilities_for_other_blocks(ctx: _StubRuntime) -> None:
    other = next(
        spec.type_name
        for spec in ctx.block_registry.all_specs().values()
        if spec.base_category == "process" and spec.type_name
    )
    schema = _run(tools_workflow.get_block_schema(other))
    assert schema.format_capabilities == []
    assert schema.format_capability_usage is None


# ---------------------------------------------------------------------------
# get_block_config
# ---------------------------------------------------------------------------


def test_config_reports_pinned_resolved_ambiguous_invalid_and_none(ctx: _StubRuntime) -> None:
    workflow = _write_workflow(
        ctx,
        [
            {
                "id": "pinned",
                "block_type": "save_data",
                "config": {"core_type": "Widget", "capability_id": WIDGET_SAVE_WDGZ},
            },
            # GUI-saved nodes nest their params under ``config.params``.
            {
                "id": "by_ext",
                "block_type": "save_data",
                "config": {"params": {"core_type": "Widget", "path": "out/a.wdg"}},
            },
            {"id": "ambiguous", "block_type": "save_data", "config": {"core_type": "Widget", "path": "out"}},
            {"id": "default", "block_type": "save_data", "config": {"core_type": "Gadget", "path": "out"}},
            {
                "id": "invalid",
                "block_type": "save_data",
                "config": {"core_type": "Widget", "capability_id": GADGET_SAVE_GDG},
            },
            {"id": "core_csv", "block_type": "load_data", "config": {"core_type": "DataFrame", "path": "data/in.csv"}},
            {"id": "none", "block_type": "load_data", "config": {"core_type": "DataFrame", "path": "data/in.nope"}},
        ],
    )

    pinned = _config(ctx, workflow, "pinned").capability
    assert pinned["status"] == "pinned"
    assert pinned["selected_capability_id"] == pinned["resolved_capability_id"] == WIDGET_SAVE_WDGZ

    by_ext = _config(ctx, workflow, "by_ext").capability
    assert by_ext["status"] == "resolved"
    assert by_ext["selected_capability_id"] is None
    assert by_ext["resolved_capability_id"] == WIDGET_SAVE_WDG
    assert by_ext["extension"] == ".wdg"

    ambiguous = _config(ctx, workflow, "ambiguous").capability
    assert ambiguous["status"] == "ambiguous"
    assert ambiguous["resolved_capability_id"] is None
    assert set(ambiguous["candidates"]) == {WIDGET_SAVE_WDG, WIDGET_SAVE_WDGZ}

    # Save honours the type's declared default when nothing else decides.
    default = _config(ctx, workflow, "default").capability
    assert (default["status"], default["resolved_capability_id"]) == ("resolved", GADGET_SAVE_GDG)

    invalid = _config(ctx, workflow, "invalid").capability
    assert invalid["status"] == "invalid"
    assert invalid["resolved_capability_id"] is None
    assert set(invalid["candidates"]) == {WIDGET_SAVE_WDG, WIDGET_SAVE_WDGZ}

    core_csv = _config(ctx, workflow, "core_csv").capability
    assert (core_csv["status"], core_csv["resolved_capability_id"]) == ("resolved", "core.dataframe.csv.load")

    none = _config(ctx, workflow, "none").capability
    assert none["status"] == "none"
    assert none["resolved_capability_id"] is None


def test_config_reports_capabilities_per_code_block_and_app_block_port(ctx: _StubRuntime) -> None:
    workflow = _write_workflow(
        ctx,
        [
            {
                "id": "code",
                "block_type": "code_block",
                "config": {
                    "script_path": "scripts/run.py",
                    "inputs": [
                        {
                            "name": "w",
                            "direction": "input",
                            "data_type": "Widget",
                            "extension": ".wdgz",
                            "capability_id": "",
                        },
                        {
                            "name": "t",
                            "direction": "input",
                            "data_type": "Widget",
                            "extension": "",
                            "capability_id": "",
                        },
                    ],
                    "outputs": [
                        {
                            "name": "back",
                            "direction": "output",
                            "data_type": "Widget",
                            "extension": ".wdg",
                            "capability_id": WIDGET_LOAD,
                        }
                    ],
                },
            },
            {
                "id": "app",
                "block_type": "app_block",
                "config": {
                    "app_command": "true",
                    "output_ports": [
                        {"name": "o", "types": ["Widget"], "extension": "wdg", "capability_id": WIDGET_SAVE_WDG},
                    ],
                },
            },
        ],
    )

    code = _config(ctx, workflow, "code")
    assert code.capability is None
    ports = {port["port"]: port for port in code.port_capabilities}
    assert ports["w"]["direction"] == "save"
    assert (ports["w"]["status"], ports["w"]["resolved_capability_id"]) == ("resolved", WIDGET_SAVE_WDGZ)
    assert ports["t"]["status"] == "ambiguous"
    assert ports["back"]["direction"] == "load"
    assert (ports["back"]["status"], ports["back"]["resolved_capability_id"]) == ("pinned", WIDGET_LOAD)

    app = _config(ctx, workflow, "app").port_capabilities
    # An output port reads the file back, so a save capability is not a fit.
    assert [(port["port"], port["direction"], port["status"]) for port in app] == [("o", "load", "invalid")]
    assert app[0]["candidates"] == [WIDGET_LOAD]


def test_config_of_a_block_without_capabilities_has_no_view(ctx: _StubRuntime) -> None:
    workflow = _write_workflow(ctx, [{"id": "n", "block_type": "no_such_block", "config": {"x": 1}}])
    result = _config(ctx, workflow, "n")
    assert result.capability is None
    assert result.port_capabilities == []


# ---------------------------------------------------------------------------
# update_block_config
# ---------------------------------------------------------------------------


def test_update_validates_node_capability_id(ctx: _StubRuntime) -> None:
    workflow = _write_workflow(
        ctx, [{"id": "save", "block_type": "save_data", "config": {"core_type": "Widget", "path": "out/a.wdg"}}]
    )
    path = ctx.project_dir / workflow  # type: ignore[operator]

    with pytest.raises(ValueError, match="not a save capability") as unknown:
        _update(workflow, "save", {"capability_id": "scistudio-blocks-widgets.nope.save"})
    assert WIDGET_SAVE_WDG in str(unknown.value)

    # Mismatched extension: the path says .wdg.
    with pytest.raises(ValueError, match=r"extension '\.wdg'"):
        _update(workflow, "save", {"capability_id": WIDGET_SAVE_WDGZ})
    # Mismatched data type.
    with pytest.raises(ValueError, match="core_type 'Widget'"):
        _update(workflow, "save", {"capability_id": GADGET_SAVE_GDG})
    assert "capability_id" not in path.read_text(encoding="utf-8")

    # A path change in the same patch is taken into account.
    _update(workflow, "save", {"capability_id": WIDGET_SAVE_WDGZ, "path": "out/a.wdgz"})
    assert _config(ctx, workflow, "save").capability["status"] == "pinned"

    _update(workflow, "save", {"capability_id": None})
    assert _config(ctx, workflow, "save").capability["status"] == "resolved"
    _update(workflow, "save", {"capability_id": ""})

    with pytest.raises(ValueError, match="must be a string"):
        _update(workflow, "save", {"capability_id": 3})


def test_update_refuses_the_display_only_artifact_choice(ctx: _StubRuntime) -> None:
    workflow = _write_workflow(ctx, [{"id": "save", "block_type": "save_data", "config": {"core_type": "Artifact"}}])
    with pytest.raises(ValueError, match="display-only"):
        _update(workflow, "save", {"capability_id": "core.artifact.any.save"})


def test_update_validates_gui_nested_params(ctx: _StubRuntime) -> None:
    workflow = _write_workflow(
        ctx, [{"id": "save", "block_type": "save_data", "config": {"params": {"core_type": "Widget"}}}]
    )
    with pytest.raises(ValueError, match="not a save capability"):
        _update(workflow, "save", {"params": {"core_type": "Widget", "capability_id": GADGET_SAVE_GDG}})
    _update(workflow, "save", {"params": {"core_type": "Widget", "capability_id": WIDGET_SAVE_WDG}})


@pytest.mark.parametrize(
    ("block_type", "key", "entry"),
    [
        ("code_block", "outputs", {"name": "o", "direction": "output", "data_type": "Widget", "extension": ".wdg"}),
        ("app_block", "output_ports", {"name": "o", "types": ["Widget"], "extension": "wdg"}),
    ],
)
def test_update_validates_port_capability_id(
    ctx: _StubRuntime, block_type: str, key: str, entry: dict[str, Any]
) -> None:
    workflow = _write_workflow(ctx, [{"id": "n", "block_type": block_type, "config": {key: []}}])

    with pytest.raises(ValueError, match=r"not a load capability.*Valid choices: " + WIDGET_LOAD.replace(".", r"\.")):
        _update(workflow, "n", {key: [{**entry, "capability_id": WIDGET_SAVE_WDG}]})
    with pytest.raises(ValueError, match="not a load capability"):
        _update(workflow, "n", {key: [{**entry, "capability_id": "unknown.cap.load"}]})

    _update(workflow, "n", {key: [{**entry, "capability_id": WIDGET_LOAD}]})
    port = _config(ctx, workflow, "n").port_capabilities[0]
    assert (port["status"], port["resolved_capability_id"]) == ("pinned", WIDGET_LOAD)

    for cleared in (None, ""):
        _update(workflow, "n", {key: [{**entry, "capability_id": cleared}]})
        assert _config(ctx, workflow, "n").port_capabilities[0]["status"] == "resolved"


def test_update_without_capability_id_is_not_checked(ctx: _StubRuntime) -> None:
    workflow = _write_workflow(
        ctx, [{"id": "save", "block_type": "save_data", "config": {"core_type": "Widget", "capability_id": "stale"}}]
    )
    # The stored id is already unusable; a patch that does not touch it still writes.
    _update(workflow, "save", {"overwrite": True})
    assert _config(ctx, workflow, "save").capability["status"] == "invalid"
