"""Lineage row dataclasses for the unified 4-table lineage.db (ADR-038 §3.1).

Each dataclass mirrors one of the four normalized tables:

* :class:`RunRecord`             ↔ ``runs``
* :class:`BlockExecutionRecord`  ↔ ``block_executions``
* :class:`DataObjectRow`         ↔ ``data_objects``
* :class:`BlockIORow`            ↔ ``block_io``

The legacy single-table ``LineageRecord`` from pre-ADR-038 is removed
(D38-3.2 / closes audit D38-3.1a P1-4); the ``ProvenanceGraph`` helper
that consumed it is also deleted. The pre-ADR-038 ``input_hashes`` /
``output_hashes`` / ``partial_output_refs`` / ``environment`` fields are
gone — ADR-038 §3.4 dropped hash-*keyed* identity (object identity is the
UUIDv4 ``object_id`` from FrameworkMeta, not a content digest).

#1529 (DSN-5) re-introduces a single ``content_hash`` *attribute* on
:class:`DataObjectRow` for integrity verification only — it is a digest of
the bytes at ``storage_path`` recorded so a dangling/overwritten artifact
can be detected (ADR-038 §3.5 "no per-run isolation"). It is NOT used as an
identity key and does not resurrect the hash-keyed graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RunRecord:
    """One row in the ``runs`` table — a workflow execution.

    Created by ``ApiRuntime.start_workflow`` (ADR-038 §3.2) before any block
    is dispatched. ``finished_at`` and ``status`` are updated on completion
    via :meth:`LineageRecorder.finalize_run`.
    """

    run_id: str
    workflow_id: str
    workflow_yaml_snapshot: str
    started_at: str
    status: str  # "running" | "completed" | "failed" | "cancelled"
    environment_snapshot: dict[str, Any]
    triggered_by: str = "user"  # "user" | "ai_block" | "execute_from"
    workflow_git_commit: str | None = None  # populated by ADR-039 once wired
    workflow_dirty: int = 0
    finished_at: str | None = None
    parent_run_id: str | None = None
    execute_from_block_id: str | None = None
    user_notes: str | None = None


@dataclass
class BlockExecutionRecord:
    """One row in the ``block_executions`` table — a single block in a run.

    Inserted by :class:`LineageRecorder` on terminal block events
    (BLOCK_DONE / BLOCK_ERROR / BLOCK_CANCELLED / BLOCK_SKIPPED). Per
    ADR-038 §3.2 the ``block_config_resolved`` field is the post-template
    expansion config dict that the runner actually used.
    """

    block_execution_id: str
    run_id: str
    block_id: str
    block_type: str
    block_version: str
    block_config_resolved: dict[str, Any]
    started_at: str
    termination: str  # "completed" | "error" | "cancelled" | "skipped"
    finished_at: str | None = None
    duration_ms: int = 0
    termination_detail: str = ""


@dataclass
class DataObjectRow:
    """One row in the ``data_objects`` table — a single ``DataObject`` ever seen.

    ``wire_payload`` carries the full ADR-031 reference-only envelope so the
    object can be reconstructed even after the underlying storage_path is
    overwritten (ADR-038 §3.5: storage_path is best-effort).
    """

    object_id: str
    type_name: str
    wire_payload: dict[str, Any]
    created_at: str
    backend: str | None = None
    storage_path: str | None = None
    size_bytes: int | None = None
    mtime_at_write: str | None = None
    derived_from: str | None = None
    produced_by_execution: str | None = None  # FK → block_executions.block_execution_id
    # #1529 (DSN-5): xxhash digest of the bytes at ``storage_path`` captured
    # at record time. ``None`` when no storage_path is set or the artifact
    # could not be read. Used by ``LineageStore.detect_dangling_objects`` to
    # flag artifacts whose on-disk bytes no longer match what the run wrote.
    content_hash: str | None = None


@dataclass
class BlockIORow:
    """One row in the ``block_io`` table — port-to-DataObject edge for a run.

    Each input or output of a block_execution is one row. For Collection
    ports, each item is a separate row with an incrementing ``position``
    (ADR-038 §3.1: Collection unrolling).
    """

    block_execution_id: str
    direction: str  # 'input' | 'output'
    port_name: str
    object_id: str
    position: int = 0


# NOTE: The legacy pre-ADR-038 ``LineageRecord`` shell with
# ``input_hashes`` / ``output_hashes`` / ``partial_output_refs`` /
# ``environment`` fields was removed in D38-3.2 (closes audit
# D38-3.1a P1-4). ADR §3.4 explicitly forbids content hashing; any
# code still importing ``LineageRecord`` from this module must migrate
# to :class:`BlockExecutionRecord` + :class:`DataObjectRow` /
# :class:`BlockIORow`.
