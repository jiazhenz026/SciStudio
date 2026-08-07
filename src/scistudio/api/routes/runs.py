"""REST endpoints for ADR-038 run history (`/api/runs`).

Endpoints (ADR-038 §3.7, §3.8; Addendum 1 §11.4):

* ``GET  /api/runs``                       -- list runs (reverse-chrono), optional ``workflow_id`` filter + pagination
* ``GET  /api/runs/validate-restore``      -- advisory preflight for a restore target (§3.6 checks)
* ``GET  /api/runs/{run_id}``              -- full run detail with joined block_executions
* ``GET  /api/runs/{run_id}/methods``      -- markdown methods export (``Content-Type: text/markdown``)

The lineage store is project-scoped -- every endpoint requires an active
project. Failures resolve to ``400 Bad Request`` (no active project) or
``404 Not Found`` (unknown run / unknown workflow).

The implementation is intentionally thin: it delegates row access to
:class:`LineageStore` (ADR-038 §3.1, §5.1), methods rendering to
:mod:`scistudio.core.lineage.methods_export`, and the restore preflight to
:mod:`scistudio.core.lineage.restore_preflight`. Every route here is read-only
against the lineage store -- ADR-038 Addendum 1 (#2033) removed
``POST /{run_id}/rerun``, which was the only mutating one.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from scistudio.api.deps import get_lineage_store
from scistudio.core.lineage.methods_export import render_methods_markdown
from scistudio.core.lineage.restore_preflight import evaluate_restore_target

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])

# Module-level Depends() singletons -- FastAPI / ruff B008 best practice.
_LineageStoreDep = Depends(get_lineage_store)


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
# GET /api/runs/validate-restore -- advisory preflight for a restore target
# Must be declared BEFORE /{run_id} so the literal segment matches first.
# ---------------------------------------------------------------------------


@router.get("/validate-restore")
def validate_restore(
    commit_sha: str = Query(description="Full SHA of the commit the user is about to restore to."),
    store: Any = _LineageStoreDep,
) -> dict[str, Any]:
    """Return the advisory checks for restoring to ``commit_sha``.

    ADR-038 §3.6 + Addendum 1 §11.3 (#2033). Resolves the commit to the newest
    run recorded at it, then compares that run's boundary inputs against what
    is on disk now and its ``environment_snapshot`` against the live
    environment. Both checks are advisory: this endpoint never blocks a
    restore, and a caller is free to ignore the response entirely.

    Keyed on the commit rather than a run id because that is what Restore
    operates on -- the Git tab restores an arbitrary commit, and the Run
    history tab restores the commit a run recorded.

    A commit with no associated run returns ``run_id: null`` with both warning
    lists empty. That is **not** a clean bill of health, and clients must not
    render it as one: it means no recorded run describes this commit, so
    nothing could be compared. Conflating the two is the defect Addendum 1
    exists to remove -- the previous UI showed "No drift detected" for a
    comparison that never ran.
    """
    return evaluate_restore_target(store, commit_sha)


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
# ADR-038 Addendum 1 (#2033): ``POST /api/runs/{run_id}/rerun`` is removed.
#
# Re-run is withdrawn as a user-facing operation -- Restore puts the recorded
# state back and the user presses Run, which is the control they already use.
# The §3.6 input + environment checks the rerun dialog was supposed to perform
# (but never did) now live on the restore preflight above.
#
# ``runs.parent_run_id`` and its read paths stay: "Run from here" (§3.6a) is a
# separate feature that still populates ``execute_from_block_id``, and
# historical rows keep rendering their parent link.
# ---------------------------------------------------------------------------
