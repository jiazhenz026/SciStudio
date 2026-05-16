"""LineageRecorder — engine-owned writer of unified lineage records (ADR-038 §3.2).

The recorder subscribes to the four terminal block events
(BLOCK_DONE / BLOCK_ERROR / BLOCK_CANCELLED / BLOCK_SKIPPED) and writes one
``block_executions`` row per event, plus zero or more ``data_objects`` /
``block_io`` rows derived from the wire-format outputs that the scheduler
attaches to the event data.

Per ADR-038 §3.2:

* All writes happen in the engine process; the worker subprocess does not
  connect to the lineage DB.
* Block authors see no contract change — the lineage system observes
  externally.
* On any DB error the recorder logs a warning and swallows the exception so
  a lineage outage cannot break a workflow.

Phase D38-2.2 wires construction of this class inside
``ApiRuntime.start_workflow``; the engine-side stub at
``src/scieasy/engine/lineage_recorder.py`` is removed.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from scieasy.core.lineage.record import (
    BlockExecutionRecord,
    BlockIORow,
    DataObjectRow,
    RunRecord,
)

# Engine-event names are duplicated as string constants here so that
# ``core/`` does not import from ``engine/`` (test_layer_deps invariant).
# These four strings MUST match the values exported by
# ``scieasy.engine.events`` — they are the BLOCK_* event_type identifiers
# the scheduler emits.
_BLOCK_DONE = "block_done"
_BLOCK_ERROR = "block_error"
_BLOCK_CANCELLED = "block_cancelled"
_BLOCK_SKIPPED = "block_skipped"

if TYPE_CHECKING:
    from scieasy.core.lineage.store import LineageStore
    from scieasy.engine.events import EngineEvent, EventBus

logger = logging.getLogger(__name__)


_TERMINATION_BY_EVENT = {
    _BLOCK_DONE: "completed",
    _BLOCK_ERROR: "error",
    _BLOCK_CANCELLED: "cancelled",
    _BLOCK_SKIPPED: "skipped",
}


class LineageRecorder:
    """Subscribes to terminal block events and writes 4-table lineage rows.

    Parameters
    ----------
    event_bus:
        The workflow ``EventBus`` to subscribe on.
    lineage_store:
        The unified :class:`~scieasy.core.lineage.store.LineageStore` to
        persist rows into. If ``None``, recording is disabled (used in tests
        that bypass the lineage layer).
    run_id:
        The ``runs.run_id`` this recorder is attached to. Block executions
        within this scheduler will all carry the same ``run_id``.
    """

    def __init__(
        self,
        event_bus: EventBus,
        lineage_store: LineageStore | None,
        run_id: str,
    ) -> None:
        self._event_bus = event_bus
        self._store = lineage_store
        self._run_id = run_id
        self._start_times: dict[str, datetime] = {}
        # Map block_id → block_execution_id so we can correlate
        # data_objects / block_io rows for the same execution.
        self._exec_ids: dict[str, str] = {}
        # D38-3.2 (closes Codex P1 on PR #926): track whether we are
        # subscribed so ``dispose()`` is idempotent.
        self._subscribed = False

        event_bus.subscribe(_BLOCK_DONE, self._on_terminal)
        event_bus.subscribe(_BLOCK_ERROR, self._on_terminal)
        event_bus.subscribe(_BLOCK_CANCELLED, self._on_terminal)
        event_bus.subscribe(_BLOCK_SKIPPED, self._on_terminal)
        self._subscribed = True

    @property
    def run_id(self) -> str:
        return self._run_id

    # ------------------------------------------------------------------
    # Lifecycle hooks called from the scheduler / ApiRuntime
    # ------------------------------------------------------------------

    def record_start(self, block_id: str) -> None:
        """Capture the start time for ``block_id`` so we can compute duration."""
        self._start_times[block_id] = datetime.now()

    def begin_run(self, run: RunRecord) -> None:
        """Insert the ``runs`` row at workflow start."""
        if self._store is None:
            return
        try:
            self._store.insert_run(run)
        except Exception:
            logger.warning("LineageRecorder: insert_run failed (non-fatal)", exc_info=True)

    def finalize_run(self, *, status: str) -> None:
        """Update the run's ``finished_at`` and ``status`` on completion."""
        if self._store is None:
            return
        try:
            self._store.finalize_run(
                self._run_id,
                finished_at=datetime.now().isoformat(),
                status=status,
            )
        except Exception:
            logger.warning("LineageRecorder: finalize_run failed (non-fatal)", exc_info=True)

    def dispose(self) -> None:
        """Detach this recorder from its ``EventBus`` (D38-3.2).

        Closes Codex P1 on PR #926: ``ApiRuntime._build_lineage_recorder``
        constructs a new recorder for every ``start_workflow`` call but
        the recorders were never unsubscribed. Each successive workflow
        run added a fresh subscriber, so a single emit fanned out to
        every prior run's recorder, writing duplicate (or wrong-run)
        rows into ``block_executions`` / ``data_objects`` / ``block_io``.

        Call this from :meth:`ApiRuntime._finalize_lineage_run` once the
        run task is done (whether the run completed, errored, or was
        cancelled) so the EventBus no longer holds a strong reference
        to the recorder and its store handle.

        Idempotent — repeated calls are no-ops.
        """
        if not self._subscribed:
            return
        for event_type in (_BLOCK_DONE, _BLOCK_ERROR, _BLOCK_CANCELLED, _BLOCK_SKIPPED):
            with contextlib.suppress(Exception):
                self._event_bus.unsubscribe(event_type, self._on_terminal)
        self._subscribed = False

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    async def _on_terminal(self, event: EngineEvent) -> None:
        """Persist a ``block_executions`` row and derive data_objects/block_io rows."""
        if self._store is None or event.block_id is None:
            return

        block_id = event.block_id
        data: dict[str, Any] = event.data or {}

        # Don't double-write if some other path already recorded this block.
        if block_id in self._exec_ids:
            return

        termination = _TERMINATION_BY_EVENT.get(event.event_type, "completed")
        start = self._start_times.pop(block_id, None)
        now = datetime.now()
        started_at = start.isoformat() if start is not None else now.isoformat()
        duration_ms = int((now - start).total_seconds() * 1000) if start is not None else 0

        block_execution_id = uuid4().hex
        self._exec_ids[block_id] = block_execution_id

        be = BlockExecutionRecord(
            block_execution_id=block_execution_id,
            run_id=self._run_id,
            block_id=block_id,
            block_type=str(data.get("block_type", "")),
            block_version=str(data.get("block_version", "")),
            block_config_resolved=_safe_dict(data.get("config")),
            started_at=started_at,
            finished_at=now.isoformat(),
            duration_ms=duration_ms,
            termination=termination,
            termination_detail=str(data.get("error", "")),
        )
        try:
            self._store.insert_block_execution(be)
        except Exception:
            logger.warning(
                "LineageRecorder: insert_block_execution failed for block %s (non-fatal)",
                block_id,
                exc_info=True,
            )
            return

        # Output port → data_objects + block_io. Inputs are tracked the same
        # way using the scheduler-provided ``input_object_ids`` map.
        try:
            self._record_io(
                block_execution_id,
                direction="input",
                payload=data.get("input_object_ids"),
                port_values=data.get("inputs"),
            )
            self._record_io(
                block_execution_id,
                direction="output",
                payload=data.get("output_object_ids"),
                port_values=data.get("outputs"),
            )
        except Exception:
            logger.warning(
                "LineageRecorder: I/O recording failed for block %s (non-fatal)",
                block_id,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_io(
        self,
        block_execution_id: str,
        *,
        direction: str,
        payload: Any,
        port_values: Any,
    ) -> None:
        """Insert data_objects + block_io for one direction.

        The scheduler hands us two synchronised views of the same thing:

        * ``payload`` — ``{port_name: [object_id, ...]}`` already unrolled for
          Collections; gives us the object_id we need on ``block_io``.
        * ``port_values`` — the raw wire-format ``{port_name: <dict|list>}``
          mapping where each value carries the full FrameworkMeta +
          storage_path metadata we need to upsert into ``data_objects``.
          Despite the historical name (``outputs=``), this carries inputs
          when ``direction='input'`` — D38-3.2 renamed for clarity.

        We iterate over the union of both, preferring ``payload`` for ordering
        and using ``port_values`` to materialise the matching ``data_objects``
        row when only an object_id string is available.
        """
        if self._store is None:
            return

        outputs_by_port: dict[str, Any] = port_values if isinstance(port_values, dict) else {}

        # Build the unified iteration list. Prefer payload form (its keys are
        # the authoritative port set the scheduler chose) but fall back to
        # the outputs dict for the wire-format details.
        if isinstance(payload, dict) and payload:
            for port_name, items in payload.items():
                if not isinstance(items, list):
                    items = [items]
                wire_items = _wire_items_for_port(outputs_by_port.get(port_name))
                for position, object_id in enumerate(items):
                    wire_dict = wire_items[position] if position < len(wire_items) else None
                    self._persist_io_entry(
                        block_execution_id=block_execution_id,
                        direction=direction,
                        port_name=str(port_name),
                        position=position,
                        object_id=object_id if isinstance(object_id, str) else None,
                        wire_dict=wire_dict,
                    )
            return

        if not outputs_by_port:
            return

        for port_name, value in outputs_by_port.items():
            wire_items = _wire_items_for_port(value)
            for position, item in enumerate(wire_items):
                object_id = _object_id_from_wire(item)
                self._persist_io_entry(
                    block_execution_id=block_execution_id,
                    direction=direction,
                    port_name=str(port_name),
                    position=position,
                    object_id=object_id,
                    wire_dict=item,
                )

    def _persist_io_entry(
        self,
        *,
        block_execution_id: str,
        direction: str,
        port_name: str,
        position: int,
        object_id: str | None,
        wire_dict: dict[str, Any] | None,
    ) -> None:
        """Materialise one ``(data_objects, block_io)`` pair.

        ``object_id`` is preferred when present (canonical from
        ``input_object_ids`` / ``output_object_ids``). When only a wire dict
        is available we extract the object_id from
        ``metadata.framework.object_id``. With neither, the entry is skipped
        silently — legitimate for scalar pass-through values on a port.
        """
        if self._store is None:
            return

        if object_id is None and wire_dict is not None:
            object_id = _object_id_from_wire(wire_dict)
        if object_id is None:
            return

        if wire_dict is not None:
            type_name = _extract_type_name(wire_dict)
            row = DataObjectRow(
                object_id=object_id,
                type_name=type_name,
                wire_payload=wire_dict,
                created_at=datetime.now().isoformat(),
                backend=wire_dict.get("backend") if isinstance(wire_dict.get("backend"), str) else None,
                storage_path=wire_dict.get("path") if isinstance(wire_dict.get("path"), str) else None,
                derived_from=(wire_dict.get("metadata") or {}).get("framework", {}).get("derived_from"),
                produced_by_execution=block_execution_id if direction == "output" else None,
            )
            self._store.upsert_data_object(row)
        else:
            # Inputs referencing an upstream block's output: the producing
            # block already inserted the data_objects row. Verify it exists;
            # if absent (e.g. external input loaded before this run started),
            # stamp a minimal placeholder so the block_io FK is satisfied.
            if self._store.get_data_object(object_id) is None:
                self._store.upsert_data_object(
                    DataObjectRow(
                        object_id=object_id,
                        type_name="DataObject",
                        wire_payload={},
                        created_at=datetime.now().isoformat(),
                    )
                )

        edge = BlockIORow(
            block_execution_id=block_execution_id,
            direction=direction,
            port_name=port_name,
            object_id=object_id,
            position=position,
        )
        self._store.insert_block_io(edge)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_dict(value: Any) -> dict[str, Any]:
    """Return ``value`` if it is a dict, else an empty dict."""
    return dict(value) if isinstance(value, dict) else {}


def _wire_items_for_port(value: Any) -> list[dict[str, Any] | None]:
    """Flatten a wire-format port value into a list of per-item wire dicts.

    Returns an empty list when the value is not a recognised DataObject
    payload (e.g. a scalar int passed through as a port value).
    """
    if isinstance(value, dict):
        if value.get("_collection"):
            return [item if isinstance(item, dict) else None for item in (value.get("items") or [])]
        return [value]
    return []


def _object_id_from_wire(wire: Any) -> str | None:
    """Extract ``metadata.framework.object_id`` from a wire-format dict."""
    if not isinstance(wire, dict):
        return None
    framework = (wire.get("metadata") or {}).get("framework") or {}
    candidate = framework.get("object_id")
    if isinstance(candidate, str) and candidate:
        return candidate
    return None


def _extract_type_name(wire_dict: dict[str, Any]) -> str:
    """Extract the leaf type name from a wire-format payload.

    ``type_chain`` is ordered from most general to most specific
    (see ``scieasy.core.types.base.TypeIdentity``); the leaf — the
    concrete output type that lineage queries / methods exports
    expect — is the LAST element, not the first. Codex P1 reconcile
    on PR #979.

    Hotfix #995: handle Collection wire-wrappers. When a block emits
    ``Collection[T]`` the serialised wire-dict has shape
    ``{"kind": "collection", "item_type": "T", "items": [<T-wire-dict>, ...]}``
    and the root-level ``metadata`` is absent — the per-item type info
    lives at ``items[i].metadata.type_chain``. Pre-#995 the helper
    only inspected the root, so every Collection output landed in
    ``data_objects.type_name`` as the literal ``"DataObject"`` fallback,
    which surfaced in the Lineage tab Methods MD as
    ``Type | DataObject`` instead of ``Image`` / ``Mask`` / etc. (Phase
    4a finding).

    The fix probes the Collection wrapper FIRST so the homogeneous
    Collection invariant (per ADR-038 §3.1) is captured by a single
    type-name read.
    """
    # Hotfix #995: Collection wrapper short-circuit.
    if wire_dict.get("kind") == "collection":
        item_type = wire_dict.get("item_type")
        if isinstance(item_type, str) and item_type:
            return item_type
        items = wire_dict.get("items")
        if isinstance(items, list) and items and isinstance(items[0], dict):
            nested = _extract_type_name(items[0])
            if nested != "DataObject":
                return nested

    metadata = wire_dict.get("metadata") or {}
    type_chain = metadata.get("type_chain")
    if isinstance(type_chain, list) and type_chain:
        leaf = type_chain[-1]
        if isinstance(leaf, str):
            return leaf
    explicit = wire_dict.get("type_name")
    if isinstance(explicit, str):
        return explicit
    return "DataObject"
