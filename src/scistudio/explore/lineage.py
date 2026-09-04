"""Explore-session lineage — the session's side of the provenance store.

An Explore session records what it did the way a workflow run does, because it
writes into the same tables. ADR-054 §4.1 puts it plainly: ``explore_sessions``
parallels ``runs`` so that everything downstream — block executions, data
objects, io edges — is the same code with a different foreign key. This module
is that code's session-facing face: it opens and closes the anchor, writes a
record for every cell run and every block a cell called, marks the objects a
notebook declared as outputs, and answers the question the shared tables exist
to make answerable — *where did this object come from, and who used it* — across
the boundary, in both directions.

The three things it writes
--------------------------

**A session** (FR-052) is one ``explore_sessions`` row: the session id, the
notebook's path, its captured content, the commit of FR-028, a reference to the
environment snapshot (FR-034), a start time, and a status.

**A cell run** (FR-053) is one ``block_executions`` row anchored to the session,
with the cell id as its ``block_id``, the notebook commit as its
``block_version``, and the environment reference beside it. It is a block
execution because that is what the shared tables call the unit below an anchor,
and using it is what makes a cell's objects reachable by the same joins a run's
objects are.

**A block called from a cell** (FR-051) is another such row, with the block's
own type and version, and its inputs and outputs recorded as ``block_io`` edges
over ``data_objects`` exactly as they are for a workflow run.

Crossing the boundary
---------------------

Because the object catalog is shared, an object a session produced and a run
consumed is one row with an edge on each side. :meth:`ExploreLineage.origin_of`
walks from the object to the session that produced it and
:meth:`ExploreLineage.uses_of` to the runs that consumed it; both return the
same :class:`ObjectOrigin` / :class:`ObjectUse` shape whichever anchor is on the
other end, so a caller does not branch on which kind of thing it found.

The other crossing is FR-054's: a packaged block's run is an ordinary workflow
run whose block version is a notebook commit, so
:meth:`ExploreLineage.session_behind_step` reads a run's step and hands back the
session the step came from.

Durability
----------

FR-055 makes the objects a notebook named through ``scistudio.output`` durable
and every other object a session produced a reclaim candidate.
:meth:`ExploreLineage.declare_output` is the hook that records the name; the
existing retention planner reads it (see
:func:`scistudio.core.lineage.retention.plan_retention`) and needs nothing else
from this module.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from scistudio.core.lineage.record import (
    BlockExecutionRecord,
    BlockIORow,
    DataObjectRow,
    ExploreSessionRecord,
)
from scistudio.core.lineage.store import DECLARED_OUTPUT_DIRECTION, LineageStore
from scistudio.stability import provisional

#: ``block_executions.block_type`` for a cell run (FR-053). A cell is not a
#: block, but the row it writes is a block execution, and the type column is
#: what tells the two kinds of session row apart on read.
CELL_BLOCK_TYPE = "explore_cell"

#: ``explore_sessions.status`` while the session is open. Retention keys on this
#: value, so it is shared rather than spelled out at each call site.
SESSION_STATUS_RUNNING = "running"

#: ``explore_sessions.status`` after a clean close.
SESSION_STATUS_CLOSED = "closed"


@provisional(since="0.3.4")
@dataclass(frozen=True)
class ObjectOrigin:
    """Where a data object came from — one anchor, whichever kind it is."""

    kind: str
    """``"session"`` or ``"run"``."""
    anchor_id: str
    """The session id or the run id."""
    block_execution_id: str
    """The execution that produced the object."""
    block_id: str
    """The cell id (for a session) or the block id (for a run)."""
    block_type: str
    """The executed block's type; :data:`CELL_BLOCK_TYPE` for a cell run."""
    block_version: str
    """The block version; the notebook commit for a session's rows (FR-053)."""


@provisional(since="0.3.4")
@dataclass(frozen=True)
class ObjectUse:
    """One consumption of a data object, on either side of the boundary."""

    kind: str
    """``"session"`` or ``"run"``."""
    anchor_id: str
    """The session id or the run id."""
    block_execution_id: str
    """The execution that consumed the object."""
    block_id: str
    """The cell id (for a session) or the block id (for a run)."""
    port_name: str
    """The port the object entered through."""


def _now() -> str:
    """Return an ISO-8601 UTC timestamp, matching the recorder's format."""
    return datetime.now(UTC).isoformat()


def _anchor_of(row: Mapping[str, Any]) -> tuple[str, str]:
    """Return ``(kind, anchor_id)`` for a ``block_executions`` row.

    The database guarantees exactly one anchor is set, so this never has to
    choose between two.
    """
    session_id = row.get("session_id")
    if session_id:
        return "session", str(session_id)
    return "run", str(row.get("run_id") or "")


@provisional(since="0.3.4")
class ExploreLineage:
    """Writes and reads an Explore session's lineage.

    A thin, explicit face over :class:`~scistudio.core.lineage.store.LineageStore`:
    it owns no state beyond the store and no caching, so a caller may hold one
    per session or one per process.

    Unlike :class:`~scistudio.core.lineage.recorder.LineageRecorder`, this class
    does **not** swallow store failures. It is called from the session service's
    own queue rather than from an engine event handler, so the service decides
    what a failed write means for the cell that provoked it — which is also how
    it knows to latch ``provenance_degraded`` when it closes the session.

    Args:
        store: The project's lineage store.
    """

    def __init__(self, store: LineageStore) -> None:
        self._store = store

    @property
    @provisional(since="0.3.4")
    def store(self) -> LineageStore:
        """The underlying lineage store."""
        return self._store

    # ------------------------------------------------------------------
    # The session anchor (FR-052)
    # ------------------------------------------------------------------

    @provisional(since="0.3.4")
    def open_session(
        self,
        *,
        session_id: str,
        notebook_path: str,
        notebook_snapshot: str,
        environment_ref: str | None = None,
        notebook_git_commit: str | None = None,
        opened_over: str = "file",
        bound_run_id: str | None = None,
        started_at: str | None = None,
    ) -> ExploreSessionRecord:
        """Record an opened session and return the row that was written.

        Args:
            session_id: The session's id; the anchor every record below it uses.
            notebook_path: Project-relative path of the notebook.
            notebook_snapshot: The notebook's content as opened.
            environment_ref: Reference to the stored environment snapshot (FR-034).
            notebook_git_commit: The session ref's commit, when one exists yet.
            opened_over: ``"file"``, ``"block_outputs"``, or ``"paused_run"``.
            bound_run_id: The run this session is bound to, when opened over one.
            started_at: ISO-8601 open time; defaults to now.

        Returns:
            The :class:`ExploreSessionRecord` that was inserted.
        """
        record = ExploreSessionRecord(
            session_id=session_id,
            notebook_path=notebook_path,
            notebook_snapshot=notebook_snapshot,
            started_at=started_at or _now(),
            status=SESSION_STATUS_RUNNING,
            environment_ref=environment_ref,
            notebook_git_commit=notebook_git_commit,
            opened_over=opened_over,
            bound_run_id=bound_run_id,
        )
        self._store.insert_explore_session(record)
        return record

    @provisional(since="0.3.4")
    def close_session(
        self,
        session_id: str,
        *,
        status: str = SESSION_STATUS_CLOSED,
        finished_at: str | None = None,
        provenance_degraded: bool = False,
    ) -> None:
        """Close a session's anchor row.

        Until this is called the session counts as in progress and retention
        refuses to sweep, so a service that loses a kernel should still close
        the row — with a status saying so.

        Args:
            session_id: The session to close.
            status: Terminal status; ``"closed"`` by default.
            finished_at: ISO-8601 close time; defaults to now.
            provenance_degraded: Whether any lineage write for this session failed.
        """
        self._store.finalize_explore_session(
            session_id,
            finished_at=finished_at or _now(),
            status=status,
            provenance_degraded=provenance_degraded,
        )

    @provisional(since="0.3.4")
    def set_notebook_commit(self, session_id: str, sha: str | None) -> None:
        """Record the session's current notebook commit (FR-028, FR-035).

        Args:
            session_id: The session to stamp.
            sha: The commit the last cell run produced, or ``None`` to clear it.
        """
        self._store.set_session_notebook_commit(session_id, sha)

    # ------------------------------------------------------------------
    # Cell runs (FR-053) and block calls (FR-051)
    # ------------------------------------------------------------------

    @provisional(since="0.3.4")
    def record_cell_run(
        self,
        *,
        session_id: str,
        cell_id: str,
        notebook_commit: str,
        environment_ref: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        duration_ms: int = 0,
        termination: str = "completed",
        termination_detail: str = "",
        block_execution_id: str | None = None,
    ) -> str:
        """Write the record for one cell run and return its execution id.

        FR-053: the record carries the session (the anchor), the notebook commit
        (as ``block_version``), the cell id (as ``block_id``), and the
        environment reference. Nothing de-duplicates it — running the same cell
        again is a second record, which is the whole point of a session.

        Args:
            session_id: The session the cell ran in.
            cell_id: The cell's stable id.
            notebook_commit: The commit FR-028 wrote for this run.
            environment_ref: Reference to the stored environment snapshot (FR-034).
            started_at: ISO-8601 start; defaults to now.
            finished_at: ISO-8601 finish, when known.
            duration_ms: Wall-clock duration in milliseconds.
            termination: ``"completed"``, ``"error"``, or ``"cancelled"``.
            termination_detail: Extra detail, e.g. an error message.
            block_execution_id: Supply to control the id; a uuid4 by default.

        Returns:
            The ``block_execution_id`` of the record written.
        """
        return self._insert_execution(
            BlockExecutionRecord(
                block_execution_id=block_execution_id or str(uuid.uuid4()),
                run_id=None,
                block_id=cell_id,
                block_type=CELL_BLOCK_TYPE,
                block_version=notebook_commit,
                block_config_resolved={},
                started_at=started_at or _now(),
                termination=termination,
                finished_at=finished_at,
                duration_ms=duration_ms,
                termination_detail=termination_detail,
                session_id=session_id,
                environment_ref=environment_ref,
            )
        )

    @provisional(since="0.3.4")
    def record_block_call(
        self,
        *,
        session_id: str,
        block_id: str,
        block_type: str,
        block_version: str,
        config: Mapping[str, Any] | None = None,
        inputs: Mapping[str, DataObjectRow | Sequence[DataObjectRow]] | None = None,
        outputs: Mapping[str, DataObjectRow | Sequence[DataObjectRow]] | None = None,
        environment_ref: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        duration_ms: int = 0,
        termination: str = "completed",
        termination_detail: str = "",
        block_execution_id: str | None = None,
    ) -> str:
        """Write the record for a block a cell called, with its io edges.

        FR-051: the execution's foreign key points at the session, and its
        inputs and outputs become ``block_io`` edges over ``data_objects`` as
        they do for a workflow run. Output rows have their
        ``produced_by_execution`` filled in here, so the caller does not have to
        know the execution id before building them.

        A port's value may be a single row or a sequence of them; a sequence
        becomes one edge per item with an incrementing ``position``, which is
        how a Collection port is recorded.

        Args:
            session_id: The session the call was made in.
            block_id: Identifier for the call — the cell id, or a per-call id
                when one cell calls several blocks.
            block_type: The called block's type name.
            block_version: The called block's version.
            config: The resolved configuration the call used.
            inputs: Port name → the object(s) that entered.
            outputs: Port name → the object(s) that came back.
            environment_ref: Reference to the stored environment snapshot (FR-034).
            started_at: ISO-8601 start; defaults to now.
            finished_at: ISO-8601 finish, when known.
            duration_ms: Wall-clock duration in milliseconds.
            termination: ``"completed"``, ``"error"``, or ``"cancelled"``.
            termination_detail: Extra detail, e.g. an error message.
            block_execution_id: Supply to control the id; a uuid4 by default.

        Returns:
            The ``block_execution_id`` of the record written.
        """
        execution_id = self._insert_execution(
            BlockExecutionRecord(
                block_execution_id=block_execution_id or str(uuid.uuid4()),
                run_id=None,
                block_id=block_id,
                block_type=block_type,
                block_version=block_version,
                block_config_resolved=dict(config or {}),
                started_at=started_at or _now(),
                termination=termination,
                finished_at=finished_at,
                duration_ms=duration_ms,
                termination_detail=termination_detail,
                session_id=session_id,
                environment_ref=environment_ref,
            )
        )
        # Inputs first: an input already exists in the catalog (or is external),
        # while an output has to learn the execution that made it.
        for port_name, value in (inputs or {}).items():
            for position, row in enumerate(_as_rows(value)):
                self._store.upsert_data_object(row)
                self._store.insert_block_io(
                    BlockIORow(
                        block_execution_id=execution_id,
                        direction="input",
                        port_name=port_name,
                        object_id=row.object_id,
                        position=position,
                    )
                )
        for port_name, value in (outputs or {}).items():
            for position, row in enumerate(_as_rows(value)):
                self._store.upsert_data_object(row if row.produced_by_execution else _produced_by(row, execution_id))
                self._store.insert_block_io(
                    BlockIORow(
                        block_execution_id=execution_id,
                        direction="output",
                        port_name=port_name,
                        object_id=row.object_id,
                        position=position,
                    )
                )
        return execution_id

    def _insert_execution(self, record: BlockExecutionRecord) -> str:
        """Insert *record* and return its id."""
        self._store.insert_block_execution(record)
        return record.block_execution_id

    # ------------------------------------------------------------------
    # Durability (FR-055)
    # ------------------------------------------------------------------

    @provisional(since="0.3.4")
    def declare_output(
        self,
        *,
        block_execution_id: str,
        name: str,
        row: DataObjectRow,
        position: int = 0,
    ) -> None:
        """Mark an object the notebook named through ``scistudio.output``.

        FR-055: a declared object is durable, and every other object the session
        produced is a reclaim candidate for the existing retention planner. The
        declaration is a ``block_io`` edge in its own direction rather than a
        flag on an output edge, because a declaration is not a port — see
        :data:`~scistudio.core.lineage.store.DECLARED_OUTPUT_DIRECTION`.

        Declaring the same name twice is a no-op; the edge is keyed on
        ``(execution, direction, name, position)``.

        Args:
            block_execution_id: The cell run or block call that produced it.
            name: The name the notebook declared.
            row: The object being declared. Upserted first, so declaring an
                object the session did not otherwise record still works.
            position: Index within a declared collection; ``0`` for a single value.
        """
        self._store.upsert_data_object(row)
        self._store.insert_block_io(
            BlockIORow(
                block_execution_id=block_execution_id,
                direction=DECLARED_OUTPUT_DIRECTION,
                port_name=name,
                object_id=row.object_id,
                position=position,
            )
        )

    @provisional(since="0.3.4")
    def durable_paths(self, session_ids: Iterable[str] | None = None) -> set[str]:
        """Return the storage paths retention must keep for these sessions.

        Args:
            session_ids: Restrict to these sessions; ``None`` covers all.

        Returns:
            The declared outputs' storage paths.
        """
        return self._store.session_declared_output_paths(session_ids)

    @provisional(since="0.3.4")
    def reclaimable_paths(self, session_ids: Iterable[str] | None = None) -> set[str]:
        """Return the storage paths retention may reclaim for these sessions.

        Everything the sessions produced except what they declared. This is the
        read the planner performs; it is exposed so a caller can show a person
        what closing a session will cost before it happens.

        Args:
            session_ids: Restrict to these sessions; ``None`` covers all.

        Returns:
            The produced-but-undeclared storage paths.
        """
        return self._store.artifact_paths_produced_by_sessions(session_ids) - self.durable_paths(session_ids)

    # ------------------------------------------------------------------
    # Reading across the boundary
    # ------------------------------------------------------------------

    @provisional(since="0.3.4")
    def origin_of(self, object_id: str) -> ObjectOrigin | None:
        """Return where an object was produced, session or run alike.

        Args:
            object_id: Id of the data object.

        Returns:
            The :class:`ObjectOrigin`, or ``None`` when the object is unknown or
            its producer was never recorded (an external input, for instance).
        """
        row = self._store.execution_producing_object(object_id)
        if row is None:
            return None
        kind, anchor_id = _anchor_of(row)
        return ObjectOrigin(
            kind=kind,
            anchor_id=anchor_id,
            block_execution_id=str(row["block_execution_id"]),
            block_id=str(row["block_id"]),
            block_type=str(row["block_type"]),
            block_version=str(row["block_version"]),
        )

    @provisional(since="0.3.4")
    def uses_of(self, object_id: str) -> list[ObjectUse]:
        """Return every consumption of an object, session or run alike.

        The other direction of :meth:`origin_of`. An object a session produced
        and a workflow run then consumed shows the run here, which is what
        "resolves across the boundary" means from the session's side.

        Args:
            object_id: Id of the data object.

        Returns:
            The consumptions in start-time order; empty when nothing read it.
        """
        uses: list[ObjectUse] = []
        for row in self._store.executions_consuming_object(object_id):
            kind, anchor_id = _anchor_of(row)
            uses.append(
                ObjectUse(
                    kind=kind,
                    anchor_id=anchor_id,
                    block_execution_id=str(row["block_execution_id"]),
                    block_id=str(row["block_id"]),
                    port_name=str(row["port_name"]),
                )
            )
        return uses

    @provisional(since="0.3.4")
    def session_of(self, object_id: str) -> dict[str, Any] | None:
        """Return the session row that produced an object, or ``None``.

        ``None`` covers both "produced by a run" and "producer not recorded";
        use :meth:`origin_of` when the difference matters.

        Args:
            object_id: Id of the data object.

        Returns:
            The ``explore_sessions`` row, or ``None``.
        """
        origin = self.origin_of(object_id)
        if origin is None or origin.kind != "session":
            return None
        return self._store.get_explore_session(origin.anchor_id)

    @provisional(since="0.3.4")
    def session_behind_step(self, run_id: str, block_id: str) -> dict[str, Any] | None:
        """Return the session a packaged block's step came from, or ``None``.

        FR-054: a packaged block's run is an ordinary workflow run whose block
        version is the notebook commit, which is exactly what makes the session
        reachable from the run. This reads that step's ``block_version`` and
        resolves it back to the session that produced the commit.

        Args:
            run_id: The workflow run.
            block_id: The step within it.

        Returns:
            The ``explore_sessions`` row, or ``None`` when the step is not a
            packaged notebook block or its commit belongs to no known session.
        """
        for row in self._store.list_block_executions(run_id):
            if row.get("block_id") == block_id:
                return self._store.explore_session_for_notebook_commit(str(row.get("block_version") or ""))
        return None


def _as_rows(value: DataObjectRow | Sequence[DataObjectRow]) -> list[DataObjectRow]:
    """Return *value* as a list of rows; a single row becomes a one-item list."""
    if isinstance(value, DataObjectRow):
        return [value]
    return list(value)


def _produced_by(row: DataObjectRow, execution_id: str) -> DataObjectRow:
    """Return a copy of *row* stamped with the execution that produced it."""
    return DataObjectRow(
        object_id=row.object_id,
        type_name=row.type_name,
        wire_payload=row.wire_payload,
        created_at=row.created_at,
        backend=row.backend,
        storage_path=row.storage_path,
        size_bytes=row.size_bytes,
        mtime_at_write=row.mtime_at_write,
        derived_from=row.derived_from,
        produced_by_execution=execution_id,
        content_hash=row.content_hash,
    )
