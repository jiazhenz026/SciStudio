"""Tests for API dependency helpers."""

from __future__ import annotations

from starlette.requests import Request

from scistudio.api import deps


def test_dependency_helpers_resolve_runtime_objects(client, opened_project) -> None:
    """Dependency helpers should surface shared runtime objects from app state."""
    request = Request({"type": "http", "app": client.app})
    runtime = client.app.state.runtime

    assert deps.get_runtime(request) is runtime
    assert deps.get_engine(request) is runtime
    assert deps.get_block_registry(request) is runtime.block_registry
    assert deps.get_type_registry(request) is runtime.type_registry

    # ADR-038 §3.1: the unified lineage store lives under ``.scistudio/`` and is
    # owned by the runtime — ``get_lineage_store`` must return that shared
    # instance, not allocate a fresh one per request.
    lineage_store = deps.get_lineage_store(request)
    assert lineage_store is runtime.lineage_store
    db_path = lineage_store._db_path
    assert db_path.endswith(".scistudio\\lineage.db") or db_path.endswith(".scistudio/lineage.db")
