"""Lineage row dataclasses for the unified 4-table lineage.db (ADR-038 §3.1).

Each dataclass mirrors one of the four normalized tables:

* :class:`RunRecord`             ↔ ``runs``
* :class:`BlockExecutionRecord`  ↔ ``block_executions``
* :class:`DataObjectRow`         ↔ ``data_objects``
* :class:`BlockIORow`            ↔ ``block_io``

The legacy single-table ``LineageRecord`` from pre-ADR-038 is removed; the
``ProvenanceGraph`` helper that consumed it is also deleted per ADR §3.4
(no content hashing → no hash-keyed graph). Phase D38-2.3 introduces the
6-month deprecation shim for the old ``MetadataStore`` import surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


# ----------------------------------------------------------------------------
# Backwards-compatible alias for downstream code that has not yet migrated.
# Phase D38-2.3 will replace this with a deprecation shim that re-exports the
# unified store. For now, keep ``LineageRecord`` resolvable from the package
# import surface so existing tests that haven't been migrated can be flagged
# explicitly rather than ImportError-ing during collection.
# ----------------------------------------------------------------------------


@dataclass
class LineageRecord:
    """Deprecated: pre-ADR-038 single-table lineage row.

    Kept as a thin shell so that ``from scieasy.core.lineage import LineageRecord``
    still resolves. New code MUST NOT use this; use :class:`BlockExecutionRecord`
    plus :class:`DataObjectRow` / :class:`BlockIORow`.
    """

    block_id: str = ""
    block_config: dict[str, Any] = field(default_factory=dict)
    block_version: str = ""
    input_hashes: dict[str, list[str]] = field(default_factory=dict)
    output_hashes: dict[str, list[str]] = field(default_factory=dict)
    timestamp: str = ""
    duration_ms: int = 0
    environment: Any = None
    termination: str = "completed"
    partial_output_refs: list[str] = field(default_factory=list)
    termination_detail: str = ""
