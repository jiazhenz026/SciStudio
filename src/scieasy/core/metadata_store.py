"""Deprecated: legacy ``metadata.db`` import surface — superseded by ADR-038.

ADR-038 §3.1 collapses the pre-existing ``metadata.db`` (ADR-032) and the
disjoint ``lineage.db`` schema into a single unified ``lineage.db`` with
four normalized tables. Phase D38-2.3 (this module) retires the
``metadata.db`` write path and converts this module into a thin
deprecation shim:

* :class:`MetadataStore` is preserved as a public symbol with the same
  ``put`` / ``put_wire`` / ``get`` / ``get_wire`` / ``get_by_storage_path``
  / ``ancestors`` / ``descendants`` / ``list_by_type`` / ``list_by_workflow``
  / ``vacuum`` / ``delete`` / ``close`` method surface so out-of-scope
  callers (notably the MCP inspection / QA tools) keep working.
* Writes (``put`` / ``put_wire`` / ``put_wire_if_missing``) are best-effort
  no-ops that emit a one-time :class:`DeprecationWarning`. The new
  authoritative writer is the :class:`scieasy.core.lineage.LineageRecorder`
  wired by ``ApiRuntime.start_workflow`` (D38-2.2, #920).
* Reads delegate to the unified
  :class:`~scieasy.core.lineage.LineageStore`'s ``data_objects`` table
  when the active project has one, returning ``None`` / ``[]`` otherwise.

Per ADR-038 §6 Phase 2 + the user direction recorded 2026-05-15 (project
is pre-release), **no historical data migration** is performed. If a
project directory contains a stale ``metadata.db`` from a pre-ADR-038
run, :func:`ApiRuntime._init_metadata_store` logs an ``INFO`` line and
leaves the file alone — it is never opened.

Removal target: 6 months after merge of the parent ADR-038 cascade.
The deprecation warning fires at most once per process to keep CI output
clean while the cascade lands.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scieasy.core.lineage.store import LineageStore
    from scieasy.core.types.base import DataObject

logger = logging.getLogger(__name__)

# Emit the DeprecationWarning at most once per process to keep test output
# readable while the rest of the ADR-038 cascade rolls out. Once the
# follow-up phases stop importing this module entirely we can drop the
# guard and let the warning fire on every call.
_WARNED: bool = False

_DEPRECATION_MESSAGE = (
    "scieasy.core.metadata_store is deprecated and superseded by ADR-038's "
    "unified lineage store (scieasy.core.lineage.LineageStore). The "
    "MetadataStore shim is retained for the 6-month deprecation window; "
    "new code MUST use the unified store via scieasy.core.lineage."
)


def _emit_deprecation_warning() -> None:
    """Fire the deprecation warning at most once per process."""
    global _WARNED
    if _WARNED:
        return
    _WARNED = True
    warnings.warn(
        _DEPRECATION_MESSAGE,
        DeprecationWarning,
        stacklevel=3,
    )


# Module-level handle to the unified :class:`LineageStore` for the active
# project. Set by :func:`ApiRuntime._init_metadata_store` so the shim's
# delegated reads have a stable lookup point that does not require a
# FastAPI request context. Tests inject directly via
# :func:`_set_active_lineage_store`.
_active_store: LineageStore | None = None


def _set_active_lineage_store(store: LineageStore | None) -> None:
    """Register (or clear) the active project's unified store.

    Called by :class:`ApiRuntime` on project open / project switch. Tests
    that fault-inject an in-memory store call this directly.
    """
    global _active_store
    _active_store = store


def _active_lineage_store() -> LineageStore | None:
    """Look up the active project's unified :class:`LineageStore`.

    Returns ``None`` when no project is open or the runtime has not yet
    registered a store. Best-effort: never raises.
    """
    return _active_store


# ---------------------------------------------------------------------------
# Public deprecation shim
# ---------------------------------------------------------------------------


class MetadataStore:
    """Deprecation shim — preserves the pre-ADR-038 ``metadata.db`` surface.

    The shim is constructed by :meth:`ApiRuntime._init_metadata_store` for
    backwards compatibility with callers that import the legacy symbols.
    Writes are silent no-ops (the unified :class:`LineageStore` is the
    authoritative writer). Reads return ``None`` / ``[]`` because no
    legacy data migration is performed per ADR-038 §6 Phase 2.

    The ``db_path`` constructor argument is accepted for API compatibility
    but is no longer used — the shim never opens a SQLite connection of
    its own. The unified store lives at ``<project>/.scieasy/lineage.db``
    and is owned by :class:`ApiRuntime`.

    Parameters
    ----------
    db_path:
        Ignored (kept for backwards-compatible constructor signature).
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        # Path is intentionally not stored — the shim is stateless.
        # We capture it for ``__repr__`` only so debug output still names
        # the legacy file location the caller asked for.
        self._db_path = Path(db_path) if db_path is not None else None
        _emit_deprecation_warning()

    # ------------------------------------------------------------------
    # Write methods — no-ops with a one-time warning.
    # ------------------------------------------------------------------

    def put(
        self,
        obj: DataObject,
        workflow_id: str | None = None,
        block_id: str | None = None,
        port_name: str | None = None,
    ) -> None:
        """No-op shim — the LineageRecorder owns writes per ADR-038 §3.2."""
        _emit_deprecation_warning()

    def put_wire(
        self,
        wire_dict: dict[str, Any],
        workflow_id: str | None = None,
        block_id: str | None = None,
        port_name: str | None = None,
    ) -> None:
        """No-op shim — the LineageRecorder owns writes per ADR-038 §3.2."""
        _emit_deprecation_warning()

    def put_wire_if_missing(
        self,
        wire_dict: dict[str, Any],
        workflow_id: str | None = None,
        block_id: str | None = None,
        port_name: str | None = None,
    ) -> None:
        """No-op shim — the LineageRecorder owns writes per ADR-038 §3.2."""
        _emit_deprecation_warning()

    # ------------------------------------------------------------------
    # Read methods — delegate to the unified LineageStore where possible.
    # ------------------------------------------------------------------

    def get(self, object_id: str) -> DataObject | None:
        """Reconstruct a :class:`DataObject` via the unified store.

        Returns ``None`` when there is no active lineage store or the
        object id is unknown. Reconstruction uses the same
        :func:`_reconstruct_one` path as the worker subprocess, so a
        successful return is byte-equivalent to the pre-ADR-038 result.
        """
        _emit_deprecation_warning()
        wire = self.get_wire(object_id)
        if wire is None:
            return None
        try:
            from scieasy.core.types.serialization import _reconstruct_one

            return _reconstruct_one(wire)
        except Exception:
            logger.debug("MetadataStore shim: _reconstruct_one failed", exc_info=True)
            return None

    def get_wire(self, object_id: str) -> dict[str, Any] | None:
        """Return the raw wire payload stored for ``object_id``, or ``None``."""
        _emit_deprecation_warning()
        store = _active_lineage_store()
        if store is None:
            return None
        try:
            row = store.get_data_object(object_id)
        except Exception:
            logger.debug("MetadataStore shim: get_data_object failed", exc_info=True)
            return None
        if row is None:
            return None
        payload = row.get("wire_payload")
        if not isinstance(payload, str):
            return None
        import json

        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None

    def get_wire_by_storage_path(self, path: str) -> dict[str, Any] | None:
        """Return the wire payload for the first row matching ``storage_path``.

        New convenience accessor used by the MCP inspection tools — they
        previously branched on ``hasattr(store, "get_wire_by_storage_path")``,
        so the shim provides it explicitly for forward-compat clarity.
        Returns ``None`` when no row matches or the store is unavailable.
        """
        _emit_deprecation_warning()
        store = _active_lineage_store()
        if store is None:
            return None
        try:
            cur = store._conn.execute(  # type: ignore[attr-defined]
                "SELECT wire_payload FROM data_objects WHERE storage_path = ? LIMIT 1",
                (path,),
            )
            row = cur.fetchone()
        except Exception:
            logger.debug("MetadataStore shim: storage_path query failed", exc_info=True)
            return None
        if row is None:
            return None
        import json

        try:
            decoded = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return None
        return decoded if isinstance(decoded, dict) else None

    def get_by_storage_path(self, path: str) -> DataObject | None:
        """Look up a DataObject whose ``storage_path`` matches ``path``.

        Returns ``None`` when there is no match or reconstruction fails.
        """
        _emit_deprecation_warning()
        wire = self.get_wire_by_storage_path(path)
        if wire is None:
            return None
        try:
            from scieasy.core.types.serialization import _reconstruct_one

            return _reconstruct_one(wire)
        except Exception:
            logger.debug("MetadataStore shim: _reconstruct_one failed", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Lineage queries — delegate to the unified ``data_objects`` table.
    # ------------------------------------------------------------------

    def ancestors(self, object_id: str) -> list[dict[str, Any]]:
        """Return the provenance chain via the unified ``derived_from`` column.

        The shim runs the same recursive CTE as the pre-ADR-038
        implementation, against ``lineage.db.data_objects``. Empty list
        when the lineage store is unavailable or the object id is
        unknown. Each entry carries ``object_id``, ``derived_from``,
        ``type_name`` and a synthetic ``block_id`` field for
        backwards-compatible payload shape (the unified store does not
        carry per-row ``block_id``; we surface ``None`` and let callers
        cope).
        """
        _emit_deprecation_warning()
        store = _active_lineage_store()
        if store is None:
            return []
        try:
            rows = store._conn.execute(  # type: ignore[attr-defined]
                """
                WITH RECURSIVE anc AS (
                    SELECT object_id, derived_from, type_name
                    FROM data_objects WHERE object_id = ?
                    UNION ALL
                    SELECT d.object_id, d.derived_from, d.type_name
                    FROM data_objects d
                    JOIN anc a ON d.object_id = a.derived_from
                )
                SELECT object_id, derived_from, type_name FROM anc;
                """,
                (object_id,),
            ).fetchall()
        except Exception:
            logger.debug("MetadataStore shim: ancestors query failed", exc_info=True)
            return []
        return [{"object_id": r[0], "derived_from": r[1], "type_name": r[2], "block_id": None} for r in rows]

    def descendants(self, object_id: str) -> list[dict[str, Any]]:
        """Return objects derived from ``object_id`` via the unified store."""
        _emit_deprecation_warning()
        store = _active_lineage_store()
        if store is None:
            return []
        try:
            rows = store._conn.execute(  # type: ignore[attr-defined]
                """
                WITH RECURSIVE desc_cte AS (
                    SELECT object_id, derived_from, type_name
                    FROM data_objects WHERE object_id = ?
                    UNION ALL
                    SELECT d.object_id, d.derived_from, d.type_name
                    FROM data_objects d
                    JOIN desc_cte a ON d.derived_from = a.object_id
                )
                SELECT object_id, derived_from, type_name FROM desc_cte;
                """,
                (object_id,),
            ).fetchall()
        except Exception:
            logger.debug("MetadataStore shim: descendants query failed", exc_info=True)
            return []
        return [{"object_id": r[0], "derived_from": r[1], "type_name": r[2], "block_id": None} for r in rows]

    def list_by_type(self, type_name: str) -> list[dict[str, Any]]:
        """List unified-store rows whose ``type_name`` equals ``type_name``."""
        _emit_deprecation_warning()
        store = _active_lineage_store()
        if store is None:
            return []
        try:
            rows = store._conn.execute(  # type: ignore[attr-defined]
                "SELECT object_id, type_name, storage_path FROM data_objects WHERE type_name = ?",
                (type_name,),
            ).fetchall()
        except Exception:
            logger.debug("MetadataStore shim: list_by_type failed", exc_info=True)
            return []
        return [
            {
                "object_id": r[0],
                "type_name": r[1],
                "storage_path": r[2],
                # ``workflow_id`` / ``block_id`` are not first-class
                # columns on the unified ``data_objects`` table; callers
                # that care should query the ``block_io`` join (Q4b in
                # ADR §3.7). The shim returns ``None`` placeholders for
                # signature compatibility.
                "workflow_id": None,
                "block_id": None,
            }
            for r in rows
        ]

    def list_by_workflow(self, workflow_id: str) -> list[dict[str, Any]]:
        """List unified-store rows produced by ``workflow_id``.

        Joins ``data_objects`` ↔ ``block_io`` ↔ ``block_executions`` ↔
        ``runs`` to find every output object produced by any run of the
        given workflow. Empty list when the lineage store is unavailable
        or the workflow has never executed.
        """
        _emit_deprecation_warning()
        store = _active_lineage_store()
        if store is None:
            return []
        try:
            rows = store._conn.execute(  # type: ignore[attr-defined]
                """
                SELECT DISTINCT do.object_id, do.type_name, do.storage_path,
                                bio.port_name, be.block_id
                FROM data_objects do
                JOIN block_io bio ON bio.object_id = do.object_id
                JOIN block_executions be ON be.block_execution_id = bio.block_execution_id
                JOIN runs r ON r.run_id = be.run_id
                WHERE r.workflow_id = ? AND bio.direction = 'output'
                """,
                (workflow_id,),
            ).fetchall()
        except Exception:
            logger.debug("MetadataStore shim: list_by_workflow failed", exc_info=True)
            return []
        return [
            {
                "object_id": r[0],
                "type_name": r[1],
                "storage_path": r[2],
                "block_id": r[4],
                "port_name": r[3],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Maintenance — no-ops.
    # ------------------------------------------------------------------

    def delete(self, object_id: str) -> None:
        """No-op — the unified store owns row lifecycle per ADR-038."""
        _emit_deprecation_warning()

    def vacuum(self, existing_paths: set[str]) -> int:
        """No-op — returns 0 (rows are retained per ADR-038 §3.5)."""
        _emit_deprecation_warning()
        return 0

    def close(self) -> None:
        """No-op — the shim does not own a SQLite handle."""

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"MetadataStore(deprecated_shim, db_path={self._db_path!r})"


# ---------------------------------------------------------------------------
# Module-level singleton — preserved for backwards compatibility.
# ---------------------------------------------------------------------------

_store: MetadataStore | None = None


def get_metadata_store() -> MetadataStore | None:
    """Return the active deprecated :class:`MetadataStore`, or ``None``.

    The instance is the shim from this module — all writes are no-ops and
    all reads delegate to :class:`~scieasy.core.lineage.LineageStore`. Use
    the unified store directly for new code.
    """
    return _store


def set_metadata_store(store: MetadataStore | None) -> None:
    """Set or clear the active deprecation-shim singleton."""
    global _store
    _store = store
