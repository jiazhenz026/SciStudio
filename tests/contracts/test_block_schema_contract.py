"""Contract tests for block registry/schema single-source API payloads.

Issues #1452/#1454, slice 3: the backend block registry is the source of truth for
palette, schema, connection validation, and MCP-facing schema helpers.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scistudio.ai.agent.mcp import _context, tools_workflow
from scistudio.api.app import create_app

IDENTITY_FIELDS = ("name", "type_name", "base_category", "source", "package_name")
SCHEMA_CONTRACT_FIELDS = {
    "ports",
    "config_schema",
    "type_hierarchy",
    "format_capabilities",
    "source",
    "package_name",
    "base_category",
}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Create an API client with isolated user state for contract tests."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    from scistudio.api import runtime as runtime_module

    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake_home))

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def _palette_by_type(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.get("/api/blocks/")
    assert response.status_code == 200
    return {block["type_name"]: block for block in response.json()["blocks"]}


def _schema(client: TestClient, type_name: str) -> dict[str, Any]:
    response = client.get(f"/api/blocks/{type_name}/schema")
    assert response.status_code == 200
    return response.json()


def _representative_type_names(palette: dict[str, dict[str, Any]]) -> list[str]:
    representatives: list[str] = []

    for candidate in ("load_data", "ai.agent", "subworkflow_block", "noop", "process_block"):
        if candidate in palette:
            representatives.append(candidate)
            break
    else:
        pytest.fail("Expected at least one representative built-in block in /api/blocks/.")

    if "code_block" in palette:
        representatives.append("code_block")

    plugin_or_imaging = next(
        (
            type_name
            for type_name, block in palette.items()
            if block.get("package_name") == "scistudio-blocks-imaging" or type_name.startswith("imaging.")
        ),
        None,
    )
    if plugin_or_imaging is not None:
        representatives.append(plugin_or_imaging)

    return representatives


def test_palette_items_and_schema_identity_fields_match_for_representative_blocks(client: TestClient) -> None:
    """Palette summaries and schema payloads must agree on registry identity."""
    palette = _palette_by_type(client)

    for type_name in _representative_type_names(palette):
        palette_item = palette[type_name]
        schema_payload = _schema(client, type_name)

        for field in IDENTITY_FIELDS:
            assert schema_payload[field] == palette_item[field], (
                f"{type_name} has mismatched {field!r}: "
                f"palette={palette_item[field]!r}, schema={schema_payload[field]!r}"
            )


@pytest.mark.xfail(
    reason="#1454: schema payloads do not yet expose the desired unified ports envelope.",
    strict=False,
)
def test_schema_payload_exposes_stable_contract_fields(client: TestClient) -> None:
    """Block schemas should expose one stable API contract envelope."""
    type_name = _representative_type_names(_palette_by_type(client))[0]
    schema_payload = _schema(client, type_name)

    missing = SCHEMA_CONTRACT_FIELDS.difference(schema_payload)
    assert not missing, f"{type_name} schema missing contract fields: {sorted(missing)}"
    assert {"input", "output"}.issubset(schema_payload["ports"])
    assert isinstance(schema_payload["config_schema"], dict)
    assert isinstance(schema_payload["type_hierarchy"], list)
    assert isinstance(schema_payload["format_capabilities"], list)


def test_connection_validation_uses_backend_registry_type_information(client: TestClient) -> None:
    """Connection validation should need only block/port identifiers from the client."""
    palette = _palette_by_type(client)
    if not {"load_data", "save_data"}.issubset(palette):
        pytest.skip("load_data/save_data are unavailable in this registry.")

    source_schema = _schema(client, "load_data")
    target_schema = _schema(client, "save_data")
    source_port = source_schema["output_ports"][0]["name"]
    target_port = target_schema["input_ports"][0]["name"]

    response = client.post(
        "/api/blocks/validate-connection",
        json={
            "source_block": "load_data",
            "source_port": source_port,
            "target_block": "save_data",
            "target_port": target_port,
        },
    )
    assert response.status_code == 200
    assert response.json()["compatible"] is True

    missing_port = client.post(
        "/api/blocks/validate-connection",
        json={
            "source_block": "load_data",
            "source_port": "__frontend_only_fake_port__",
            "target_block": "save_data",
            "target_port": target_port,
        },
    )
    assert missing_port.status_code == 404


@pytest.mark.xfail(
    reason="#1454: MCP get_block_schema is not yet API-equivalent for identity and schema fields.",
    strict=False,
)
def test_mcp_and_api_schema_payloads_share_block_registry_source_of_truth(client: TestClient) -> None:
    """MCP workflow helpers and HTTP schema payloads should expose equivalent contracts."""
    type_name = _representative_type_names(_palette_by_type(client))[0]
    api_schema = _schema(client, type_name)

    _context.set_context(client.app.state.runtime)
    try:
        mcp_schema = asyncio.run(tools_workflow.get_block_schema(type_name)).model_dump()
    finally:
        _context.set_context(None)

    assert mcp_schema["type_name"] == api_schema["type_name"]
    assert mcp_schema["config_schema"] == api_schema["config_schema"]
    assert mcp_schema["ports"] == api_schema["ports"]
