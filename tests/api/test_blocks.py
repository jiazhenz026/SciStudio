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


def test_block_source_endpoint_returns_core_block_source(client: TestClient) -> None:
    """#1758: GET /api/blocks/{type}/source returns a core block's source."""
    response = client.get("/api/blocks/load_data/source")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["block_type"] == "load_data"
    assert payload["language"] == "python"
    assert payload["origin"] == "builtin"
    assert payload["path"].endswith("load_data.py")
    # The returned text is the real module source, not a placeholder.
    assert "class LoadData" in payload["source"]


def test_block_source_endpoint_unknown_type_is_404(client: TestClient) -> None:
    """An unregistered block type resolves to 404, not a server error."""
    response = client.get("/api/blocks/no_such_block_type/source")
    assert response.status_code == 404
