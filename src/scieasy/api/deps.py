"""FastAPI dependency injection for shared API runtime objects."""

from __future__ import annotations

from pathlib import Path
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
    """Return the lineage store for the active project."""
    runtime = get_runtime(request)
    try:
        project = runtime.require_active_project()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from scieasy.core.lineage.store import LineageStore

    return LineageStore(Path(project.path) / "lineage" / "lineage.db")


def get_process_registry(request: Request) -> ProcessRegistry:
    """Retrieve the shared ProcessRegistry from app state."""
    registry: ProcessRegistry | None = getattr(request.app.state, "registry", None)
    if registry is None:
        raise RuntimeError("ProcessRegistry not initialized -- app lifespan not started")
    return registry
