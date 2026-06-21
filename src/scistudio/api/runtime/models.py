"""Plain data records shared across the ``api.runtime`` sub-modules.

#1597 / round-4 no-cycles: these dataclasses used to live in the package
``__init__``. The free-function sub-modules (``_data``, ``_runs``,
``_projects``) construct them at runtime, so they imported them back from
``scistudio.api.runtime`` — a child -> parent edge that closed an import
cycle around the package facade. Hosting the records in this leaf module
breaks that edge: ``models`` imports nothing from its own package (every
type reference is annotation-only under ``TYPE_CHECKING``), and the package
``__init__`` re-exports the records so the public
``from scistudio.api.runtime import DataRecord`` surface is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncio

    from scistudio.core.storage.ref import StorageReference
    from scistudio.engine.checkpoint import CheckpointManager
    from scistudio.engine.scheduler import DAGScheduler


@dataclass
class KnownProject:
    """Persisted metadata for a known project workspace."""

    id: str
    name: str
    path: str
    description: str = ""
    last_opened: str | None = None


@dataclass
class DataRecord:
    """Opaque registry entry for a previewable data object."""

    id: str
    ref: StorageReference
    type_name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    # ADR-027 D2 / #407: full type chain from the worker subprocess wire format,
    # e.g. ["DataObject", "Array", "Image"]. Used by the routed previewer target
    # resolution to resolve plugin types via TypeRegistry instead of relying on
    # class name equality.
    type_chain: list[str] = field(default_factory=list)


@dataclass
class WorkflowRun:
    """Track a live scheduler task for a workflow.

    ADR-039 §3.4 / §3.4a: ``workflow_git_commit`` captures the HEAD SHA of
    the project's git repo at workflow-start time (post pre-run auto-commit
    when the working tree was dirty). It is the ADR-038 ``runs.workflow_git_commit``
    join key. Populated by :meth:`ApiRuntime.start_workflow` end-to-end; the
    LineageRecorder (ADR-038) reads this when persisting the ``runs`` row.

    The field is ``None`` only when the project is not a git repository
    (degraded mode per ADR-039 §3.9) or auto-commit failed both ways.
    """

    scheduler: DAGScheduler
    task: asyncio.Task[None]
    checkpoint_manager: CheckpointManager
    workflow_git_commit: str | None = None
