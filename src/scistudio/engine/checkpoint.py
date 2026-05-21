"""WorkflowCheckpoint -- serialise and deserialise workflow state.

ADR-018: Checkpoint must record all 8 block states including CANCELLED
and SKIPPED.  The ``skip_reasons`` field captures why a block was
cancelled or skipped so that resumed workflows can honour those
decisions.

ADR-038 §3.5 / §5.2 (Phase D38-2.3) — **scope clarification + path move**.
The checkpoint subsystem owns *pause/resume* and the "Run from here on
the most recent run" affordance only (ADR-012, unchanged). It is
**distinct from** the unified run lineage database (``lineage.db``,
ADR-038 §3.1), which records every run's recipe + I/O catalog but does
**not** preserve intermediate data files. Concretely:

* Checkpoint files now live at ``<project>/.scistudio/pause/<workflow_id>/``
  (relocated from the legacy ``<project>/checkpoints/<workflow_id>/``).
  The semantics are unchanged: single-slot per workflow, overwritten on
  every terminal block event, restored only on the latest run.
* Lineage rows persist at ``<project>/.scistudio/lineage.db`` and survive
  across runs — but the on-disk intermediate data they reference may be
  overwritten by subsequent runs (ADR-038 §3.5 "no per-run isolation").

The two subsystems share a directory but no contract.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# intermediate_refs serialisation (Collection-aware)
# ---------------------------------------------------------------------------


def serialize_intermediate_refs(block_outputs: dict[str, Any]) -> dict[str, Any]:
    """Serialize block outputs for checkpoint storage.

    Preserves Collection structure as ``{"_collection": True, "items": [...],
    "item_type": "ClassName"}`` instead of flattening via ``str()``.
    StorageReference-backed objects are serialized as ref dicts.
    """
    result: dict[str, Any] = {}
    for block_id, outputs in block_outputs.items():
        if isinstance(outputs, dict):
            serialized: dict[str, Any] = {}
            for port_name, value in outputs.items():
                serialized[port_name] = _serialize_value(value)
            result[block_id] = serialized
        else:
            result[block_id] = _serialize_value(outputs)
    return result


def _serialize_value(value: Any) -> Any:
    """Serialize a single output value for checkpoint storage."""
    from scistudio.core.types.base import DataObject
    from scistudio.core.types.collection import Collection

    if isinstance(value, Collection):
        items = []
        for item in value:
            if hasattr(item, "storage_ref") and item.storage_ref is not None:
                ref = item.storage_ref
                items.append(
                    {
                        "backend": ref.backend,
                        "path": ref.path,
                        "format": ref.format,
                        "metadata": ref.metadata,
                    }
                )
            else:
                items.append({"_value": str(item), "_type": type(item).__name__})
        return {
            "_collection": True,
            "items": items,
            "item_type": value.item_type.__name__,
        }

    if isinstance(value, DataObject) and hasattr(value, "storage_ref") and value.storage_ref is not None:
        ref = value.storage_ref
        return {
            "backend": ref.backend,
            "path": ref.path,
            "format": ref.format,
            "metadata": ref.metadata,
        }

    if isinstance(value, (str, int, float, bool, type(None), list, dict)):
        return value

    return str(value)


def deserialize_intermediate_refs(data: dict[str, Any]) -> dict[str, Any]:
    """Deserialize checkpoint intermediate_refs back to live objects.

    .. deprecated::
        This function is **not called** in the production execute-from path
        and must not be introduced there.  The execute-from path in
        :meth:`~scistudio.engine.scheduler.DAGScheduler.execute_from` assigns
        ``checkpoint.intermediate_refs[node_id]`` directly to
        ``_block_outputs[node_id]`` as a wire-format dict.  The downstream
        worker subprocess then calls ``_reconstruct_one()`` (ADR-027 Addendum
        1 §1) which reads ``metadata.type_chain`` from the wire-format dict
        and reconstructs the typed object inside the sandboxed subprocess.

        The function is preserved (not deleted) for:
        - historical reference and future testing utilities
        - potential use in offline / introspection tooling that does not
          route through the subprocess execution path

        Do **not** call this from within the scheduler, runner, or any path
        that feeds inputs to a worker subprocess.

    ADR-031 D8: Reconstructs typed :class:`DataObject` instances (not
    ViewProxy) from serialized StorageReference dicts, using the same
    ``_reconstruct_one()`` path as the worker. Falls back to a base
    ``DataObject(storage_ref=ref)`` if type resolution fails.
    """
    result: dict[str, Any] = {}
    for block_id, outputs in data.items():
        if isinstance(outputs, dict):
            result[block_id] = {port_name: _deserialize_value(value) for port_name, value in outputs.items()}
        else:
            result[block_id] = _deserialize_value(outputs)
    return result


def _deserialize_value(value: Any) -> Any:
    """Deserialize a single value from checkpoint storage.

    ADR-031 D8: constructs typed DataObject instances via
    ``_reconstruct_one()`` instead of ViewProxy. Falls back to base
    ``DataObject(storage_ref=ref)`` if type resolution fails.
    """
    if not isinstance(value, dict):
        return value

    # --- Collection structure ---
    if value.get("_collection") is True:
        if "items" not in value or "item_type" not in value:
            logger.warning(
                "Malformed _collection dict (missing 'items' or 'item_type'), returning raw data: %s",
                list(value.keys()),
            )
            return value

        from scistudio.core.types.base import DataObject

        item_type_name: str = value["item_type"]
        objects: list[DataObject] = []
        for item_data in value["items"]:
            if not isinstance(item_data, dict):
                continue
            if "_value" in item_data:
                logger.warning(
                    "Cannot fully reconstruct non-persisted item (type=%s, value=%s) — skipping",
                    item_data.get("_type", "unknown"),
                    item_data["_value"],
                )
                continue
            if "backend" in item_data and "path" in item_data:
                # Try typed reconstruction via _reconstruct_one.
                obj = _try_reconstruct(item_data, item_type_name)
                objects.append(obj)

        return {"_collection": True, "items": objects, "item_type": item_type_name}

    # --- Single StorageReference dict ---
    if "backend" in value and "path" in value:
        return _try_reconstruct(value, "DataObject")

    return value


def _try_reconstruct(item_data: dict[str, Any], fallback_type_name: str) -> Any:
    """Attempt typed DataObject reconstruction; fall back to base DataObject.

    ADR-031 D8: uses ``_reconstruct_one()`` from the serialization module
    when a ``metadata.type_chain`` is available. Otherwise constructs a
    base ``DataObject`` with ``storage_ref`` set.
    """
    from scistudio.core.storage.ref import StorageReference
    from scistudio.core.types.base import DataObject

    # Build a wire-format payload compatible with _reconstruct_one.
    item_meta = item_data.get("metadata") or {}
    item_chain = item_meta.get("type_chain") if isinstance(item_meta, dict) else None

    if isinstance(item_chain, list) and item_chain:
        # Has type_chain — try full typed reconstruction.
        try:
            from scistudio.core.types.serialization import _reconstruct_one

            return _reconstruct_one(item_data)
        except Exception:
            logger.warning(
                "Typed reconstruction failed for type_chain=%s, falling back to base DataObject",
                item_chain,
                exc_info=True,
            )

    # Fallback: construct base DataObject with storage_ref.
    ref = StorageReference(
        backend=item_data["backend"],
        path=item_data["path"],
        format=item_data.get("format"),
        metadata=item_data.get("metadata"),
    )
    return DataObject(storage_ref=ref)


@dataclass
class WorkflowCheckpoint:
    """Snapshot of a workflow execution that can be persisted and restored.

    Captures block states, intermediate data references, and configuration
    so that execution can be resumed from this point.
    """

    workflow_id: str
    timestamp: datetime
    block_states: dict[str, str]
    intermediate_refs: dict[str, Any] = field(default_factory=dict)
    pending_block: str | None = None
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    skip_reasons: dict[str, str] = field(default_factory=dict)  # ADR-018: block_id → skip reason


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def save_checkpoint(checkpoint: WorkflowCheckpoint, path: str | Path) -> None:
    """Persist *checkpoint* to the file at *path*.

    The checkpoint is serialised as JSON.  The ``timestamp`` field is
    written in ISO-8601 format.  Any non-JSON-native values inside
    ``intermediate_refs`` or ``config_snapshot`` are coerced to strings
    via the ``default=str`` fallback.

    Parameters
    ----------
    checkpoint:
        The checkpoint data to write.
    path:
        Destination file path (will be created or overwritten).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(checkpoint)
    data["timestamp"] = checkpoint.timestamp.isoformat()
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_checkpoint(path: str | Path) -> WorkflowCheckpoint:
    """Restore a :class:`WorkflowCheckpoint` from a previously saved file.

    Parameters
    ----------
    path:
        File path written by :func:`save_checkpoint`.

    Returns
    -------
    WorkflowCheckpoint
        The deserialised checkpoint.
    """
    path = Path(path)
    with open(path) as f:
        data = json.load(f)
    data["timestamp"] = datetime.fromisoformat(data["timestamp"])
    return WorkflowCheckpoint(**data)


# ---------------------------------------------------------------------------
# CheckpointManager
# ---------------------------------------------------------------------------


class CheckpointManager:
    """Manages checkpoint files for workflow executions.

    Checkpoints are stored as JSON files in a configurable directory,
    named ``checkpoint_<workflow_id>.json``.  When an :class:`EventBus`
    is provided the manager automatically subscribes to terminal block
    events (``BLOCK_DONE``, ``BLOCK_ERROR``, ``BLOCK_CANCELLED``,
    ``BLOCK_SKIPPED``) so that a future scheduler integration can
    trigger auto-saves on state changes.

    Path: per ADR-038 §5.2 (Phase D38-2.3), :class:`ApiRuntime` passes
    ``<project>/.scistudio/pause/<workflow_id>/`` as the
    ``checkpoint_dir`` argument. The class itself remains
    location-agnostic — callers in tests / CLI may still pass a
    ``tmp_path`` and the manager will create / use that directory.
    """

    def __init__(self, checkpoint_dir: str | Path, event_bus: Any = None) -> None:
        self._checkpoint_dir = Path(checkpoint_dir)
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._latest: WorkflowCheckpoint | None = None
        if event_bus is not None:
            from scistudio.engine.events import (
                BLOCK_CANCELLED,
                BLOCK_DONE,
                BLOCK_ERROR,
                BLOCK_SKIPPED,
            )

            event_bus.subscribe(BLOCK_DONE, self._on_state_change)
            event_bus.subscribe(BLOCK_ERROR, self._on_state_change)
            event_bus.subscribe(BLOCK_CANCELLED, self._on_state_change)
            event_bus.subscribe(BLOCK_SKIPPED, self._on_state_change)

    # -- public API ---------------------------------------------------------

    def save(self, checkpoint: WorkflowCheckpoint) -> Path:
        """Write *checkpoint* to disk and update :pyattr:`latest`.

        Returns the path of the saved file.
        """
        path = self._checkpoint_dir / f"checkpoint_{checkpoint.workflow_id}.json"
        save_checkpoint(checkpoint, path)
        self._latest = checkpoint
        return path

    def load(self, workflow_id: str) -> WorkflowCheckpoint | None:
        """Load the checkpoint for *workflow_id*, or ``None`` if absent."""
        path = self._checkpoint_dir / f"checkpoint_{workflow_id}.json"
        if path.exists():
            return load_checkpoint(path)
        return None

    # -- EventBus callback --------------------------------------------------

    def _on_state_change(self, event: Any) -> None:
        """Hook invoked on terminal block events.

        ADR-018: Auto-save checkpoint when latest state is available.
        If a checkpoint has been saved previously (via save()), updates it
        with the new block state from the event.
        """
        if self._latest is not None:
            block_id = getattr(event, "block_id", None)
            event_type = getattr(event, "event_type", "")
            if block_id and event_type:
                self._latest.block_states[block_id] = event_type.replace("block_", "")
                self.save(self._latest)

    # -- properties ---------------------------------------------------------

    @property
    def latest(self) -> WorkflowCheckpoint | None:
        """The most recently saved checkpoint (in-memory cache)."""
        return self._latest
