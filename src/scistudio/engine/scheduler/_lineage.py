"""Lineage + output-persistence method implementations for :class:`DAGScheduler`.

ADR-046 §3 (Lineage + output group): extracted verbatim from the
original ``engine/scheduler.py`` god-file. Pure structural move per
umbrella #1427 Phase 3 — no behavior changes. ADR-038/039 emission
contracts are preserved.

Each function is a free function whose first parameter is ``self`` —
they are bound onto :class:`DAGScheduler` in
``scheduler/__init__.py`` via class-body static assignment so griffe
emits the canonical ``scistudio.engine.scheduler.DAGScheduler.<method>``
fact (see ADR-042 + the doc/closure audit walker).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ._helpers import _collect_object_ids, _extract_error_summary

if TYPE_CHECKING:
    from . import DAGScheduler

logger = logging.getLogger("scistudio.engine.scheduler")


# -- ADR-038 §5.2: DataObject identity persistence -----------------------


def _persist_output_metadata(
    self: DAGScheduler,
    node_id: str,
    result: dict[str, Any] | Any,
    workflow_id: str,
) -> None:
    """Persist DataObject identity rows to the unified ``data_objects`` table.

    Phase D38-2.3 (ADR-038 §6 Phase 2): replaces the pre-ADR-038
    ``metadata.db`` write path. Writes go to the active
    :class:`~scistudio.core.lineage.LineageStore`.

    **Recorder-aware split (Codex P1 #931):** when a
    :class:`LineageRecorder` is bound to this scheduler, the recorder
    owns the authoritative write of every ``data_objects`` row from
    its ``BLOCK_DONE`` handler. The recorder stamps the
    ``produced_by_execution`` foreign key with the same
    ``block_execution_id`` it writes to ``block_executions``. Letting
    the scheduler also pre-write would call ``upsert_data_object()``
    (which uses ``INSERT OR IGNORE``), permanently fixing the row's
    ``produced_by_execution`` to ``NULL`` and breaking the ADR §3.7
    Q4b join. So when a recorder is present this method is a no-op —
    the recorder's pass writes the row with the correct producer.

    When the scheduler is constructed *without* a recorder (CLI /
    direct test runners that bypass :class:`ApiRuntime`), this method
    is the only writer. In that mode the row's
    ``produced_by_execution`` is legitimately ``NULL`` because no
    ``block_executions`` row exists to reference.

    The method is **non-fatal**: any exception is logged as a warning
    and does not crash the workflow.
    """
    # Recorder owns the write path when bound — see docstring.
    if self._lineage_recorder is not None:
        return
    try:
        store = self._resolve_lineage_store()
        if store is None:
            return
        if not isinstance(result, dict):
            return
        for port_name, value in result.items():
            self._persist_single_output(store, value, workflow_id, node_id, port_name)
    except Exception:
        logger.warning(
            "ADR-038: data_objects persist failed for node %s (non-fatal)",
            node_id,
            exc_info=True,
        )


def _resolve_lineage_store(self: DAGScheduler) -> Any:
    """Return the active :class:`LineageStore`, or ``None``.

    Looks first at the lineage recorder bound to this scheduler, then
    falls back to the deprecation shim's module-level handle which
    :meth:`ApiRuntime._init_lineage_store` publishes on project open.
    The lazy import keeps the scheduler usable outside the API server
    (CLI / direct test invocation that bypasses :class:`ApiRuntime`).
    """
    recorder = self._lineage_recorder
    if recorder is not None:
        store = getattr(recorder, "_store", None)
        if store is not None:
            return store
    try:
        from scistudio.core.metadata_store import _active_lineage_store

        return _active_lineage_store()
    except Exception:
        return None


def _persist_single_output(
    self: DAGScheduler,
    store: Any,
    value: Any,
    workflow_id: str,
    node_id: str,
    port_name: str,
) -> None:
    """Upsert one output port's wire payload(s) into ``data_objects``."""
    if not isinstance(value, dict):
        return
    # Collection: {"_collection": True, "items": [...], "item_type": "..."}
    if value.get("_collection"):
        for item in value.get("items", []):
            if isinstance(item, dict) and "metadata" in item:
                self._upsert_wire_row(store, item, node_id, port_name)
    elif "metadata" in value:
        self._upsert_wire_row(store, value, node_id, port_name)


def _upsert_wire_row(
    self: DAGScheduler,
    store: Any,
    wire_dict: dict[str, Any],
    node_id: str,
    port_name: str,
) -> None:
    """Materialise one ``DataObjectRow`` for a wire payload and upsert."""
    try:
        from datetime import datetime

        from scistudio.core.lineage.record import DataObjectRow
    except Exception:
        logger.debug(
            "ADR-038: lineage record import failed for %s/%s (non-fatal)",
            node_id,
            port_name,
            exc_info=True,
        )
        return
    metadata = wire_dict.get("metadata") or {}
    framework = metadata.get("framework") or {}
    object_id = framework.get("object_id") if isinstance(framework, dict) else None
    if not isinstance(object_id, str) or not object_id:
        return

    type_chain = metadata.get("type_chain")
    type_name = "DataObject"
    if isinstance(type_chain, list) and type_chain:
        # type_chain is ordered most-general -> most-specific; the leaf
        # (concrete output type) is the LAST element, matching
        # LineageRecorder._extract_type_name. Reading [0] recorded the base
        # "DataObject" for every object on the scheduler/no-recorder (CLI)
        # write path (#1757).
        leaf = type_chain[-1]
        if isinstance(leaf, str):
            type_name = leaf
    elif isinstance(wire_dict.get("type_name"), str):
        type_name = wire_dict["type_name"]

    created_at = framework.get("created_at") if isinstance(framework, dict) else None
    if not isinstance(created_at, str) or not created_at:
        created_at = datetime.now().isoformat()

    row = DataObjectRow(
        object_id=object_id,
        type_name=type_name,
        wire_payload=wire_dict,
        created_at=created_at,
        backend=wire_dict.get("backend") if isinstance(wire_dict.get("backend"), str) else None,
        storage_path=wire_dict.get("path") if isinstance(wire_dict.get("path"), str) else None,
        derived_from=framework.get("derived_from") if isinstance(framework, dict) else None,
        # ``produced_by_execution`` is FK to ``block_executions``.
        # The LineageRecorder owns that table and back-stamps the
        # column from the BLOCK_DONE event handler. We leave it None
        # here and rely on the recorder's INSERT OR IGNORE — but the
        # recorder also re-inserts with ``produced_by_execution`` set
        # for output direction, so the join key gets populated on the
        # recorder's pass.
        produced_by_execution=None,
    )
    try:
        store.upsert_data_object(row)
    except Exception:
        logger.warning(
            "ADR-038: upsert_data_object failed for %s/%s (non-fatal)",
            node_id,
            port_name,
        )


def _sync_checkpoint_to_store(self: DAGScheduler) -> None:
    """Backfill ``data_objects`` rows from checkpoint data on resume.

    ADR-038 §5.2: when ``execute_from()`` reloads intermediate refs
    from a checkpoint, the referenced DataObjects may not yet exist
    in ``lineage.db`` (the checkpoint pre-dates the run). Iterate the
    rehydrated outputs and upsert each one so downstream
    ``block_io`` FK constraints succeed when the resumed run emits
    BLOCK_DONE.
    """
    try:
        store = self._resolve_lineage_store()
        if store is None:
            return
        workflow_id = self._workflow.id
        for node_id, outputs in self._block_outputs.items():
            if not isinstance(outputs, dict):
                continue
            for port_name, value in outputs.items():
                self._persist_single_output(store, value, workflow_id, node_id, port_name)
    except Exception:
        logger.warning(
            "ADR-038: checkpoint-to-store sync failed (non-fatal)",
            exc_info=True,
        )


# -- ADR-038 §3.2: lineage event-data extension --------------------------


def _build_block_done_data(
    self: DAGScheduler,
    *,
    node_id: str,
    block: Any,
    inputs: dict[str, Any],
    config: dict[str, Any],
    outputs: dict[str, Any] | Any,
    environment: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assemble the BLOCK_DONE event payload (ADR-038 §3.2).

    In addition to the legacy ``workflow_id`` + ``outputs`` keys this
    emits the fields that :class:`LineageRecorder` needs to write the
    ``block_executions`` / ``data_objects`` / ``block_io`` rows:

    * ``config``               — resolved config dict (post-template expansion)
    * ``block_type``           — registry type name for the block
    * ``block_version``        — registry-resolved version per ADR-038 §3.3
    * ``environment``          — full env snapshot from the worker
    * ``input_object_ids``     — ``{port: [object_id, ...]}`` derived from inputs
    * ``output_object_ids``    — same shape for outputs
    * ``inputs``               — raw wire-format inputs (fallback for the recorder)
    """
    block_type = self._resolve_block_type(node_id, block)
    block_version = self._resolve_block_version(block, block_type)
    # ADR-051 / FR-011: the user's interactive decision travels inside the
    # resolved config and IS recorded as provenance, but the engine-held
    # intermediate scratch references are ephemeral optimisation, not
    # provenance — strip them from the recorded config.
    recorded_config = dict(config) if isinstance(config, dict) else {}
    recorded_config.pop("interactive_intermediate", None)
    return {
        "workflow_id": self._workflow.id,
        "outputs": outputs,
        "inputs": inputs,
        "config": recorded_config,
        "block_type": block_type,
        "block_version": block_version,
        "environment": environment,
        "input_object_ids": _collect_object_ids(inputs),
        "output_object_ids": _collect_object_ids(outputs),
    }


def _build_block_terminal_data(
    self: DAGScheduler,
    *,
    node_id: str,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the BLOCK_ERROR / BLOCK_CANCELLED / BLOCK_SKIPPED payload.

    D38-3.2 (closes audit D38-3.1a P1-1 + D38-3.1b P1-3): all four
    terminal events must carry the ADR-038 §3.2 metadata so the
    recorder writes non-empty ``block_type`` / ``block_version`` /
    ``block_config_resolved`` columns into ``block_executions``.
    Without this, ADR §3.7 Q3 ("which blocks ran in run X") returns
    empty strings for any non-completed block, breaking methods
    export and downstream queries.

    Best-effort: block instantiation may have failed *before* the
    block object exists (the pre-dispatch error paths). In that
    case the registry NodeDef still carries ``block_type``, so we
    look up the version from the registry by type alone.
    ``inputs`` is sampled at terminal time from ``_block_outputs``
    of upstream nodes (read-only via ``_gather_inputs``); when that
    sample fails (e.g. cancel during dispatch) we fall back to an
    empty dict.
    """
    node = self._dag.nodes.get(node_id)
    block_type = ""
    if node is not None:
        block_type = str(getattr(node, "block_type", "") or "")

    block_version = ""
    config: dict[str, Any] = {}
    if node is not None:
        cfg = getattr(node, "config", None)
        if isinstance(cfg, dict):
            config = dict(cfg)
        # Registry-resolved version (ADR-038 §3.3 force-injection at
        # scan time). When the registry isn't wired (mock-runner
        # tests) fall back to a blank string — the recorder writes
        # the empty string into the NOT NULL column without raising.
        if self._registry is not None and block_type:
            try:
                spec = self._registry.get_spec(block_type)
                if spec is not None and getattr(spec, "version", None):
                    block_version = str(spec.version)
            except Exception:
                logger.debug(
                    "Block version registry lookup failed for terminal-event %s/%s",
                    node_id,
                    block_type,
                )

    try:
        inputs = self._gather_inputs(node_id)
    except Exception:
        inputs = {}

    data: dict[str, Any] = {
        "workflow_id": self._workflow.id,
        "block_type": block_type,
        "block_version": block_version,
        "config": config,
        "inputs": inputs,
        "input_object_ids": _collect_object_ids(inputs),
        "output_object_ids": {},
    }
    if error is not None:
        data["error"] = error
        data["error_summary"] = _extract_error_summary(error)
    if extra:
        data.update(extra)
    return data


def _resolve_block_type(self: DAGScheduler, node_id: str, block: Any) -> str:
    """Return the registry type name for ``block``, falling back to NodeDef."""
    node = self._dag.nodes.get(node_id)
    block_type = getattr(node, "block_type", None) if node is not None else None
    if block_type:
        return str(block_type)
    return type(block).__name__


def _resolve_block_version(self: DAGScheduler, block: Any, block_type: str) -> str:
    """Return the version stamped on the block spec at registry scan time.

    Per ADR-038 §3.3 the registry force-injects this from
    ``importlib.metadata`` at scan time. When the registry is not wired
    up (mock-runner tests), fall back to the block class's ``version``
    attribute and then to ``scistudio.__version__``.
    """
    if self._registry is not None:
        try:
            spec = self._registry.get_spec(block_type)
            if spec is not None and getattr(spec, "version", None):
                return str(spec.version)
        except Exception:
            logger.debug("Block version registry lookup failed for %s", block_type)
    explicit = getattr(block, "version", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    try:
        from scistudio import __version__ as scistudio_version

        return str(scistudio_version)
    except Exception:
        return "unknown"
