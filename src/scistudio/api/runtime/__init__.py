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
import threading
import time
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from scistudio.api.file_contracts import FILE_ENTITY_CLASS
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.registry import TypeRegistry
from scistudio.engine.checkpoint import CheckpointManager
from scistudio.engine.events import EventBus
from scistudio.engine.resources import ResourceManager
from scistudio.engine.runners.local import LocalRunner
from scistudio.engine.runners.process_handle import ProcessRegistry
from scistudio.engine.scheduler import DAGScheduler
from scistudio.utils.event_logger import install_event_logger

from . import _data, _projects, _runs, _workflows
from ._helpers import _now_iso, _rmtree_force, _safe_parent_dir, _slugify

# ADR-048 / #1598: the DataFrame table cache and the raster preview pipeline
# moved down into ``scistudio.previewers`` (``_table_cache`` / ``_raster``) so the
# previewer subsystem no longer imports up into the API layer. Only the
# API-specific ``_infer_type_name_from_ref`` remains here.
from ._preview_image import _infer_type_name_from_ref

logger = logging.getLogger("scistudio.api.runtime")
WORKFLOW_ENTITY_CLASS = "workflow"
_FIRST_PARTY_WRITE_SUPPRESSION_SECONDS = 2.0


def _env_int(name: str, default: int) -> int:
    """Read a positive-integer override from the environment, else *default*."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r is not an integer; using default %d", name, raw, default)
        return default
    if value <= 0:
        logger.warning("%s=%d must be positive; using default %d", name, value, default)
        return default
    return value


# #1551 / DSN-12: the per-session ``data_catalog`` and ``workflow_runs`` registries
# previously grew unboundedly — ``data_catalog`` accumulates one entry per block
# output for the lifetime of the process and ``workflow_runs`` retains a finished
# run per workflow id forever. Both are now bounded with LRU eviction so a long
# session does not leak. Caps are generous (a real session touches far fewer
# distinct previews / workflows) and overridable via the environment for power
# users with very large projects.
_DATA_CATALOG_MAX = _env_int("SCISTUDIO_DATA_CATALOG_MAX", 4096)
_WORKFLOW_RUNS_MAX = _env_int("SCISTUDIO_WORKFLOW_RUNS_MAX", 256)

_K = TypeVar("_K")
_V = TypeVar("_V")


class _BoundedRegistry(dict[_K, _V]):
    """LRU-bounded ``dict`` subclass with optional eviction guarding.

    A drop-in ``dict`` (it **subclasses** ``dict`` so ``isinstance(x, dict)``
    stays ``True`` for every existing consumer — ``api/ws.py``, the MCP tool
    layer, ``api/app.py`` — without touching those modules). It caps the number
    of retained entries at *max_entries*; when an insertion would exceed the
    cap, the least-recently-used entries are evicted oldest-first. ``dict``
    preserves insertion order (Python 3.7+), and recency is maintained by
    re-inserting touched keys.

    ``evictable`` is an optional predicate ``(key, value) -> bool``. An entry
    for which it returns ``False`` is skipped during eviction and kept — this
    is how ``workflow_runs`` avoids dropping a still-live run (whose asyncio
    task would otherwise be orphaned). If every over-cap entry is unevictable
    the map is allowed to exceed the cap rather than evicting a live entry; a
    warning is logged so the condition is visible.

    Recency note: ``__setitem__`` (write) refreshes recency. ``__getitem__``
    deliberately does *not* reorder — reordering on read would mutate the dict
    during a ``for x in reg.values()`` loop (the lifespan shutdown does exactly
    this), raising ``RuntimeError: dict mutated during iteration``. Write-order
    LRU is sufficient for the leak fix in #1551.
    """

    def __init__(
        self,
        max_entries: int,
        *,
        evictable: Callable[[_K, _V], bool] | None = None,
        on_evict: Callable[[_K, _V], None] | None = None,
    ) -> None:
        super().__init__()
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._max = int(max_entries)
        self._evictable = evictable
        self._on_evict = on_evict

    def __setitem__(self, key: _K, value: _V) -> None:
        if key in self:
            # Refresh recency: delete + reinsert moves the key to the end.
            super().__delitem__(key)
        super().__setitem__(key, value)
        self._evict_if_needed()

    def _evict_if_needed(self) -> None:
        if len(self) <= self._max:
            return
        # Walk oldest-first, evicting evictable entries until back under cap.
        for key in list(self.keys()):
            if len(self) <= self._max:
                break
            value = self[key]
            if self._evictable is not None and not self._evictable(key, value):
                continue
            super().__delitem__(key)
            if self._on_evict is not None:
                try:
                    self._on_evict(key, value)
                except Exception:
                    logger.debug("registry on_evict callback failed for %r", key, exc_info=True)
        overflow = len(self) - self._max
        if overflow > 0:
            # Every remaining over-cap entry was unevictable (e.g. all runs
            # still live). Keep them — orphaning a live run is worse than a
            # temporary overflow — but surface the condition.
            logger.warning(
                "_BoundedRegistry: %d entries over cap %d are unevictable; retaining",
                overflow,
                self._max,
            )


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


def _run_is_evictable(_key: str, run: WorkflowRun) -> bool:
    """#1551: only finished runs may be LRU-evicted from ``workflow_runs``.

    Evicting a live run would orphan its ``asyncio.Task`` and scheduler (they
    share the event bus / resource manager / lineage store), so an in-flight
    run is pinned in the registry until its task completes. A completed run has
    nothing live to lose — its lineage row is finalized by the task's
    done-callback (see ``_runs._finalize_lineage_run``).
    """
    return run.task.done()


@dataclass(frozen=True)
class FirstPartyEntityWrite:
    """Exact file signature for a first-party entity write."""

    version: int
    seen_at: float
    path: str | None = None
    mtime_ns: int | None = None
    size: int | None = None
    exists: bool | None = None
    kind: str | None = None


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
        # #1551 / DSN-12: both registries are LRU-bounded so a long session does
        # not leak. ``data_catalog`` evicts the least-recently-previewed record;
        # ``workflow_runs`` only evicts finished runs (a live run's asyncio task
        # would be orphaned if dropped — see ``_run_is_evictable``). They are
        # exposed via the ``data_catalog`` / ``workflow_runs`` properties below
        # so that the project-lifecycle resets in ``_projects`` (which assign a
        # plain ``{}``) keep the LRU bound instead of silently reverting to an
        # unbounded dict.
        self._data_catalog: _BoundedRegistry[str, DataRecord] = _BoundedRegistry(_DATA_CATALOG_MAX)
        self._workflow_runs: _BoundedRegistry[str, WorkflowRun] = _BoundedRegistry(
            _WORKFLOW_RUNS_MAX,
            evictable=_run_is_evictable,
        )
        # ADR-034: the MCP server's TCP/socket port is published into the
        # active project's ``.scistudio/`` so the per-project ``mcp-bridge``
        # subprocess can discover it.
        self._mcp_port: int | None = None
        # ADR-040 Addendum 5 / #1488: the workflow id the GUI is currently
        # editing. Frontend POSTs to ``/api/ai/active-context`` on every
        # change; the value is persisted to
        # ``<project>/.scistudio/active_workflow.json`` so it survives
        # backend restart, and surfaced to the chat agent via the
        # ``get_active_workflow_context`` MCP tool.
        self.active_workflow_id: str | None = None
        self._entity_versions: dict[tuple[str, str], int] = {}
        self._entity_disk_versions: dict[tuple[str, str], int] = {}
        self._first_party_entity_writes: dict[tuple[str, str], FirstPartyEntityWrite] = {}
        self._version_lock = threading.RLock()
        # ADR-039 §5.2: the in-memory ``_workflow_revisions`` counter and its
        # ``If-Match`` enforcement path were removed in D39-2.1. Git commit SHA
        # plus the working-tree dirty state (D39-2.2b) replace the optimistic-
        # concurrency model.

        self.event_bus = EventBus()
        # ADR-045: watcher reads runtime via getattr(event_bus, "runtime", None).
        # The EventBus class lives in a protected path (engine.events) so we set
        # the back-reference dynamically rather than adding a typed attribute,
        # which would require a core-change label.
        self.event_bus.runtime = self  # type: ignore[attr-defined]
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

        # #827: structured stdlib-logging audit trail for every engine
        # event. Independent of ``_bind_event_logging`` below — that
        # callback fans out to the WS LogBroadcaster (live frontend
        # Logs panel) and only subscribes to seven of the ~18 emitted
        # event types. The event_logger subscriber observes every
        # event type and writes one record per event on the
        # ``scistudio.events`` logger.
        install_event_logger(self.event_bus)

        self._load_known_projects()
        self._configure_static_registries()
        self._bind_event_logging()

    # ------------------------------------------------------------------
    # #1551 / DSN-12: bounded session registries.
    #
    # Exposed as properties so the existing ``self.data_catalog = {}`` /
    # ``self.workflow_runs = {}`` resets in ``_projects`` re-seed a *bounded*
    # registry rather than swapping in an unbounded dict. The setter accepts
    # any mapping (the common case is an empty dict on project switch) and
    # rebuilds the LRU-bounded container, preserving the cap + eviction policy
    # across project lifecycle transitions.
    # ------------------------------------------------------------------
    @property
    def data_catalog(self) -> MutableMapping[str, DataRecord]:
        return self._data_catalog

    @data_catalog.setter
    def data_catalog(self, value: MutableMapping[str, DataRecord]) -> None:
        registry: _BoundedRegistry[str, DataRecord] = _BoundedRegistry(_DATA_CATALOG_MAX)
        for key, record in value.items():
            registry[key] = record
        self._data_catalog = registry

    @property
    def workflow_runs(self) -> MutableMapping[str, WorkflowRun]:
        return self._workflow_runs

    @workflow_runs.setter
    def workflow_runs(self, value: MutableMapping[str, WorkflowRun]) -> None:
        registry: _BoundedRegistry[str, WorkflowRun] = _BoundedRegistry(
            _WORKFLOW_RUNS_MAX,
            evictable=_run_is_evictable,
        )
        for key, run in value.items():
            registry[key] = run
        self._workflow_runs = registry

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
    # ADR-045 version-state compatibility surface.
    # ------------------------------------------------------------------
    def reset_version_state_for_project(self, project_dir: Path) -> None:
        """Initialize ADR-045 version state from the active project's disk state."""
        workflows_dir = project_dir / "workflows"
        seeded: dict[tuple[str, str], int] = {}
        disk_versions: dict[tuple[str, str], int] = {}
        if workflows_dir.is_dir():
            for pattern in ("*.yaml", "*.yml"):
                for path in workflows_dir.glob(pattern):
                    try:
                        disk_version = int(path.stat().st_mtime_ns)
                    except OSError:
                        continue
                    key = (WORKFLOW_ENTITY_CLASS, path.stem)
                    seeded[key] = max(seeded.get(key, 0), 1)
                    disk_versions[key] = max(disk_versions.get(key, 0), disk_version)
        with self._version_lock:
            self._entity_versions = seeded
            self._entity_disk_versions = disk_versions
            self._first_party_entity_writes.clear()

    def current_entity_version(self, entity_class: str, entity_id: str, *, path: Path | None = None) -> int:
        key = self._version_key(entity_class, entity_id)
        with self._version_lock:
            return self._entity_version_locked(key, path=path, bump=False, disk=False)

    def bump_entity_version(self, entity_class: str, entity_id: str, *, path: Path | None = None) -> int:
        key = self._version_key(entity_class, entity_id)
        with self._version_lock:
            return self._entity_version_locked(key, path=path, bump=True, disk=False)

    def current_entity_disk_version(self, entity_class: str, entity_id: str, *, path: Path | None = None) -> int:
        key = self._version_key(entity_class, entity_id)
        with self._version_lock:
            return self._entity_version_locked(key, path=path, bump=False, disk=True)

    def _entity_version_locked(
        self,
        key: tuple[str, str],
        *,
        path: Path | None,
        bump: bool,
        disk: bool,
    ) -> int:
        target = self._entity_disk_versions if disk else self._entity_versions
        current = target.get(key)
        if current is None:
            current = self._disk_version_from_path(path) if disk else self._initial_version_from_path(path)
        elif bump:
            current = int(current) + 1
        target[key] = current
        if not disk and path is not None and (bump or key not in self._entity_disk_versions):
            self._entity_disk_versions[key] = self._disk_version_from_path(path)
        return current

    def current_workflow_version(self, workflow_id: str) -> int:
        return self.current_entity_version(
            WORKFLOW_ENTITY_CLASS,
            workflow_id,
            path=self.workflow_path(workflow_id),
        )

    def bump_workflow_version(self, workflow_id: str) -> int:
        return self.bump_entity_version(
            WORKFLOW_ENTITY_CLASS,
            workflow_id,
            path=self.workflow_path(workflow_id),
        )

    def _first_party_write_signature(self, path: Path) -> tuple[str, int | None, int | None, bool]:
        normalized = str(path.resolve())
        try:
            stat = path.stat()
        except OSError:
            return normalized, None, None, False
        return normalized, int(stat.st_mtime_ns), int(stat.st_size), True

    def _signature_for_entity_write(
        self, path: Path | None, *, pending: bool
    ) -> tuple[str | None, int | None, int | None, bool | None]:
        if path is None:
            return None, None, None, None
        if pending:
            return str(path.resolve()), None, None, None
        return self._first_party_write_signature(path)

    def mark_entity_first_party_write(
        self,
        entity_class: str,
        entity_id: str,
        version: int,
        *,
        path: Path | None = None,
        kind: str | None = None,
        pending: bool = False,
    ) -> None:
        """Record an exact write-site signature so watcher fallback can suppress echoes."""
        key = self._version_key(entity_class, entity_id)
        path_key, mtime_ns, size, exists = self._signature_for_entity_write(path, pending=pending)
        with self._version_lock:
            self._first_party_entity_writes[key] = FirstPartyEntityWrite(
                version=int(version),
                seen_at=time.monotonic(),
                path=path_key,
                mtime_ns=mtime_ns,
                size=size,
                exists=exists,
                kind=kind,
            )
            if mtime_ns is not None:
                self._entity_disk_versions[key] = mtime_ns

    def mark_workflow_first_party_write(
        self,
        workflow_id: str,
        version: int,
        *,
        path: Path | None = None,
        kind: str | None = None,
    ) -> None:
        self.mark_entity_first_party_write(WORKFLOW_ENTITY_CLASS, workflow_id, version, path=path, kind=kind)

    def _active_first_party_entity_write(
        self, key: tuple[str, str], version: int | None
    ) -> FirstPartyEntityWrite | None:
        entry = self._first_party_entity_writes.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry.seen_at > _FIRST_PARTY_WRITE_SUPPRESSION_SECONDS:
            self._first_party_entity_writes.pop(key, None)
            return None
        if version is not None and int(version) != entry.version:
            return None
        return entry

    def _entity_write_path_matches(self, entry: FirstPartyEntityWrite, path: Path, kind: str | None) -> bool:
        path_key, mtime_ns, size, exists = self._first_party_write_signature(path)
        if entry.path != path_key:
            return False
        if entry.exists is None:
            return True
        if entry.exists is False:
            return exists is False and entry.kind == "deleted" and kind == "deleted"
        return exists is True and entry.mtime_ns == mtime_ns and entry.size == size

    def is_recent_first_party_entity_write(
        self,
        entity_class: str,
        entity_id: str,
        *,
        version: int | None = None,
        path: Path | None = None,
        kind: str | None = None,
    ) -> bool:
        key = (str(entity_class), str(entity_id))
        with self._version_lock:
            entry = self._active_first_party_entity_write(key, version)
            if path is None:
                return entry is not None and version is not None
            return entry is not None and self._entity_write_path_matches(entry, path, kind)

    def is_recent_workflow_first_party_write(
        self,
        workflow_id: str,
        *,
        version: int | None = None,
        path: Path | None = None,
        kind: str | None = None,
    ) -> bool:
        return self.is_recent_first_party_entity_write(
            WORKFLOW_ENTITY_CLASS,
            workflow_id,
            version=version,
            path=path,
            kind=kind,
        )

    def versioned_change_payload(
        self,
        *,
        entity_class: str,
        entity_id: str,
        version: int,
        source: str,
        source_id: str | None,
        kind: str,
        timestamp: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Build the shared ADR-045 event/response contract payload."""
        payload: dict[str, Any] = {
            "entity_class": entity_class,
            "entity_id": entity_id,
            "version": int(version),
            "source": source,
            "source_id": source_id,
            "kind": kind,
            "timestamp": timestamp or _now_iso(),
        }
        payload.update(extra)
        return payload

    def _version_key(self, entity_class: str, entity_id: str) -> tuple[str, str]:
        if not entity_class:
            raise ValueError("entity_class is required")
        if not entity_id:
            raise ValueError("entity_id is required")
        return (entity_class, entity_id)

    @staticmethod
    def _initial_version_from_path(path: Path | None) -> int:
        if path is None:
            return 0
        try:
            return 1 if path.exists() else 0
        except OSError:
            return 0

    @staticmethod
    def _disk_version_from_path(path: Path | None) -> int:
        if path is None:
            return 0
        try:
            return int(path.stat().st_mtime_ns)
        except OSError:
            return 0

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
    # ADR-040 Addendum 5 / #1488: persistence helpers for ``active_workflow_id``.
    _load_active_workflow_id_from_disk = _projects._load_active_workflow_id_from_disk
    _publish_active_workflow_id = _projects._publish_active_workflow_id
    set_active_workflow_id = _projects.set_active_workflow_id
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
    _upload_destination = _workflows._upload_destination
    stage_upload_file = _workflows.stage_upload_file
    discard_staged_upload = _workflows.discard_staged_upload
    finish_staged_upload = _workflows.finish_staged_upload
    upload_file = _workflows.upload_file

    # Data catalog + preview (_data)
    register_data_ref = _data.register_data_ref
    register_output_payload = _data.register_output_payload
    get_data_record = _data.get_data_record
    describe_ref = _data.describe_ref
    _resolve_record_class = _data._resolve_record_class
    preview_data = _data.preview_data
    # ADR-048 SPEC 1: previewer subsystem accessors.
    get_preview_service = _data.get_preview_service
    refresh_preview_service = _data.refresh_preview_service
    enrich_preview_query = _data.enrich_preview_query
    resolve_session_target = _data.resolve_session_target
    _build_preview_target = _data._build_preview_target

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
    "FILE_ENTITY_CLASS",
    "WORKFLOW_ENTITY_CLASS",
    "ApiRuntime",
    "DataRecord",
    "FirstPartyEntityWrite",
    "KnownProject",
    "LogBroadcaster",
    "Path",
    "WorkflowRun",
    "_infer_type_name_from_ref",
    "_now_iso",
    "_rmtree_force",
    "_safe_parent_dir",
    "_slugify",
    "logger",
]
