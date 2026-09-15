"""Shared constants and reference helpers for ``tools_inspection``.

The constants define the canonical MCP inspection budgets for preview payloads,
text reads, thumbnails, and log tails.
"""

from __future__ import annotations

from typing import Any

from scistudio.core.storage.ref import StorageReference

_LOCK_TIMEOUT_SECONDS: float = 10.0
"""File lock timeout."""
# Development references: ADR-033.

_MAX_PREVIEW_BYTES: int = 8 * 1024 * 1024
"""Maximum preview payload size: 8 MiB."""

_THUMBNAIL_MAX_DIM: int = 256
_DATAFRAME_PREVIEW_ROWS: int = 100
_SERIES_PREVIEW_POINTS: int = 200
_TEXT_PREVIEW_CHARS: int = 4096
_BLOCK_LOG_TRUNCATE_BYTES: int = 16 * 1024  # 16 KiB per stream


def _ref_from_dict(ref: dict[str, Any]) -> StorageReference:
    """Build a :class:`StorageReference` from a JSON-safe dict envelope."""
    return StorageReference(
        backend=str(ref.get("backend", "filesystem")),
        path=str(ref.get("path", "")),
        format=ref.get("format"),
        metadata=ref.get("metadata"),
    )


_LINEAGE_MAX_OBJECTS: int = 10_000
"""Upper bound on the objects one ``get_lineage`` walk visits."""


def _walk_lineage(lineage: Any, object_id: str) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Return ``(nodes, edges)`` for the transitive ancestors of *object_id*.

    An object's parents are the object it was ``derived_from`` and every input
    of the block execution that produced it (``block_io`` rows with
    ``direction='input'``), so the walk crosses block boundaries the way the
    run record does. Each node carries ``object_id``, ``type_name`` and the
    producing ``block_id`` (``None`` when no execution produced it); each edge is
    ``(parent_object_id, child_object_id)``. *lineage* is the project's
    :class:`~scistudio.core.lineage.store.LineageStore`.
    """
    # Development references: ADR-038, #2402.
    nodes: list[dict[str, Any]] = []
    edges: list[tuple[str, str]] = []
    seen: set[str] = set()
    queue = [object_id]
    while queue and len(seen) < _LINEAGE_MAX_OBJECTS:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        row = lineage.get_data_object(current)
        if row is None:
            continue
        execution_id = row.get("produced_by_execution")
        block_id: str | None = None
        parents: list[str] = []
        if row.get("derived_from"):
            parents.append(str(row["derived_from"]))
        if execution_id:
            found = lineage.execute_query(
                "SELECT block_id FROM block_executions WHERE block_execution_id = ?", (execution_id,)
            )
            block_id = str(found[0][0]) if found else None
            for edge in lineage.list_block_io(execution_id):
                if edge.get("direction") == "input" and edge.get("object_id"):
                    parents.append(str(edge["object_id"]))
        nodes.append({"object_id": current, "type_name": row.get("type_name") or "", "block_id": block_id})
        for parent in dict.fromkeys(parents):
            if parent == current:
                continue
            edges.append((parent, current))
            queue.append(parent)
    return nodes, edges


__all__ = [
    "_BLOCK_LOG_TRUNCATE_BYTES",
    "_DATAFRAME_PREVIEW_ROWS",
    "_LOCK_TIMEOUT_SECONDS",
    "_MAX_PREVIEW_BYTES",
    "_SERIES_PREVIEW_POINTS",
    "_TEXT_PREVIEW_CHARS",
    "_THUMBNAIL_MAX_DIM",
    "_ref_from_dict",
    "_walk_lineage",
]
