"""REST endpoints for ADR-038 run history (`/api/runs`).

Endpoints (ADR-038 §3.7, §3.8):

* ``GET  /api/runs``                       -- list runs (reverse-chrono), optional ``workflow_id`` filter + pagination
* ``GET  /api/runs/{run_id}``              -- full run detail with joined block_executions
* ``GET  /api/runs/{run_id}/methods``      -- markdown methods export (``Content-Type: text/markdown``)
* ``POST /api/runs/{run_id}/rerun``        -- queue a new run from the recorded workflow snapshot

The lineage store is project-scoped -- every endpoint requires an active
project. Failures resolve to ``400 Bad Request`` (no active project) or
``404 Not Found`` (unknown run / unknown workflow).

The implementation is intentionally thin: it delegates row access to
:class:`LineageStore` (ADR-038 §3.1, §5.1) and methods rendering to
:mod:`scistudio.core.lineage.methods_export`. Routes are read-only against
the lineage store; only ``/rerun`` mutates engine state (and that goes
through the existing :meth:`ApiRuntime.start_workflow` path so the new
run is recorded just like any user-initiated start).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from scistudio.api.deps import get_lineage_store, get_runtime
from scistudio.api.runtime import ApiRuntime
from scistudio.core.lineage.methods_export import render_methods_markdown

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])

# Module-level Depends() singletons -- FastAPI / ruff B008 best practice.
_LineageStoreDep = Depends(get_lineage_store)
_RuntimeDep = Depends(get_runtime)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RerunRequest(BaseModel):
    """Body for ``POST /api/runs/{run_id}/rerun``.

    ``execute_from_block_id`` is optional. When set, the new run executes
    only from that block forward, reusing upstream outputs from the most
    recent checkpoint per ADR-038 §3.6a. When unset, the whole workflow
    is re-run from scratch.
    """

    execute_from_block_id: str | None = Field(
        default=None,
        description="Optional block id to start execution from (ADR-038 §3.6a).",
    )


# ---------------------------------------------------------------------------
# GET /api/runs/_health -- preserved from the D38-2.2 placeholder
# Must be declared BEFORE /{run_id} so the literal segment matches first.
# ---------------------------------------------------------------------------


@router.get("/_health")
def runs_health(store: Any = _LineageStoreDep) -> dict[str, Any]:
    """Per-table row count for the active project's lineage DB.

    Retained from the D38-2.2 placeholder so the smoke-test invocation
    used during the unified-store wire-up keeps working.
    """
    return {
        "runs": store.count("runs"),
        "block_executions": store.count("block_executions"),
        "data_objects": store.count("data_objects"),
        "block_io": store.count("block_io"),
    }


# ---------------------------------------------------------------------------
# GET /api/runs -- list runs
# ---------------------------------------------------------------------------


@router.get("/", include_in_schema=False)
@router.get("")
def list_runs(
    workflow_id: str | None = Query(default=None, description="Filter by workflow_id."),
    offset: int = Query(default=0, ge=0, description="Pagination offset (>=0)."),
    limit: int = Query(default=50, ge=1, le=500, description="Pagination limit (1..500)."),
    store: Any = _LineageStoreDep,
) -> dict[str, Any]:
    """List runs in reverse-chronological order.

    The store's ``list_runs`` returns rows already sorted ``started_at DESC``;
    we slice in Python for pagination. The current row count is bounded by
    project lifetime (KB-MB scale per ADR-038 §7.3) so in-memory slicing is
    fine for v1; a SQL ``LIMIT/OFFSET`` extension can replace this if it ever
    matters.
    """
    # Fetch one full page (offset+limit) so we can do slice + total count.
    # Use a generous upper bound to support pagination without re-querying.
    all_rows = store.list_runs(workflow_id=workflow_id, limit=offset + limit + 1)
    page = all_rows[offset : offset + limit]
    has_more = len(all_rows) > offset + limit
    return {
        "runs": page,
        "offset": offset,
        "limit": limit,
        "has_more": has_more,
    }


# ---------------------------------------------------------------------------
# GET /api/runs/{run_id} -- full detail
# ---------------------------------------------------------------------------


@router.get("/{run_id}")
def get_run(run_id: str, store: Any = _LineageStoreDep) -> dict[str, Any]:
    """Return one run row plus its joined ``block_executions`` rows.

    Per ADR-038 §3.7 (Q3/Q4) we surface block_executions ordered by
    ``started_at`` so the UI can render the per-block timeline directly.

    Hotfix #996: per-block I/O DataObjects are now **inlined** as
    ``block_executions[i].inputs`` / ``.outputs`` arrays. ADR-038 §3.7
    Q4b "Per-block I/O DataObjects?" SQL is materialised via one
    batched query (``LineageStore.list_block_io_with_objects(run_id)``)
    and bucketed in Python. Pre-#996 the route returned a hand-waved
    "clients fetch on demand" placeholder, but no separate endpoint was
    ever wired up, so the Lineage tab block cards rendered "0 inputs /
    0 outputs" for every block (Phase 4a finding).

    Each I/O entry has shape::

        {
          "direction": "input" | "output",
          "port_name": str,
          "position": int,
          "object_id": str,
          "type_name": str,          # e.g. "Image" / "Mask"
          "backend": str | None,     # e.g. "zarr"
          "storage_path": str | None,
          "produced_by_execution": str | None,  # FK to block_executions
        }

    ``wire_payload`` is intentionally excluded from the response -- its
    KB-scale per-object JSON would balloon the payload (ADR-038 §3.1
    Collection unrolling note: ~1-2 KB per item x many items x many
    blocks). Clients that need the full wire-format dict can query
    ``GET /api/runs/{run_id}/data-objects/{object_id}`` (deferred to a
    follow-up endpoint; v1 reference-by-id is sufficient for the tab).
    """
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run_id {run_id!r} not found")
    block_executions = store.list_block_executions(run_id)

    # Bucket I/O rows into each block_execution. One batched query keeps
    # the response O(rows) instead of O(blocks x round-trips).
    io_rows = store.list_block_io_with_objects(run_id)
    inputs_by_be: dict[str, list[dict[str, Any]]] = {}
    outputs_by_be: dict[str, list[dict[str, Any]]] = {}
    for row in io_rows:
        be_id = row["block_execution_id"]
        entry = {
            "direction": row["direction"],
            "port_name": row["port_name"],
            "position": row["position"],
            "object_id": row["object_id"],
            "type_name": row["type_name"],
            "backend": row["backend"],
            "storage_path": row["storage_path"],
            "produced_by_execution": row["produced_by_execution"],
        }
        bucket = inputs_by_be if row["direction"] == "input" else outputs_by_be
        bucket.setdefault(be_id, []).append(entry)

    for be in block_executions:
        be_id = be["block_execution_id"]
        be["inputs"] = inputs_by_be.get(be_id, [])
        be["outputs"] = outputs_by_be.get(be_id, [])

    return {
        "run": run,
        "block_executions": block_executions,
    }


# ---------------------------------------------------------------------------
# GET /api/runs/{run_id}/methods -- markdown export
# ---------------------------------------------------------------------------


@router.get("/{run_id}/methods", response_class=PlainTextResponse)
def get_run_methods(run_id: str, store: Any = _LineageStoreDep) -> PlainTextResponse:
    """Return the methods-section markdown body for a run.

    Served as ``text/markdown; charset=utf-8`` so the browser can offer
    "View source" instead of attempting to render it as HTML. The body
    answers ADR-038 §3.7 Q1-Q4 in one document; see
    :mod:`scistudio.core.lineage.methods_export` for the renderer.
    """
    if store.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail=f"run_id {run_id!r} not found")
    body = render_methods_markdown(store, run_id)
    return PlainTextResponse(content=body, media_type="text/markdown; charset=utf-8")


# ---------------------------------------------------------------------------
# POST /api/runs/{run_id}/rerun -- queue a new run
# ---------------------------------------------------------------------------


@router.post("/{run_id}/rerun")
async def rerun_run(
    run_id: str,
    body: RerunRequest,
    store: Any = _LineageStoreDep,
    runtime: ApiRuntime = _RuntimeDep,
) -> dict[str, Any]:
    """Queue a re-run of the workflow that produced ``run_id``.

    Must be ``async def`` so the handler executes on the asyncio event-loop
    thread rather than FastAPI's sync threadpool:
    :meth:`ApiRuntime.start_workflow` schedules the run via
    :func:`asyncio.create_task`, which raises ``RuntimeError("no running
    event loop")`` from a threadpool caller and leaves the lineage
    ``runs`` row stranded in ``running`` state (the row is inserted
    before ``create_task`` is reached). The sibling
    ``POST /api/workflows/{id}/execute`` handler is async for the same
    reason.

    The new run is created via :meth:`ApiRuntime.start_workflow` against
    the historical run's ``workflow_id``. The runtime constructs a fresh
    ``run_id`` and records it in the lineage store; this endpoint does
    NOT manually insert anything into ``runs``.

    Notes
    -----
    Per ADR-038 §3.6a, re-running with ``execute_from_block_id`` set
    requires the checkpoint to be present (the latest run's intermediate
    state). The runtime raises ``ValueError`` ("Run the full workflow at
    least once …") when that precondition is not met -- we surface it as
    a 400.

    Re-running an older historical run (one whose intermediate data has
    been overwritten by later runs) is **not** supported per ADR §3.6a;
    the user is directed to run the full workflow from start instead.
    The runtime's checkpoint resolution already enforces this; we don't
    duplicate the check here.

    The "input file size+mtime check" and "environment drift check"
    listed in ADR §6 Phase 3 are advisory warnings emitted by the
    frontend ``RerunDialog`` (D38-2.4b/c) before this endpoint is
    called; this route does not re-implement them.
    """
    historical = store.get_run(run_id)
    if historical is None:
        raise HTTPException(status_code=404, detail=f"run_id {run_id!r} not found")

    workflow_id = historical.get("workflow_id")
    if not workflow_id:
        # Defensive: a runs row without workflow_id is malformed, but we
        # surface the failure as 422 so the client can distinguish from a
        # plain "run not found".
        raise HTTPException(
            status_code=422,
            detail=f"run {run_id!r} has no workflow_id; cannot determine target workflow",
        )

    try:
        # D38-3.2 (closes D38-3.1a P2 / D38-3.1b P2-4): stamp the
        # historical run id as ``parent_run_id`` on the new run so the
        # rerun chain is queryable per ADR §3.6.
        result = runtime.start_workflow(
            workflow_id,
            execute_from=body.execute_from_block_id,
            parent_run_id=run_id,
        )
    except FileNotFoundError as exc:
        # The historical workflow YAML may have been deleted since this run
        # was recorded. ADR-038 §3.6a's "reproduce from snapshot" is a future
        # enhancement -- at v1 we surface the missing-workflow case as 404.
        raise HTTPException(
            status_code=404,
            detail=f"workflow {workflow_id!r} no longer exists on disk: {exc}",
        ) from exc
    except ValueError as exc:
        # Most common cause: execute_from set but no checkpoint present
        # ("Run the full workflow at least once before using 'Run from here'").
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        # No active project, etc. Surface as 400 so the client gets a
        # human-readable message instead of a 500.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "rerun_of": run_id,
        "workflow_id": workflow_id,
        "execute_from_block_id": body.execute_from_block_id,
        "result": result,
    }
