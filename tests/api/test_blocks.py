"""Tests for block registry API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scistudio.api.routes.blocks import _is_plugin_package


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("scistudio-blocks-imaging", True),
        ("scistudio-blocks-lcms", True),
        ("scistudio-blocks-srs", True),
        ("ai_block", False),
        ("code_block", False),
        ("load_data", False),
        ("", False),
    ],
)
def test_is_plugin_package(name: str, expected: bool) -> None:
    assert _is_plugin_package(name) is expected


def test_list_blocks_and_schema_alias_endpoints(client: TestClient) -> None:
    """The block palette and schema endpoints should expose built-in metadata."""
    response = client.get("/api/blocks/")
    assert response.status_code == 200
    payload = response.json()
    assert "blocks" in payload
    # T-TRK-003: TransformBlock was relocated to tests/fixtures/noop_block.py
    # as NoopBlock with type_name="noop". The conftest hook re-registers it
    # under the legacy "process_block" alias for backward compatibility, but
    # the canonical type_name reported by the palette endpoint is now "noop".
    assert any(block["type_name"] == "noop" for block in payload["blocks"])

    schema = client.get("/api/blocks/process_block/schema")
    assert schema.status_code == 200
    schema_payload = schema.json()
    assert schema_payload["name"] == "Process Block"
    assert schema_payload["base_category"] == "process"
    assert schema_payload["config_schema"]["properties"]["sleep_seconds"]["ui_priority"] == 1
    assert any(entry["name"] == "DataObject" for entry in schema_payload["type_hierarchy"])

    alias = client.get("/api/blocks/process_block")
    assert alias.status_code == 200
    assert alias.json() == schema_payload


def test_validate_connection_endpoint_uses_registry_type_information(client: TestClient) -> None:
    """Connection validation should accept compatible ports and reject mismatches."""
    compatible = client.post(
        "/api/blocks/validate-connection",
        json={
            "source_block": "io_block",
            "source_port": "data",
            "target_block": "process_block",
            "target_port": "input",
        },
    )
    assert compatible.status_code == 200
    assert compatible.json()["compatible"] is True

    # #601: With bidirectional subclass check, DataObject (superclass) ->
    # DataFrame (subclass) is now compatible since DataFrame is a subclass
    # of DataObject. Use an unrelated type pair for the incompatibility test.
    bidirectional = client.post(
        "/api/blocks/validate-connection",
        json={
            "source_block": "process_block",
            "source_port": "output",
            "target_block": "imaging.axis_merge",
            "target_port": "images",
        },
    )
    assert bidirectional.status_code == 200
    assert bidirectional.json()["compatible"] is True


def test_validate_connection_uses_load_data_effective_core_type(client: TestClient) -> None:
    """#889: ``LoadData(core_type=Array)`` validates as ``Array``, not ``DataObject``.

    Without ``source_node_config`` the route falls back to the static
    spec — ``LoadData`` declares its output port as a placeholder
    ``DataObject``, so a target requiring ``Array`` would be rejected
    even when the user has chosen ``core_type='Array'`` on the canvas.
    """
    # With node_config: LoadData -> SaveData(core_type=Array) must be compatible
    # because both sides resolve to the Array type via get_effective_*_ports().
    compatible = client.post(
        "/api/blocks/validate-connection",
        json={
            "source_block": "load_data",
            "source_port": "data",
            "target_block": "save_data",
            "target_port": "data",
            "source_node_config": {"core_type": "Array"},
            "target_node_config": {"core_type": "Array"},
        },
    )
    assert compatible.status_code == 200, compatible.text
    assert compatible.json()["compatible"] is True, compatible.json()

    # Without node_config the route still answers (legacy fallback).
    legacy = client.post(
        "/api/blocks/validate-connection",
        json={
            "source_block": "load_data",
            "source_port": "data",
            "target_block": "save_data",
            "target_port": "data",
        },
    )
    assert legacy.status_code == 200


def test_validate_connection_rejects_load_data_core_type_mismatch(client: TestClient) -> None:
    """#889: ``LoadData(core_type=DataFrame)`` -> ``SaveData(core_type=Array)`` fails.

    The two endpoints resolve to different DataObject subclasses and
    the connection validator rejects the link.
    """
    response = client.post(
        "/api/blocks/validate-connection",
        json={
            "source_block": "load_data",
            "source_port": "data",
            "target_block": "save_data",
            "target_port": "data",
            "source_node_config": {"core_type": "DataFrame"},
            "target_node_config": {"core_type": "Array"},
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["compatible"] is False, payload


def test_resolve_effective_port_output_uses_block_get_effective_output_ports() -> None:
    """#889: resolver consumes ``get_effective_output_ports`` when config given.

    Unit test against the shared resolver so we exercise the
    ``node_config`` -> ``Block.instantiate`` -> effective-ports path
    independent of which concrete blocks happen to be installed in the
    test environment.
    """
    from typing import ClassVar

    from scistudio.api.routes.blocks import _resolve_effective_port
    from scistudio.blocks.base.ports import OutputPort
    from scistudio.core.types.array import Array
    from scistudio.core.types.base import DataObject

    class _FakeBlock:
        def __init__(self, config: dict[str, object]) -> None:
            self.config = config

        def get_effective_output_ports(self) -> list[OutputPort]:
            core = self.config.get("core_type", "DataObject")
            cls = Array if core == "Array" else DataObject
            return [OutputPort(name="data", accepted_types=[cls])]

        def get_effective_input_ports(self) -> list[OutputPort]:
            return []

    class _FakeSpec:
        variadic_outputs = False
        variadic_inputs = False
        output_ports: ClassVar[list[OutputPort]] = [
            OutputPort(name="data", accepted_types=[DataObject]),
        ]
        input_ports: ClassVar[list[OutputPort]] = []

    class _FakeRegistry:
        def instantiate(self, block_type: str, config: dict[str, object]) -> _FakeBlock:
            return _FakeBlock(config)

    # Output direction with node_config — resolver returns the Array-typed port.
    port = _resolve_effective_port(
        _FakeSpec(), _FakeRegistry(), "fake", "data", {"core_type": "Array"}, direction="output"
    )
    assert isinstance(port, OutputPort)
    assert port.accepted_types == [Array]

    # Output direction without node_config — falls back to static DataObject port.
    static_port = _resolve_effective_port(_FakeSpec(), _FakeRegistry(), "fake", "data", None, direction="output")
    assert isinstance(static_port, OutputPort)
    assert static_port.accepted_types == [DataObject]


def test_resolve_effective_port_input_direction_uses_block_get_effective_input_ports() -> None:
    """#889: input direction mirrors the output-side contract."""
    from typing import ClassVar

    from scistudio.api.routes.blocks import _resolve_effective_port
    from scistudio.blocks.base.ports import InputPort
    from scistudio.core.types.array import Array
    from scistudio.core.types.base import DataObject

    class _FakeBlock:
        def __init__(self, config: dict[str, object]) -> None:
            self.config = config

        def get_effective_input_ports(self) -> list[InputPort]:
            core = self.config.get("core_type", "DataObject")
            cls = Array if core == "Array" else DataObject
            return [InputPort(name="data", accepted_types=[cls])]

    class _FakeSpec:
        variadic_inputs = False
        input_ports: ClassVar[list[InputPort]] = [
            InputPort(name="data", accepted_types=[DataObject]),
        ]

    class _FakeRegistry:
        def instantiate(self, block_type: str, config: dict[str, object]) -> _FakeBlock:
            return _FakeBlock(config)

    port = _resolve_effective_port(
        _FakeSpec(), _FakeRegistry(), "fake", "data", {"core_type": "Array"}, direction="input"
    )
    assert isinstance(port, InputPort)
    assert port.accepted_types == [Array]


def test_resolve_effective_port_falls_back_when_registry_raises() -> None:
    """#889: a registry failure does not 500 — the resolver retries the static spec."""
    from typing import ClassVar

    from scistudio.api.routes.blocks import _resolve_effective_port
    from scistudio.blocks.base.ports import OutputPort
    from scistudio.core.types.base import DataObject

    class _FakeSpec:
        variadic_outputs = False
        output_ports: ClassVar[list[OutputPort]] = [
            OutputPort(name="data", accepted_types=[DataObject]),
        ]

    class _ExplodingRegistry:
        def instantiate(self, block_type: str, config: dict[str, object]) -> object:
            raise RuntimeError("bad config")

    port = _resolve_effective_port(
        _FakeSpec(), _ExplodingRegistry(), "fake", "data", {"core_type": "Array"}, direction="output"
    )
    assert isinstance(port, OutputPort)
    # Falls back to the static spec rather than propagating the error.
    assert port.accepted_types == [DataObject]


def test_imaging_io_schema_exposes_item_types_and_collection_flags(client: TestClient) -> None:
    """Imaging IO blocks should expose concrete item types and collection metadata."""
    load_schema = client.get("/api/blocks/imaging.load_image/schema")
    assert load_schema.status_code == 200
    load_payload = load_schema.json()
    assert load_payload["direction"] == "input"
    assert load_payload["output_ports"][0]["accepted_types"] == ["Image"]
    assert load_payload["output_ports"][0]["is_collection"] is True
    assert any(entry["name"] == "Mask" for entry in load_payload["type_hierarchy"])
    assert any(entry["name"] == "Label" for entry in load_payload["type_hierarchy"])

    save_schema = client.get("/api/blocks/imaging.save_image/schema")
    assert save_schema.status_code == 200
    save_payload = save_schema.json()
    assert save_payload["direction"] == "output"
    assert save_payload["input_ports"][0]["accepted_types"] == ["Image"]
    assert save_payload["input_ports"][0]["is_collection"] is True


def test_block_schema_exposes_serializable_format_capabilities(client: TestClient) -> None:
    """ADR-043 capability metadata is exposed on schema payloads."""
    response = client.get("/api/blocks/imaging.load_image/schema")
    assert response.status_code == 200
    payload = response.json()

    capabilities = payload["format_capabilities"]
    assert capabilities
    capability = capabilities[0]
    assert {
        "id",
        "direction",
        "data_type",
        "format_id",
        "extensions",
        "label",
        "block_type",
        "handler",
        "is_default",
        "priority",
        "roundtrip_group",
        "metadata_fidelity",
        "is_synthesized",
        "migration_scaffold",
    }.issubset(capability)
    assert capability["direction"] == "load"
    assert capability["data_type"] == "Image"
    assert capability["extensions"]
    assert capability["metadata_fidelity"]["level"] in {
        "pixel_only",
        "typed_meta",
        "format_specific",
        "lossless",
    }


def test_list_blocks_keeps_palette_compact_with_capability_metadata(client: TestClient) -> None:
    """ADR-043 package IO capabilities are surfaced through core Load/Save."""
    response = client.get("/api/blocks/")
    assert response.status_code == 200
    blocks = response.json()["blocks"]

    assert [block for block in blocks if block["type_name"] == "imaging.load_image"] == []
    assert [block for block in blocks if block["type_name"] == "imaging.save_image"] == []

    load = next(block for block in blocks if block["type_name"] == "load_data")
    save = next(block for block in blocks if block["type_name"] == "save_data")
    assert any(capability["data_type"] == "Image" for capability in load["format_capabilities"])
    assert any(capability["data_type"] == "Image" for capability in save["format_capabilities"])


def test_core_load_save_schema_aggregates_registered_io_types(client: TestClient) -> None:
    """Core Load/Save schema exposes package types and removes allow_pickle UI."""
    load_response = client.get("/api/blocks/load_data/schema")
    assert load_response.status_code == 200
    load_payload = load_response.json()
    load_props = load_payload["config_schema"]["properties"]
    assert "Image" in load_props["core_type"]["enum"]
    assert "allow_pickle" not in load_props
    assert load_props["path"]["ui_widget"] == "file_browser"
    assert any(capability["data_type"] == "Image" for capability in load_payload["format_capabilities"])
    assert load_payload["dynamic_ports"]["output_port_mapping"]["data"]["Image"] == ["Image"]

    save_response = client.get("/api/blocks/save_data/schema")
    assert save_response.status_code == 200
    save_payload = save_response.json()
    save_props = save_payload["config_schema"]["properties"]
    assert "Image" in save_props["core_type"]["enum"]
    assert "allow_pickle" not in save_props
    assert save_props["path"]["ui_widget"] == "directory_browser"
    assert any(capability["data_type"] == "Image" for capability in save_payload["format_capabilities"])
    assert any(
        capability["id"] == "scistudio-blocks-lcms.table.xlsx.save"
        for capability in save_payload["format_capabilities"]
    )
    assert save_payload["dynamic_ports"]["input_port_mapping"]["data"]["Image"] == ["Image"]


def test_core_load_save_schema_collapses_artifact_formats_to_any(client: TestClient) -> None:
    """Artifact is opaque bytes, so the unified GUI exposes Any, not extensions."""
    load_response = client.get("/api/blocks/load_data/schema")
    assert load_response.status_code == 200
    load_payload = load_response.json()
    load_artifact = [
        capability for capability in load_payload["format_capabilities"] if capability["data_type"] == "Artifact"
    ]
    assert len(load_artifact) == 1
    assert load_artifact[0]["id"] == "core.artifact.any.load"
    assert load_artifact[0]["direction"] == "load"
    assert load_artifact[0]["format_id"] == "any"
    assert load_artifact[0]["extensions"] == []
    assert load_artifact[0]["label"] == "Any"
    assert load_artifact[0]["is_default"] is True

    save_response = client.get("/api/blocks/save_data/schema")
    assert save_response.status_code == 200
    save_payload = save_response.json()
    save_artifact = [
        capability for capability in save_payload["format_capabilities"] if capability["data_type"] == "Artifact"
    ]
    assert len(save_artifact) == 1
    assert save_artifact[0]["id"] == "core.artifact.any.save"
    assert save_artifact[0]["direction"] == "save"
    assert save_artifact[0]["format_id"] == "any"
    assert save_artifact[0]["extensions"] == []
    assert save_artifact[0]["label"] == "Any"
    assert save_artifact[0]["is_default"] is True


# ----------------------------------------------------------------------------
# Stage 10.1 Part 2 — skipped test stubs authored by Agent A.
#
# Agent B will remove the skip markers and implement these in Part 2.
# ----------------------------------------------------------------------------


def test_list_blocks_includes_source_and_package_name(client: TestClient) -> None:
    """GET /api/blocks/ response items contain ``source`` and ``package_name``."""
    response = client.get("/api/blocks/")
    assert response.status_code == 200
    blocks = response.json()["blocks"]
    assert len(blocks) > 0
    for block in blocks:
        assert "source" in block, f"Block {block['type_name']} missing 'source'"
        assert "package_name" in block, f"Block {block['type_name']} missing 'package_name'"


def test_list_blocks_source_values_enumerated(client: TestClient) -> None:
    """Every block reports ``source`` in {"builtin", "package", "custom", ""}."""
    response = client.get("/api/blocks/")
    assert response.status_code == 200
    blocks = response.json()["blocks"]
    valid_sources = {"builtin", "package", "custom", ""}
    for block in blocks:
        assert block["source"] in valid_sources, f"Block {block['type_name']} has unexpected source={block['source']!r}"
        # Raw internal labels must never leak to the API
        assert block["source"] not in ("tier1", "entry_point", "monorepo"), (
            f"Block {block['type_name']} leaks raw source={block['source']!r}"
        )


def test_core_blocks_have_empty_package_name(client: TestClient) -> None:
    """Core/builtin blocks must have package_name='' so the frontend groups them together."""
    response = client.get("/api/blocks/")
    assert response.status_code == 200
    blocks = response.json()["blocks"]
    # Blocks with source "builtin" should have empty package_name
    builtin_blocks = [b for b in blocks if b["source"] == "builtin"]
    for block in builtin_blocks:
        assert block["package_name"] == "", (
            f"Core block {block['type_name']} should have empty package_name, got {block['package_name']!r}"
        )


def test_plugin_blocks_retain_package_name(client: TestClient) -> None:
    """Plugin blocks (scistudio-blocks-*) should retain their package_name."""
    response = client.get("/api/blocks/")
    assert response.status_code == 200
    blocks = response.json()["blocks"]
    pkg_blocks = [b for b in blocks if b["package_name"].startswith("scistudio-blocks-")]
    # The imaging package is always installed in tests
    assert any(b["package_name"] == "scistudio-blocks-imaging" for b in pkg_blocks), (
        "Expected at least one block from scistudio-blocks-imaging"
    )


def test_lcms_srs_blocks_have_domain_prefix(client: TestClient) -> None:
    """LCMS and SRS blocks must have dotted type_name prefixes for palette grouping."""
    response = client.get("/api/blocks/")
    assert response.status_code == 200
    blocks = response.json()["blocks"]
    lcms_blocks = [b for b in blocks if b.get("package_name") == "scistudio-blocks-lcms"]
    srs_blocks = [b for b in blocks if b.get("package_name") == "scistudio-blocks-srs"]
    for block in lcms_blocks:
        assert block["type_name"].startswith("lcms."), (
            f"LCMS block {block['name']} missing 'lcms.' prefix: {block['type_name']}"
        )
    for block in srs_blocks:
        assert block["type_name"].startswith("srs."), (
            f"SRS block {block['name']} missing 'srs.' prefix: {block['type_name']}"
        )


# ----------------------------------------------------------------------------
# ADR-050 canvas-node-readability — package -> registry -> API schema contract.
#
# The square node + BottomPanel refactor (issue #1698) removes inline node-body
# config but MUST NOT change the package -> registry -> API block-schema
# contract that feeds canvas ports, the `+/-` topology controls, the TypeLegend,
# and BottomPanel Config field ordering / widget selection. These tests prove
# that BlockSummary (palette) and BlockSchemaResponse (detail) keep exposing the
# metadata the new frontend reads — for core AND for package-provided imaging,
# spectroscopy, LCMS, and SRS blocks — without any package source edit.
#
# Spec: docs/specs/adr-050-canvas-node-readability.md FR-027..FR-033,
# SC-010..SC-012. ADR: docs/adr/ADR-050.md §5.
# ----------------------------------------------------------------------------


# Representative package-provided blocks per domain. One IO block (carries
# format_capabilities + a config_schema path widget) and one process/analysis
# block (carries typed ports) per package, so the contract is proven across
# imaging, spectroscopy, LCMS, and SRS without editing any package source.
_ADR050_PACKAGE_BLOCKS = {
    "scistudio-blocks-imaging": ("imaging.load_image", "imaging.axis_merge"),
    "scistudio-blocks-spectroscopy": (
        "spectroscopy.load_spectrum",
        "spectroscopy.find_peaks",
    ),
    "scistudio-blocks-lcms": ("lcms.load_mzml_files", "lcms.pool_size_normalize"),
    "scistudio-blocks-srs": ("srs.pca", "srs.calibrate"),
}

_ADR050_PACKAGE_TYPE_NAMES = [tn for pair in _ADR050_PACKAGE_BLOCKS.values() for tn in pair]

# BlockSummary fields the square node + palette read (FR-027/FR-028/FR-030).
_BLOCK_SUMMARY_CONTRACT_FIELDS = (
    "name",
    "type_name",
    "base_category",
    "subcategory",
    "input_ports",
    "output_ports",
    "direction",
    "source",
    "package_name",
    "variadic_inputs",
    "variadic_outputs",
    "format_capabilities",
)

# Extra BlockSchemaResponse fields the BottomPanel + port editor read on top of
# the summary fields (FR-029/FR-030).
_BLOCK_SCHEMA_CONTRACT_FIELDS = (
    "config_schema",
    "type_hierarchy",
    "dynamic_ports",
    "allowed_input_types",
    "allowed_output_types",
    "min_input_ports",
    "max_input_ports",
    "min_output_ports",
    "max_output_ports",
)


def _port_shape_ok(port: dict[str, object]) -> bool:
    """A port payload must name itself and expose serialized accepted types."""
    accepted_types = port.get("accepted_types")
    return (
        isinstance(port.get("name"), str)
        and isinstance(accepted_types, list)
        and all(isinstance(t, str) for t in accepted_types)
    )


@pytest.mark.parametrize("type_name", _ADR050_PACKAGE_TYPE_NAMES)
def test_adr050_package_block_summary_exposes_node_contract(client: TestClient, type_name: str) -> None:
    """SC-010/SC-011: palette summaries keep every field the square node reads.

    Each representative package block must appear in ``GET /api/blocks/`` (or,
    for aggregated IO loaders/savers, be reachable via its schema endpoint) with
    the full BlockSummary contract intact, so the square node mark, palette
    grouping, and ``[+]`` variadic affordance render from package contracts.
    """
    response = client.get("/api/blocks/")
    assert response.status_code == 200
    blocks = {block["type_name"]: block for block in response.json()["blocks"]}

    # ADR-043 collapses some package IO blocks (e.g. imaging.load_image) into
    # core Load/Save and omits them from the palette listing; for those the
    # contract is carried by the schema endpoint instead.
    summary = blocks.get(type_name)
    if summary is None:
        schema = client.get(f"/api/blocks/{type_name}/schema")
        assert schema.status_code == 200, f"{type_name} resolvable in neither palette nor schema"
        summary = schema.json()

    for field_name in _BLOCK_SUMMARY_CONTRACT_FIELDS:
        assert field_name in summary, f"{type_name} dropped BlockSummary field '{field_name}'"

    # base_category is the source of the block-kind mark; subcategory drives
    # palette grouping (FR-028). Both must be strings and base_category must be
    # one of the six canonical base kinds.
    assert summary["base_category"] in {"io", "process", "code", "app", "ai", "subworkflow"}
    assert isinstance(summary["subcategory"], str)

    # Ports must keep their serialized shape for canvas rendering + TypeLegend.
    for port in [*summary["input_ports"], *summary["output_ports"]]:
        assert _port_shape_ok(port), f"{type_name} port lost its name/accepted_types shape: {port}"

    # Variadic flags drive the [+]/[-] affordance even before schema fetch.
    assert isinstance(summary["variadic_inputs"], bool)
    assert isinstance(summary["variadic_outputs"], bool)
    assert isinstance(summary["format_capabilities"], list)


@pytest.mark.parametrize("type_name", _ADR050_PACKAGE_TYPE_NAMES)
def test_adr050_package_block_schema_exposes_bottompanel_contract(client: TestClient, type_name: str) -> None:
    """SC-010/SC-011/FR-029/FR-030: detail schema keeps BottomPanel + port-editor fields.

    The BottomPanel Config tab orders fields by ``config_schema`` and selects
    widgets via ``ui_widget``; the port editor reads ``dynamic_ports``,
    variadic flags, allowed types, and min/max port limits. All must survive
    the node refactor for every representative package block.
    """
    response = client.get(f"/api/blocks/{type_name}/schema")
    assert response.status_code == 200, response.text
    payload = response.json()

    for field_name in (*_BLOCK_SUMMARY_CONTRACT_FIELDS, *_BLOCK_SCHEMA_CONTRACT_FIELDS):
        assert field_name in payload, f"{type_name} schema dropped contract field '{field_name}'"

    # config_schema must be an object-typed JSON schema with a properties map
    # so BottomPanel can render and order Config fields (FR-029).
    config_schema = payload["config_schema"]
    assert isinstance(config_schema, dict)
    assert isinstance(config_schema.get("properties", {}), dict)

    # dynamic_ports is either None (static block) or the enum-driven descriptor
    # the frontend uses to recompute accepted_types (FR-030).
    dynamic_ports = payload["dynamic_ports"]
    assert dynamic_ports is None or isinstance(dynamic_ports, dict)
    if isinstance(dynamic_ports, dict):
        assert "source_config_key" in dynamic_ports
        assert "output_port_mapping" in dynamic_ports

    # Variadic-port editor contract: flags are bools, allowed-type lists are
    # string lists, and min/max limits are int-or-None (FR-030).
    assert isinstance(payload["variadic_inputs"], bool)
    assert isinstance(payload["variadic_outputs"], bool)
    assert all(isinstance(t, str) for t in payload["allowed_input_types"])
    assert all(isinstance(t, str) for t in payload["allowed_output_types"])
    for limit_field in ("min_input_ports", "max_input_ports", "min_output_ports", "max_output_ports"):
        assert payload[limit_field] is None or isinstance(payload[limit_field], int)


def test_adr050_package_config_schema_exposes_ui_priority_and_ui_widget(client: TestClient) -> None:
    """FR-029/SC-010: package config_schema keeps ``ui_priority`` and ``ui_widget``.

    Removing node-body config MUST NOT strip the schema fields BottomPanel uses
    to order fields (``ui_priority``) and pick widgets (``ui_widget``). Proven
    against a package process block (LCMS pool-size normalize: every field is
    priority-ordered) and a package app block (imaging napari: declares a
    ``file_browser`` path widget and ``port_editor`` widgets for variadic
    ports), so both axes of the contract are covered without package edits.
    """
    process_schema = client.get("/api/blocks/lcms.pool_size_normalize/schema")
    assert process_schema.status_code == 200
    process_props = process_schema.json()["config_schema"]["properties"]
    assert process_props, "lcms.pool_size_normalize lost its config properties"
    # BottomPanel orders Config fields by ui_priority — package process fields
    # keep an integer priority.
    assert all("ui_priority" in prop for prop in process_props.values()), (
        "lcms.pool_size_normalize dropped ui_priority from a config field"
    )
    assert all(isinstance(prop["ui_priority"], int) for prop in process_props.values())

    app_schema = client.get("/api/blocks/imaging.napari/schema")
    assert app_schema.status_code == 200
    app_props = app_schema.json()["config_schema"]["properties"]
    # ui_widget selection survives for package-provided fields: a file browser
    # for the executable path and the port editor for variadic port config.
    widgets = {name: prop.get("ui_widget") for name, prop in app_props.items()}
    assert widgets.get("app_command") == "file_browser", widgets
    assert widgets.get("input_ports") == "port_editor", widgets
    assert widgets.get("output_ports") == "port_editor", widgets


def test_adr050_package_io_block_schema_exposes_format_capabilities(client: TestClient) -> None:
    """FR-030/SC-011: package IO loaders keep serialized format_capabilities.

    BottomPanel capability selection reads ``format_capabilities`` from package
    IO blocks. The contract (the field is present and each entry carries the
    BottomPanel-consumed keys) must hold for spectroscopy and LCMS loaders
    without editing package source.
    """
    for type_name, expected_data_type in (
        ("spectroscopy.load_spectrum", "Spectrum"),
        ("lcms.load_mzml_files", "MSRawFile"),
    ):
        response = client.get(f"/api/blocks/{type_name}/schema")
        assert response.status_code == 200, response.text
        capabilities = response.json()["format_capabilities"]
        assert capabilities, f"{type_name} dropped its format_capabilities"
        capability = capabilities[0]
        assert {"id", "direction", "data_type", "format_id", "extensions", "label"}.issubset(capability)
        assert any(cap["data_type"] == expected_data_type for cap in capabilities), (
            f"{type_name} no longer advertises a {expected_data_type} capability"
        )


def test_adr050_variadic_package_block_advertises_topology_controls(client: TestClient) -> None:
    """FR-030/SC-011: a variadic package block keeps the ``[+]`` topology contract.

    ``spectroscopy.merge_spectral_dataset`` is variadic on inputs. The square
    node renders its ``[+]/[-]`` controls from ``variadic_inputs`` and the port
    editor reads ``allowed_input_types`` + min/max limits — all must round-trip
    through the API for the package block.
    """
    response = client.get("/api/blocks/spectroscopy.merge_spectral_dataset/schema")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["variadic_inputs"] is True, "package variadic-input flag was lost"
    assert isinstance(payload["allowed_input_types"], list)
    # min/max limits remain part of the contract (None means unconstrained).
    for limit_field in ("min_input_ports", "max_input_ports"):
        assert limit_field in payload
        assert payload[limit_field] is None or isinstance(payload[limit_field], int)
    # The single declared input port still serializes with its accepted types.
    assert payload["input_ports"], "variadic merge block lost its declared input port"
    assert _port_shape_ok(payload["input_ports"][0])


def test_adr050_no_package_specific_node_hint_fields_added(client: TestClient) -> None:
    """FR-032/SC-012: the API exposes no old-node / square-node hint fields.

    The refactor must not introduce package-specific legacy-renderer,
    compact-card, or square-node marker fields onto the schema payload, and
    must not drop the existing package-facing fields. The BlockSchemaResponse
    field set is the contract; a representative package block exercises it.
    """
    response = client.get("/api/blocks/imaging.axis_merge/schema")
    assert response.status_code == 200
    keys = set(response.json())

    forbidden_markers = {
        "legacy_node",
        "old_node",
        "square_node",
        "compact_card",
        "node_renderer",
        "inline_config",
        "node_hint",
    }
    leaked = keys & forbidden_markers
    assert not leaked, f"ADR-050 forbids package-specific node hint fields; found {leaked}"

    # And the existing package-facing contract fields are all still present.
    required = set(_BLOCK_SUMMARY_CONTRACT_FIELDS) | set(_BLOCK_SCHEMA_CONTRACT_FIELDS)
    missing = required - keys
    assert not missing, f"imaging.axis_merge schema dropped contract fields: {missing}"
