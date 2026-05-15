"""Placeholder routes for ADR-038 run history.

D38-2.2 scope: register the router so Phase D38-2.4a (the backend REST agent)
extends an existing module rather than wiring the import path from scratch.
The actual routes — ``GET /api/runs``, ``GET /api/runs/{run_id}``,
``GET /api/runs/{run_id}/methods``, ``POST /api/runs/{run_id}/rerun`` —
are filled in by D38-2.4a per ADR-038 §3.7.

For now the only endpoint is a health-check that confirms the unified
lineage store is reachable. It is intentionally minimal; consumers should
treat the surface as unstable until D38-2.4a ships.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from scieasy.api.deps import get_lineage_store

router = APIRouter(prefix="/api/runs", tags=["runs"])

# Module-level Depends() singleton — FastAPI / ruff B008 best practice.
_LineageStoreDep = Depends(get_lineage_store)


@router.get("/_health")
def runs_health(store: Any = _LineageStoreDep) -> dict[str, Any]:
    """Return the per-table row count for the active project's lineage DB.

    Useful during Phase D38-2.2 smoke testing; D38-2.4a may keep or replace it.
    """
    return {
        "runs": store.count("runs"),
        "block_executions": store.count("block_executions"),
        "data_objects": store.count("data_objects"),
        "block_io": store.count("block_io"),
    }
