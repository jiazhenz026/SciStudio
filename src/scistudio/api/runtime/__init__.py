"""Shared runtime services for the FastAPI layer.

Issue #1430 / umbrella #1427: the original god-file ``api/runtime.py``
(~1839 LOC) was split into concern-specific sub-modules under this
package. The full public surface from before the split is defined
*directly* in this ``__init__`` (or re-exported from sub-modules) so
existing callers — ``from scistudio.api.runtime import X`` and
``from scistudio.api import runtime`` followed by ``runtime.X`` —
keep working unchanged.

The split is structural-only with **no behavior changes**. Each
sub-module is well under the 750-LOC god-file threshold.

Sub-module layout:

* ``_helpers``         — ``_now_iso``, ``_slugify``, ``_safe_parent_dir``, ``_rmtree_force``
* ``_preview_cache``   — DataFrame preview cache + pyarrow IO helpers
* ``_preview_image``   — raster preview helpers + ``_infer_type_name_from_ref``
* ``_projects``        — project CRUD + registry refresh (free functions)
* ``_workflows``       — workflow YAML I/O + upload (free functions)
* ``_data``            — data catalog + preview routing (free functions)
* ``_runs``            — workflow execution + lineage (free functions)

``ApiRuntime`` itself is defined here (not in a sub-module) so the
static analyser griffe emits the canonical
``scistudio.api.runtime.ApiRuntime`` fact and its
``scistudio.api.runtime.ApiRuntime.<method>`` attribute facts. Each
method is bound from the corresponding free function in a sub-module
via a class-body static assignment.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scistudio.blocks.registry import BlockRegistry
from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.registry import TypeRegistry
from scistudio.engine.checkpoint import CheckpointManager
from scistudio.engine.events import EventBus
from scistudio.engine.resources import ResourceManager
from scistudio.engine.runners.local import LocalRunner
from scistudio.engine.runners.process_handle import ProcessRegistry
from scistudio.engine.scheduler import DAGScheduler

from . import _data, _projects, _runs, _workflows
from ._helpers import _now_iso, _rmtree_force, _safe_parent_dir, _slugify
from ._preview_cache import (
    _TABLE_CACHE_MAX,
    MAX_TABLE_PAGE_SIZE,
    _get_preview_table,
    _read_preview_table_from_disk,
    _table_cache,
    _table_cache_lock,
    _trim_table_cache_locked,
)
from ._preview_image import (
    _downsample_matrix,
    _image_data_uri_from_matrix,
    _infer_type_name_from_ref,
    _load_preview_matrix,
)

logger = logging.getLogger("scistudio.api.runtime")


# ----------------------------------------------------------------------
# Dataclasses owned by ``ApiRuntime``
#
# Defined at package-level so griffe emits canonical facts at
# ``scistudio.api.runtime.<Name>`` rather than a sub-module path.
# ----------------------------------------------------------------------


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
    # e.g. ["DataObject", "Array", "Image"]. Used by preview_data() to resolve
    # plugin types via TypeRegistry instead of relying on class name equality.
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


class LogBroadcaster:
    """Fan-out log events to SSE subscribers."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    async def publish(
        self,
        *,
        level: str,
        message: str,
        workflow_id: str | None = None,
        block_id: str | None = None,
    ) -> None:
        payload = {
            "timestamp": _now_iso(),
            "level": level,
            "message": message,
            "workflow_id": workflow_id,
            "block_id": block_id,
        }
        for queue in list(self._subscribers):
            await queue.put(payload)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)


class ApiRuntime:
    """Shared mutable state owned by the FastAPI application.

    The class is defined here (in ``__init__.py``) rather than in a
    sub-module so griffe emits ``scistudio.api.runtime.ApiRuntime`` as
    the canonical symbol fact. Method implementations live in the
    sibling sub-modules (``_projects``, ``_workflows``, ``_data``,
    ``_runs``); each method is bound below via a class-body static
    assignment so static analysis still sees the method as a member of
    ``ApiRuntime`` (a discoverable Attribute on the class, subject
    path ``scistudio.api.runtime.ApiRuntime.<method>``).

    Issue #1430 / umbrella #1427: behavior unchanged from the
    pre-split implementation.
    """

    def __init__(self) -> None:
        self.registry_dir = Path.home() / ".scistudio"
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.known_projects_path = self.registry_dir / "projects.json"
        self.known_projects: dict[str, KnownProject] = {}

        self.active_project: KnownProject | None = None
        self.data_catalog: dict[str, DataRecord] = {}
        self.workflow_runs: dict[str, WorkflowRun] = {}
        # ADR-034: the MCP server's TCP/socket port is published into the
        # active project's ``.scistudio/`` so the per-project ``mcp-bridge``
        # subprocess can discover it.
        self._mcp_port: int | None = None
        # ADR-039 §5.2: the in-memory ``_workflow_revisions`` counter and its
        # ``If-Match`` enforcement path were removed in D39-2.1. Git commit SHA
        # plus the working-tree dirty state (D39-2.2b) replace the optimistic-
        # concurrency model.

        self.event_bus = EventBus()
        self.resource_manager = ResourceManager(event_bus=self.event_bus)
        self.process_registry = ProcessRegistry()
        self.runner = LocalRunner(event_bus=self.event_bus, registry=self.process_registry)
        self.block_registry = BlockRegistry()
        self.type_registry = TypeRegistry()
        self.log_broadcaster = LogBroadcaster()
        # ADR-038 §3.1: project-scoped unified lineage store. Opened on
        # ``open_project`` and closed when switching projects. ``None`` when
        # no project is open or when initialization failed (best-effort).
        self.lineage_store: Any = None

        self._load_known_projects()
        self._configure_static_registries()
        self._bind_event_logging()

    def _configure_static_registries(self) -> None:
        include_monorepo = os.environ.get("SCISTUDIO_DEV") == "1"
        if include_monorepo:
            logger.info("SCISTUDIO_DEV=1: monorepo package scan enabled")
        self.refresh_type_registry()
        self.refresh_block_registry()

    def _bind_event_logging(self) -> None:
        async def _emit_log(event: Any) -> None:
            message = event.event_type.replace("_", " ")
            workflow_id = None
            if isinstance(event.data, dict):
                workflow_id = event.data.get("workflow_id")
            await self.log_broadcaster.publish(
                level="info",
                message=message,
                workflow_id=workflow_id,
                block_id=event.block_id,
            )

        async def _register_outputs(event: Any) -> None:
            if event.event_type != "block_done":
                return
            outputs = event.data.get("outputs", {}) if isinstance(event.data, dict) else {}
            event.data["outputs"] = self.register_output_payload(outputs)

        for event_type in (
            "workflow_started",
            "workflow_completed",
            "block_running",
            "block_done",
            "block_error",
            "block_cancelled",
            "block_skipped",
        ):
            self.event_bus.subscribe(event_type, _register_outputs)
            self.event_bus.subscribe(event_type, _emit_log)

    # ------------------------------------------------------------------
    # Bound methods (static class-body assignment).
    #
    # Each free function in ``_projects`` / ``_workflows`` / ``_data`` /
    # ``_runs`` takes ``self: ApiRuntime`` as its first parameter; the
    # descriptor protocol turns the assignment into a bound method on
    # instances. Griffe sees each name as a class Attribute, emitting
    # the canonical ``scistudio.api.runtime.ApiRuntime.<method>`` fact
    # that ADR-038 / ADR-039 contract claims resolve against.
    # ------------------------------------------------------------------

    # Project lifecycle (_projects)
    _load_known_projects = _projects._load_known_projects
    _save_known_projects = _projects._save_known_projects
    refresh_block_registry = _projects.refresh_block_registry
    refresh_type_registry = _projects.refresh_type_registry
    _init_lineage_store = _projects._init_lineage_store
    _init_metadata_store = _projects._init_metadata_store
    create_project = _projects.create_project
    list_projects = _projects.list_projects
    _load_project_from_path = _projects._load_project_from_path
    open_project = _projects.open_project
    set_mcp_port = _projects.set_mcp_port
    _publish_mcp_port = _projects._publish_mcp_port
    update_project = _projects.update_project
    delete_project = _projects.delete_project
    project_response = _projects.project_response
    require_active_project = _projects.require_active_project
    list_project_workflows = _projects.list_project_workflows

    # Workflow I/O + upload (_workflows)
    workflow_path = _workflows.workflow_path
    save_workflow = _workflows.save_workflow
    load_workflow = _workflows.load_workflow
    _config_schema_for_block = _workflows._config_schema_for_block
    _relativify_node_config = _workflows._relativify_node_config
    _absolutify_node_config = _workflows._absolutify_node_config
    delete_workflow = _workflows.delete_workflow
    upload_file = _workflows.upload_file

    # Data catalog + preview (_data)
    register_data_ref = _data.register_data_ref
    register_output_payload = _data.register_output_payload
    get_data_record = _data.get_data_record
    describe_ref = _data.describe_ref
    _resolve_record_class = _data._resolve_record_class
    preview_data = _data.preview_data

    # Workflow execution + lineage (_runs)
    _ancestors_of = _runs._ancestors_of
    checkpoint_dir_for = _runs.checkpoint_dir_for
    _build_lineage_recorder = _runs._build_lineage_recorder
    _serialise_workflow_snapshot = _runs._serialise_workflow_snapshot
    _derive_lineage_run_status = _runs._derive_lineage_run_status
    _finalize_lineage_run = _runs._finalize_lineage_run
    start_workflow = _runs.start_workflow
    _log_workflow_task_failure = _runs._log_workflow_task_failure
    get_run = _runs.get_run


# Sorted to satisfy ruff RUF022.
__all__ = [
    "MAX_TABLE_PAGE_SIZE",
    "_TABLE_CACHE_MAX",
    "ApiRuntime",
    "DataRecord",
    "KnownProject",
    "LogBroadcaster",
    "Path",
    "WorkflowRun",
    "_downsample_matrix",
    "_get_preview_table",
    "_image_data_uri_from_matrix",
    "_infer_type_name_from_ref",
    "_load_preview_matrix",
    "_now_iso",
    "_read_preview_table_from_disk",
    "_rmtree_force",
    "_safe_parent_dir",
    "_slugify",
    "_table_cache",
    "_table_cache_lock",
    "_trim_table_cache_locked",
    "logger",
]
