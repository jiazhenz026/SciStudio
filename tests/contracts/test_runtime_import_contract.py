"""Architecture contract tests for runtime import and public-API invariants.

Issue #1452: remaining architecture contract tests for runtime surfaces.

This file covers the following contract surfaces not yet exercised by
the other contract files in tests/contracts/:

1. **Runtime module import contract**: Key runtime packages must be
   importable without side effects (no DB connections, no file I/O,
   no network) and must expose their documented public surfaces.

2. **API route contract**: The REST API must expose all documented
   workflow, block, filesystem, AI, and data endpoints. Adding a new
   route is fine; silently removing a documented endpoint is a
   contract break.

3. **MCP tool registry contract**: The MCP server must always expose
   exactly 34 tools (ADR-040 §3.1 + Addendum 5 + ADR-048 SPEC 2 plot + edit_workflow #1912
   tools). This is a separate
   invariant from the parity test in test_mcp_fastmcp.py — it ensures
   the contract is also enforced from the contracts test suite so that
   CI failure is clearly labelled as an architecture regression.

4. **BlockRegistry public-API contract**: The registry must expose
   ``all_specs()``, ``get_spec()``, and ``scan()`` as stable entry
   points. The block count is not part of the contract (it grows as
   new blocks are added), but the API shape is.

5. **TypeRegistry internal runtime-registry shape**: ADR-052 §3.9
   demotes ``TypeRegistry`` to **internal** (dropped from
   ``scistudio.core.types.__all__``; 0 author-facing importers). It is
   no longer a public-API contract. These remain useful invariants on the
   *internal* registry reached via the deep
   ``scistudio.core.types.registry`` path: ``all_types()`` and
   ``scan_builtins()`` keep their shape and built-in types include the
   documented base data objects — an internal-stability check, not an
   author-facing promise.

TODO(#1452): EventBus block_type contract (4 xfail rows), MCP/API
  schema parity contract (2 xfail rows), and IO roundtrip group
  declarations (2 xfail rows) require product-code changes and are
  tracked under issue #1452. Out of scope for this test-only PR.
  Followup: https://github.com/zjzcpj/SciStudio/issues/1452
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Mapping

import pytest

# ---------------------------------------------------------------------------
# 1. Runtime module import contract.
# ---------------------------------------------------------------------------


_REQUIRED_RUNTIME_MODULES = [
    # Core workflow definition layer.
    "scistudio.workflow.definition",
    # Engine layer.
    "scistudio.engine.events",
    "scistudio.engine.scheduler",
    # Block layer.
    "scistudio.blocks.registry",
    "scistudio.blocks.base.block",
    "scistudio.blocks.base.ports",
    # Type layer.
    "scistudio.core.types.registry",
    # AI agent layer.
    "scistudio.ai.agent.mcp.server",
    "scistudio.ai.agent.mcp._context",
    # API layer (no DB/network side effects at import time).
    "scistudio.api.app",
]


@pytest.mark.parametrize("module_path", _REQUIRED_RUNTIME_MODULES)
def test_runtime_module_imports_without_error(module_path: str) -> None:
    """Each documented runtime module must import cleanly.

    This catches renamed or deleted modules before any runtime code
    runs — an import error here means a contract break for every
    downstream consumer (frontend, CI, deployment).
    """
    mod = importlib.import_module(module_path)
    assert mod is not None, f"import returned None for {module_path}"


# ---------------------------------------------------------------------------
# 2. API route contract.
# ---------------------------------------------------------------------------


_REQUIRED_WORKFLOW_ROUTES = {
    # CRUD
    "/api/workflows/list",
    "/api/workflows/",
    "/api/workflows/{workflow_id}",
    # Execution lifecycle
    "/api/workflows/{workflow_id}/execute",
    "/api/workflows/{workflow_id}/cancel",
}

_REQUIRED_BLOCK_ROUTES = {
    "/api/blocks/",
    "/api/blocks/{block_type}/schema",
    "/api/blocks/validate-connection",
}

_REQUIRED_FILESYSTEM_ROUTES = {
    "/api/filesystem/browse",
    "/api/filesystem/native-dialog",
}

_REQUIRED_AI_ROUTES = {
    "/api/ai/active-context",
    "/api/ai/status",
}


def _has_contract_field(spec: object, field: str) -> bool:
    """Return whether a registry spec exposes a required field."""
    return hasattr(spec, field) or (isinstance(spec, Mapping) and field in spec)


def _collect_route_paths(routes: object, prefix: str = "") -> set[str]:
    """Recursively collect route paths, tolerant of Starlette's layouts.

    Starlette < 1.3 flattens ``include_router`` children directly into
    ``app.routes`` (each route exposes ``.path``). Starlette >= 1.3 (pulled in
    by FastAPI 0.138) instead inserts a single ``_IncludedRouter`` object with
    no ``.path``; the real routes live under ``route.original_router.routes``
    and the mount prefix under ``route.include_context.prefix`` (#1769). This
    helper handles both so the route contract is dependency-version agnostic.
    """
    paths: set[str] = set()
    for route in routes:  # type: ignore[union-attr]
        path = getattr(route, "path", None)
        if path is not None:
            paths.add(prefix + path)
        included = getattr(route, "original_router", None)
        if included is not None:
            context = getattr(route, "include_context", None)
            nested_prefix = prefix + (getattr(context, "prefix", "") or "")
            paths |= _collect_route_paths(getattr(included, "routes", ()), nested_prefix)
    return paths


@pytest.fixture(scope="module")
def app_routes() -> set[str]:
    """Collect all registered route paths from the FastAPI app."""
    from scistudio.api.app import create_app

    app = create_app()
    return _collect_route_paths(app.routes)


def test_fastapi_router_paths_remain_visible_to_contract_tests() -> None:
    """FastAPI dependency updates must preserve route path introspection."""
    from fastapi import APIRouter, FastAPI

    router = APIRouter()

    @router.get("/contract-route")
    def contract_route() -> dict[str, bool]:
        return {"ok": True}

    app = FastAPI()
    app.include_router(router)

    route_paths = _collect_route_paths(app.routes)
    assert "/contract-route" in route_paths


def test_api_workflow_routes_are_registered(app_routes: set[str]) -> None:
    """Workflow CRUD and lifecycle endpoints must always be registered."""
    missing = _REQUIRED_WORKFLOW_ROUTES - app_routes
    assert not missing, f"Missing workflow API routes (contract break — #1452): {sorted(missing)}"


def test_api_block_routes_are_registered(app_routes: set[str]) -> None:
    """Block palette, schema, and connection-validation endpoints must be registered."""
    missing = _REQUIRED_BLOCK_ROUTES - app_routes
    assert not missing, f"Missing block API routes (contract break — #1452): {sorted(missing)}"


def test_api_filesystem_routes_are_registered(app_routes: set[str]) -> None:
    """Filesystem browse and native-dialog endpoints must be registered."""
    missing = _REQUIRED_FILESYSTEM_ROUTES - app_routes
    assert not missing, f"Missing filesystem API routes (contract break — #1452): {sorted(missing)}"


def test_api_ai_routes_are_registered(app_routes: set[str]) -> None:
    """AI active-context and status endpoints must be registered."""
    missing = _REQUIRED_AI_ROUTES - app_routes
    assert not missing, f"Missing AI API routes (contract break — #1452): {sorted(missing)}"


# ---------------------------------------------------------------------------
# 3. MCP tool registry contract.
# ---------------------------------------------------------------------------

# ADR-040 §3.1 + Addendum 5 (#1488) + ADR-048 SPEC 2 + edit_workflow (#1912): 34 tools total.
_MCP_EXPECTED_TOOL_NAMES = {
    # category (a) workflow (11 + 1 addendum5)
    "list_blocks",
    "get_block_schema",
    "list_types",
    "get_workflow",
    "validate_workflow",
    "write_workflow",
    "edit_workflow",
    "run_workflow",
    "cancel_run",
    "get_run_status",
    "finish_ai_block",
    "get_active_workflow_context",
    # category (b) authoring (5)
    "read_block_source",
    "list_block_examples",
    "scaffold_block",
    "reload_blocks",
    "run_block_tests",
    # category (c) inspection (7)
    "get_block_output",
    "inspect_data",
    "preview_data",
    "get_lineage",
    "get_block_config",
    "update_block_config",
    "get_block_logs",
    # category (d) qa (4)
    "search_docs",
    "get_doc",
    "list_data",
    "get_project_info",
    # category (e) plot (6) — ADR-048 SPEC 2
    "list_plot_targets",
    "scaffold_plot",
    "list_plot_examples",
    "read_plot_source",
    "validate_plot",
    "run_plot_job",
}
_MCP_EXPECTED_COUNT = 34


def test_mcp_server_exposes_34_tools() -> None:
    """ADR-040 §3.1 + Addendum 5 + ADR-048 SPEC 2 + edit_workflow (#1912): MCP server must expose 34 tools.

    This contract test mirrors the parity check in test_mcp_fastmcp.py but
    lives in the contracts suite so a regression is flagged as an
    architecture contract break rather than a unit-test failure.
    """
    from scistudio.ai.agent.mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    actual_names = {t.name for t in tools}
    assert len(tools) == _MCP_EXPECTED_COUNT, (
        f"MCP tool count changed: expected {_MCP_EXPECTED_COUNT}, got {len(tools)}. "
        f"Added: {actual_names - _MCP_EXPECTED_TOOL_NAMES}, "
        f"Removed: {_MCP_EXPECTED_TOOL_NAMES - actual_names}"
    )
    assert actual_names == _MCP_EXPECTED_TOOL_NAMES, (
        f"MCP tool set changed (contract break — ADR-040 §3.1 / #1452). "
        f"Added: {actual_names - _MCP_EXPECTED_TOOL_NAMES}. "
        f"Removed: {_MCP_EXPECTED_TOOL_NAMES - actual_names}."
    )


# ---------------------------------------------------------------------------
# 4. BlockRegistry public-API contract.
# ---------------------------------------------------------------------------


def test_block_registry_public_api_shape() -> None:
    """BlockRegistry must expose ``scan()``, ``all_specs()``, and ``get_spec()``."""
    from scistudio.blocks.registry import BlockRegistry

    reg = BlockRegistry()
    # Structural check: methods must exist and be callable.
    assert callable(getattr(reg, "scan", None)), "BlockRegistry.scan() must be callable"
    assert callable(getattr(reg, "all_specs", None)), "BlockRegistry.all_specs() must be callable"
    assert callable(getattr(reg, "get_spec", None)), "BlockRegistry.get_spec() must be callable"

    # Functional check: scan populates the registry with at least one spec.
    reg.scan()
    specs = reg.all_specs()
    assert isinstance(specs, dict), f"all_specs() must return a dict, got {type(specs).__name__}"
    assert len(specs) > 0, "BlockRegistry.all_specs() returned an empty dict after scan()"

    # Round-trip: every type_name from all_specs() must be retrievable via get_spec().
    for type_name in specs:
        spec = reg.get_spec(type_name)
        assert spec is not None, f"get_spec({type_name!r}) returned None after all_specs() listed it"


def test_block_spec_has_required_contract_fields() -> None:
    """Every block spec from the registry must expose the documented contract fields.

    This is an import-layer check only — it does not require the full
    JSON API shape (that is covered by test_block_schema_contract.py).
    The fields tested here are the ones consumed by the scheduler and
    the connection validator.
    """
    from scistudio.blocks.registry import BlockRegistry

    reg = BlockRegistry()
    reg.scan()
    for type_name, spec in reg.all_specs().items():
        # spec must have a type_name that matches the key.
        assert _has_contract_field(spec, "type_name"), f"Block spec for {type_name!r} has no type_name"
        # spec must have input_ports and output_ports accessible.
        assert _has_contract_field(spec, "input_ports"), f"Block spec for {type_name!r} has no input_ports"
        assert _has_contract_field(spec, "output_ports"), f"Block spec for {type_name!r} has no output_ports"


# ---------------------------------------------------------------------------
# 5. TypeRegistry internal runtime-registry shape.
#    ADR-052 §3.9 demotes TypeRegistry to internal (dropped from
#    scistudio.core.types.__all__). The checks below assert the INTERNAL
#    registry shape reached via the deep scistudio.core.types.registry path —
#    not an author-facing public-API promise.
# ---------------------------------------------------------------------------

# Documented base data objects from ADR-033 / scistudio core type tree.
# Note: ``Image`` is a plugin type registered by the imaging extension, NOT
# a builtin. ``scan_builtins()`` only loads the core data model types.
# TODO(#1452): A separate contract test should verify imaging plugin types
#   after a full plugin scan. Out of scope for this test-only PR.
#   Followup: https://github.com/zjzcpj/SciStudio/issues/1452
_REQUIRED_BUILTIN_TYPES = {
    "DataObject",
    "Array",
    "DataFrame",
    "Artifact",
    "Series",
    "Text",
}


def test_type_registry_internal_shape() -> None:
    """Internal ``TypeRegistry`` must expose ``scan_builtins()`` and ``all_types()``.

    ADR-052 §3.9: ``TypeRegistry`` is internal (reached via the deep
    ``scistudio.core.types.registry`` path), not public API.
    """
    from scistudio.core.types.registry import TypeRegistry

    tr = TypeRegistry()
    assert callable(getattr(tr, "scan_builtins", None)), "TypeRegistry.scan_builtins() must be callable"
    assert callable(getattr(tr, "all_types", None)), "TypeRegistry.all_types() must be callable"

    tr.scan_builtins()
    types = tr.all_types()
    assert isinstance(types, (dict, list)), f"all_types() must return a dict or list, got {type(types).__name__}"


def test_type_registry_has_required_builtin_types() -> None:
    """Built-in type scan must register all documented core data objects."""
    from scistudio.core.types.registry import TypeRegistry

    tr = TypeRegistry()
    tr.scan_builtins()
    all_t = tr.all_types()
    # Normalize: may be a dict keyed by name or a list of entries with .name.
    if isinstance(all_t, dict):
        registered = set(all_t.keys())
    else:
        registered = {getattr(t, "name", None) or t.get("name") for t in all_t}

    missing = _REQUIRED_BUILTIN_TYPES - registered
    assert not missing, (
        f"TypeRegistry after scan_builtins() is missing required types: {sorted(missing)}. "
        f"Contract break — these types are consumed by connection validation and MCP (ADR-040 / #1452)."
    )
