"""Row dataclasses for the four lineage tables.

Each dataclass mirrors one of the four tables in the lineage database:

* :class:`RunRecord`             ↔ ``runs``
* :class:`BlockExecutionRecord`  ↔ ``block_executions``
* :class:`DataObjectRow`         ↔ ``data_objects``
* :class:`BlockIORow`            ↔ ``block_io``

Object identity is the ``object_id`` carried in a ``DataObject``'s framework
metadata, not a content digest. :class:`DataObjectRow` does keep a separate
``content_hash`` purely for integrity checks (detecting an artifact whose bytes
were later overwritten); it is never used as an identity key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RunRecord:
    """One row in the ``runs`` table — a single workflow execution.

    Created when a workflow starts, before any block runs. The terminal fields
    (``finished_at``, ``status``) are filled in when the run completes.
    """

    run_id: str
    """Unique identifier for this run."""
    workflow_id: str
    """Identifier of the workflow that was executed."""
    workflow_yaml_snapshot: str
    """The workflow definition (YAML) exactly as it was at run time."""
    started_at: str
    """ISO-8601 timestamp of when the run started."""
    status: str
    """Run status: one of ``"running"``, ``"completed"``, ``"failed"``, ``"cancelled"``."""
    environment_snapshot: dict[str, Any]
    """Captured Python/package environment for the run (see :class:`EnvironmentSnapshot`)."""
    triggered_by: str = "user"
    """What started the run: ``"user"``, ``"ai_block"``, or ``"execute_from"``."""
    workflow_git_commit: str | None = None
    """Git commit SHA of the workflow at run time, or ``None`` when not recorded."""
    workflow_dirty: int = 0
    """``1`` if the workflow had uncommitted changes at run time, else ``0``."""
    finished_at: str | None = None
    """ISO-8601 timestamp of when the run finished, or ``None`` while it is still running."""
    parent_run_id: str | None = None
    """The parent run's id when this run was spawned from another, else ``None``."""
    execute_from_block_id: str | None = None
    """For a partial re-run, the block the run started from, else ``None``."""
    user_notes: str | None = None
    """Optional free-form notes attached to the run."""


@dataclass
class BlockExecutionRecord:
    """One row in the ``block_executions`` table — one block within a run.

    Recorded when a block reaches a terminal state (done, error, cancelled, or
    skipped). ``block_config_resolved`` is the block's configuration after
    template expansion — the values the runner actually used.
    """

    block_execution_id: str
    """Unique identifier for this block execution."""
    run_id: str
    """Identifier of the run this block belongs to."""
    block_id: str
    """Identifier of the block within the workflow graph."""
    block_type: str
    """The block's type name."""
    block_version: str
    """The block type's version string."""
    block_config_resolved: dict[str, Any]
    """The block configuration after template expansion — what the runner actually used."""
    started_at: str
    """ISO-8601 timestamp of when the block started."""
    termination: str
    """How the block ended: ``"completed"``, ``"error"``, ``"cancelled"``, or ``"skipped"``."""
    finished_at: str | None = None
    """ISO-8601 timestamp of when the block finished, or ``None`` if unknown."""
    duration_ms: int = 0
    """Wall-clock duration of the block in milliseconds."""
    termination_detail: str = ""
    """Extra detail about the outcome (e.g. an error message); empty when none."""


@dataclass
class DataObjectRow:
    """One row in the ``data_objects`` table — a single ``DataObject`` ever seen.

    ``wire_payload`` carries the full reference-only envelope, so the object can
    be reconstructed later even if the underlying ``storage_path`` is
    overwritten.
    """

    object_id: str
    """Stable identifier for the data object (from its framework metadata)."""
    type_name: str
    """The data object's concrete type name (e.g. ``"Image"``, ``"Mask"``)."""
    wire_payload: dict[str, Any]
    """The full reference-only envelope used to reconstruct the object."""
    created_at: str
    """ISO-8601 timestamp of when this row was recorded."""
    backend: str | None = None
    """Storage backend that holds the object's data (e.g. ``"zarr"``), or ``None``."""
    storage_path: str | None = None
    """On-disk location of the object's data; best-effort and may later be overwritten."""
    size_bytes: int | None = None
    """Size of the stored bytes at record time, or ``None`` when unknown."""
    mtime_at_write: str | None = None
    """Modification time of the stored file at record time, or ``None`` when unknown."""
    derived_from: str | None = None
    """The parent object's ``object_id`` when this object was derived, else ``None``."""
    produced_by_execution: str | None = None
    """The ``block_execution_id`` that produced this object, or ``None`` for external inputs."""
    # Content digest captured at record time so a later run that overwrites the
    # same storage_path can be detected as a dangling artifact.
    content_hash: str | None = None
    """Digest of the bytes at ``storage_path`` at record time, used to detect a later overwrite; ``None`` when not computable."""


@dataclass
class BlockIORow:
    """One row in the ``block_io`` table — a port-to-DataObject edge for a run.

    Each input or output of a block execution is one row. For a Collection
    port, each item is a separate row with an incrementing ``position``.
    """

    block_execution_id: str
    """The block execution this edge belongs to."""
    direction: str
    """Whether the object was an ``"input"`` or an ``"output"`` of the block."""
    port_name: str
    """Name of the port the object flowed through."""
    object_id: str
    """Identifier of the data object on this edge."""
    position: int = 0
    """Index within a Collection port; ``0`` for a single (non-Collection) value."""
