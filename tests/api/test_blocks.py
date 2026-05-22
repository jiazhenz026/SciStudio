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


def test_code_block_builtin_schema_is_registered(client: TestClient) -> None:
    """The concrete CodeBlock runtime must be visible to workflows and the UI."""
    response = client.get("/api/blocks/")
    assert response.status_code == 200
    blocks = response.json()["blocks"]
    assert any(block["type_name"] == "code_block" for block in blocks)

    schema = client.get("/api/blocks/code_block/schema")
    assert schema.status_code == 200
    payload = schema.json()
    assert payload["name"] == "Code Block"
    assert payload["type_name"] == "code_block"
    assert payload["base_category"] == "code"
    assert payload["config_schema"]["required"] == ["script_path"]
    assert "script_path" in payload["config_schema"]["properties"]


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
            "target_block": "Merge",
            "target_port": "left",
        },
    )
    assert bidirectional.status_code == 200
    assert bidirectional.json()["compatible"] is True


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
    """ADR-043 capabilities must not expand one aggregate IOBlock into many blocks."""
    response = client.get("/api/blocks/")
    assert response.status_code == 200
    blocks = response.json()["blocks"]

    load_image_blocks = [block for block in blocks if block["type_name"] == "imaging.load_image"]
    assert len(load_image_blocks) == 1
    assert load_image_blocks[0]["format_capabilities"]


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
