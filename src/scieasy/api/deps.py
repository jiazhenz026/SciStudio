"""FastAPI dependency injection for shared API runtime objects."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from scieasy.api.runtime import ApiRuntime
from scieasy.engine.runners.process_handle import ProcessRegistry


def get_runtime(request: Request) -> ApiRuntime:
    """Return the shared API runtime."""
    return request.app.state.runtime  # type: ignore[no-any-return]


def get_engine(request: Request) -> ApiRuntime:
    """Return the workflow execution runtime."""
    return get_runtime(request)


def get_block_registry(request: Request) -> Any:
    """Return the shared block registry instance."""
    return get_runtime(request).block_registry


def get_type_registry(request: Request) -> Any:
    """Return the shared type registry instance."""
    return get_runtime(request).type_registry


def get_lineage_store(request: Request) -> Any:
    """Return the unified ADR-038 lineage store for the active project.

    The store is owned by :class:`ApiRuntime` and shared across routes — the
    previous per-call ``LineageStore(...)`` construction was an orphan that
    opened a second SQLite handle per request. After ADR-038 the runtime
    opens one store per project on ``open_project`` and routes acquire that
    same instance here.
    """
    runtime = get_runtime(request)
    try:
        runtime.require_active_project()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    store = runtime.lineage_store
    if store is None:
        raise HTTPException(status_code=503, detail="Lineage store not initialised for this project")
    return store


def get_process_registry(request: Request) -> ProcessRegistry:
    """Retrieve the shared ProcessRegistry from app state."""
    registry: ProcessRegistry | None = getattr(request.app.state, "registry", None)
    if registry is None:
        raise RuntimeError("ProcessRegistry not initialized -- app lifespan not started")
    return registry
