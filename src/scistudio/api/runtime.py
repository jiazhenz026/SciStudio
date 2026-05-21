"""Shared runtime services for the FastAPI layer."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shutil
import threading
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

import pyarrow.parquet as pq
import yaml

from scistudio.blocks.registry import BlockRegistry
from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.registry import TypeRegistry
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text
from scistudio.engine.checkpoint import CheckpointManager
from scistudio.engine.events import EventBus
from scistudio.engine.resources import ResourceManager
from scistudio.engine.runners.local import LocalRunner
from scistudio.engine.runners.process_handle import ProcessRegistry
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition
from scistudio.workflow.serializer import absolutify_paths, load_yaml, relativify_paths, save_yaml

logger = logging.getLogger(__name__)

# DataFrame preview paging — cap the per-request payload to keep the response
# under a few hundred KB even with wide tables.
MAX_TABLE_PAGE_SIZE = 200

# DataFrame preview cache — keyed by (path, mtime_ns, sort_by, sort_dir).
# Empty sort_by means the unsorted base table; sorted variants reuse the
# cached base on miss to avoid re-parsing the source file.
#
# Wide-table sorts (e.g. 5200 rows x 40 cols) cost ~200 ms per request when
# we re-read + re-sort on every page click. The cache turns that into a
# one-time cost per (column, direction) pair; subsequent pagination of the
# same sort lands O(slice).
#
# Cap is intentionally small — large enough to cover typical
# unsorted+asc+desc trios per column but bounded by RAM.
_TABLE_CACHE_MAX = 16
_table_cache: OrderedDict[tuple[str, int, str, str], Any] = OrderedDict()
_table_cache_lock = threading.Lock()


def _trim_table_cache_locked() -> None:
    """Evict oldest entries until under the cap. Caller holds the lock."""
    while len(_table_cache) > _TABLE_CACHE_MAX:
        _table_cache.popitem(last=False)


def _read_preview_table_from_disk(path: Path) -> Any:
    """Read a csv/parquet file into a pyarrow Table — uncached."""
    if path.suffix.lower() == ".parquet":
        return pq.read_table(path)
    import pyarrow.csv as pcsv

    return pcsv.read_csv(str(path))


def _get_preview_table(path: Path, sort_by: str | None, sort_dir: str) -> Any:
    """Return a parsed (and optionally sorted) pyarrow Table for ``path``.

    Cached by (path, mtime, sort_by, sort_dir). On sort-variant cache miss
    we look up the unsorted base in the same cache to avoid re-reading the
    file, sort that, then cache the sorted variant.
    """
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        mtime = 0
    sort_key = sort_by or ""
    dir_key = sort_dir if sort_key else ""
    key = (str(path), mtime, sort_key, dir_key)

    with _table_cache_lock:
        cached = _table_cache.get(key)
        if cached is not None:
            _table_cache.move_to_end(key)
            return cached

    # Cache miss — try to reuse an already-parsed unsorted base, otherwise read disk.
    base = None
    if sort_key:
        base_key = (str(path), mtime, "", "")
        with _table_cache_lock:
            base = _table_cache.get(base_key)
            if base is not None:
                _table_cache.move_to_end(base_key)
    if base is None:
        base = _read_preview_table_from_disk(path)
        if sort_key:
            # Persist the unsorted base too so the next sort change skips IO.
            base_key = (str(path), mtime, "", "")
            with _table_cache_lock:
                _table_cache[base_key] = base
                _trim_table_cache_locked()

    if sort_key:
        order = "descending" if dir_key == "desc" else "ascending"
        table = base.sort_by([(sort_key, order)])
    else:
        table = base

    with _table_cache_lock:
        _table_cache[key] = table
        _trim_table_cache_locked()
    return table


def _rmtree_force(target: Path) -> None:
    """Remove a directory tree, retrying on Windows read-only / locked files.

    ADR-039: auto-init creates ``.git/`` with read-only object files on
    Windows. Plain ``shutil.rmtree`` cannot remove read-only files, and
    can also race with file watchers that briefly hold handles. This
    helper:

    1. Pre-walks the tree to ``chmod -R`` every file writable.
    2. Calls ``shutil.rmtree`` with an ``onerror`` that retries with
       chmod for any remaining stragglers.
    3. Does a small bounded retry loop for transient locks (file watcher
       holding a handle while we delete).
    """
    import contextlib
    import stat
    import time

    target_p = Path(target)
    if not target_p.exists():
        return

    # 1. Walk + chmod everything writable. Directories need execute (x)
    # for traversal on POSIX; files just need write to be unlinkable.
    dir_perms = stat.S_IRWXU  # 0700 — read/write/execute for owner
    file_perms = stat.S_IWRITE | stat.S_IREAD  # 0600
    for root, dirs, files in os.walk(target_p):
        with contextlib.suppress(OSError):
            os.chmod(root, dir_perms)
        for name in dirs:
            with contextlib.suppress(OSError):
                os.chmod(Path(root) / name, dir_perms)
        for name in files:
            with contextlib.suppress(OSError):
                os.chmod(Path(root) / name, file_perms)
    with contextlib.suppress(OSError):
        os.chmod(target_p, dir_perms)

    def _on_rm_error(func, path, _exc_info):  # type: ignore[no-untyped-def]
        try:
            p = Path(path)
            os.chmod(p, dir_perms if p.is_dir() else file_perms)
            func(path)
        except Exception:
            logger.debug("rmtree retry failed for %s", path, exc_info=True)

    # 2. Bounded retry loop for transient locks (e.g. sqlite WAL).
    for _ in range(5):
        try:
            shutil.rmtree(target_p, onerror=_on_rm_error)
        except Exception:
            logger.debug("rmtree raised", exc_info=True)
        if not target_p.exists():
            return
        time.sleep(0.2)
    # Last resort: best-effort one more pass after a longer wait so any
    # in-process sqlite WAL flush has time to release file handles.
    time.sleep(0.5)
    try:
        shutil.rmtree(target_p, onerror=_on_rm_error)
    except Exception:
        logger.warning("rmtree failed to remove %s", target_p, exc_info=True)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _slugify(name: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in name).strip("-")
    return slug or "project"


def _safe_parent_dir(path: str | Path | None) -> Path:
    if path is None:
        return Path.cwd()
    return Path(path).expanduser().resolve()


def _infer_type_name_from_ref(ref: StorageReference) -> str:
    # ADR-027 D2 / #407: prefer the type_chain written by the worker subprocess
    # via _serialise_one().  The rightmost (most specific) entry is the
    # canonical type name.  Fall through to the extension heuristic only when
    # metadata is absent (e.g. file uploads that have no type_chain yet).
    if ref.metadata:
        type_chain = ref.metadata.get("type_chain")
        if type_chain and isinstance(type_chain, list) and type_chain:
            return str(type_chain[-1])

    fmt = (ref.format or "").lower()
    if fmt in {"csv", "parquet"}:
        return DataFrame.__name__
    if fmt in {"txt", "json", "yaml", "yml", "md"}:
        return Text.__name__
    # T-006 / ADR-027 D2: ``Image`` lives in the imaging plugin, not
    # core. Imaging payloads are modelled as generic ``Array`` with
    # ``axes=["y", "x"]`` here; the frontend preview hook still handles
    # the "image" kind via the TIFF/PNG data-URI path below.
    if fmt in {"png", "jpg", "jpeg", "tif", "tiff"}:
        return Array.__name__
    if fmt == "zarr":
        return Array.__name__
    return Artifact.__name__


def _image_data_uri_from_matrix(values: list[list[float]]) -> str:
    """Encode a 2D float matrix as a grayscale PNG data URI.

    Uses stdlib struct + zlib to produce a minimal valid PNG.
    No external dependencies.  Universal browser support.
    """
    import struct
    import zlib

    height = len(values)
    width = len(values[0]) if values and values[0] else 0
    if width == 0 or height == 0:
        return ""
    max_val = max((v for row in values for v in row), default=1.0) or 1.0

    # Build raw scanlines: each row has a filter byte (0 = None) followed by pixel bytes.
    raw = b""
    for row in values:
        raw += b"\x00"  # PNG filter: None
        raw += bytes(max(0, min(255, int(v / max_val * 255))) for v in row)

    def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        body = chunk_type + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    # IHDR: width, height, bit-depth=8, color-type=0 (grayscale)
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", ihdr_data)
    png += _png_chunk(b"IDAT", zlib.compress(raw))
    png += _png_chunk(b"IEND", b"")

    return f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"


def _load_preview_matrix(ref: StorageReference) -> Any:
    """Load a raster payload for preview generation."""
    path = Path(ref.path)
    suffix = path.suffix.lower()

    if suffix in {".tif", ".tiff"}:
        import tifffile

        return tifffile.imread(str(path))

    if suffix == ".zarr":
        import zarr

        node: Any = zarr.open(str(path), mode="r")
        if isinstance(node, zarr.Array):
            return node[...]
        if "data" in node:
            data_array: Any = node["data"]
            return data_array[...]
        raise ValueError(f"Zarr preview store at {path} has no top-level array or 'data' dataset")

    raise ValueError(f"Unsupported raster preview format for {path}")


def _downsample_matrix(matrix: Any, max_dim: int = 256) -> Any:
    """Downsample a 2-D matrix to at most *max_dim* on the longest side.

    Uses nearest-neighbour sampling via ``numpy.linspace`` indices so the
    full spatial extent of the image is preserved in the thumbnail.
    """
    import numpy as np

    h, w = int(matrix.shape[0]), int(matrix.shape[1])
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        new_h, new_w = max(1, int(h * scale)), max(1, int(w * scale))
        row_idx = np.linspace(0, h - 1, new_h, dtype=int)
        col_idx = np.linspace(0, w - 1, new_w, dtype=int)
        thumbnail_arr = matrix[np.ix_(row_idx, col_idx)]
    else:
        thumbnail_arr = matrix
    return thumbnail_arr.tolist()


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
    # e.g. ["DataObject", "Array", "Image"].  Used by preview_data() to resolve
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
    """Shared mutable state owned by the FastAPI application."""

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
        # subprocess can discover it. Held here so ``open_project`` can
        # republish on project switch (otherwise the bridge keeps looking
        # in the previous project and falls back to standalone mode,
        # which has no ApiRuntime and breaks ``run_workflow``).
        self._mcp_port: int | None = None
        # ADR-039 §5.2: the in-memory ``_workflow_revisions`` counter and its
        # ``If-Match`` enforcement path were removed in D39-2.1. Git commit SHA
        # plus the working-tree dirty state (D39-2.2b) replace the optimistic-
        # concurrency model; cross-tab cache invalidation rides on the existing
        # ``workflow.changed`` event flow (now without a ``revision`` field).

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

    def _load_known_projects(self) -> None:
        if not self.known_projects_path.exists():
            self.known_projects = {}
            return
        raw = json.loads(self.known_projects_path.read_text(encoding="utf-8"))
        self.known_projects = {
            entry["id"]: KnownProject(**entry)
            for entry in raw.get("projects", [])
            if isinstance(entry, dict) and entry.get("id") and entry.get("path")
        }

    def _save_known_projects(self) -> None:
        payload = {"projects": [asdict(entry) for entry in self.known_projects.values()]}
        self.known_projects_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def refresh_block_registry(self) -> None:
        registry = BlockRegistry()
        if self.active_project is not None:
            registry.add_scan_dir(Path(self.active_project.path) / "blocks")
            registry.add_scan_dir(Path.home() / ".scistudio" / "blocks")
        registry.scan(include_monorepo=os.environ.get("SCISTUDIO_DEV") == "1")
        self.block_registry = registry

    def refresh_type_registry(self) -> None:
        """Re-scan the TypeRegistry with the current active project's types dir.

        Issue #1332 / ARCHITECTURE.md §10 + §10.5: mirrors
        :meth:`refresh_block_registry` so a project switch picks up
        ``<project>/types`` drop-in :class:`DataObject` subclasses and the
        user-wide ``~/.scistudio/types`` dir. Always rebuilds from scratch
        so a switch from project A to project B does not leak project A's
        types into project B.
        """
        registry = TypeRegistry()
        if self.active_project is not None:
            registry.add_scan_dir(Path(self.active_project.path) / "types")
        registry.add_scan_dir(Path.home() / ".scistudio" / "types")
        registry.scan_all(include_monorepo=os.environ.get("SCISTUDIO_DEV") == "1")
        self.type_registry = registry

    def _init_lineage_store(self, project_path: Path) -> None:
        """Open the unified ADR-038 lineage store for the active project.

        The DB lives at ``<project>/.scistudio/lineage.db``. Schema creation is
        idempotent so first-time opens auto-bootstrap. Best-effort: a failure
        is logged and the store is set to ``None``, which makes the lineage
        recorder a no-op for this project.
        """
        # Close any previously open store before switching projects to avoid
        # leaking a file handle on the prior project's DB.
        prior = getattr(self, "lineage_store", None)
        if prior is not None:
            try:
                prior.close()
            except Exception:
                logger.debug("ApiRuntime: closing prior LineageStore raised", exc_info=True)
            self.lineage_store = None
        try:
            from scistudio.core.lineage.store import LineageStore

            scistudio_dir = project_path / ".scistudio"
            scistudio_dir.mkdir(parents=True, exist_ok=True)
            db_path = scistudio_dir / "lineage.db"
            self.lineage_store = LineageStore(db_path)
            logger.info("ADR-038: LineageStore opened at %s", db_path)
        except Exception:
            logger.warning("ADR-038: Failed to initialize LineageStore (non-fatal)", exc_info=True)
            self.lineage_store = None
        # ADR-038 §6 Phase 2 (D38-2.3): publish the active store for the
        # deprecation-shim ``MetadataStore`` so legacy read-only callers
        # (``ai/agent/mcp/tools_*``) delegate through to the unified
        # ``data_objects`` table. None when init failed.
        try:
            from scistudio.core.metadata_store import _set_active_lineage_store

            _set_active_lineage_store(self.lineage_store)
        except Exception:
            logger.debug(
                "ADR-038: failed to publish lineage store to shim (non-fatal)",
                exc_info=True,
            )

    def _init_metadata_store(self, project_path: Path) -> None:
        """Install the deprecation-shim :class:`MetadataStore` (ADR-038 §6).

        ADR-032's ``metadata.db`` was superseded by ADR-038's unified
        ``lineage.db`` in Phase D38-2.3. This method:

        * Detects an existing legacy ``<project>/metadata.db`` and logs
          an ``INFO`` line — per ADR-038 §6 Phase 2 + the user direction
          recorded 2026-05-15 the project is pre-release and no historical
          data migration is performed. The file is left in place untouched
          so a forensic user can still inspect it manually.
        * Sets the module-level :class:`MetadataStore` shim singleton so
          out-of-scope read-only callers (``ai/agent/mcp/tools_*``) keep
          working against the unified store. Writes through the shim are
          no-ops; the authoritative writer is the :class:`LineageRecorder`
          wired by :meth:`start_workflow`.

        Non-fatal: shim construction never raises in practice but we keep
        the defensive ``try`` block for symmetry with the prior
        implementation. On failure we explicitly clear the singleton so a
        stale shim from a previous project does not leak.
        """
        try:
            from scistudio.core.metadata_store import (
                MetadataStore,
                get_metadata_store,
                set_metadata_store,
            )

            # Close any previously-opened store so its sqlite handle is
            # released before we open a new one. Otherwise switching
            # projects accumulates dangling connections that prevent
            # rmtree on Windows (test cleanup + delete_project both fail).
            previous = get_metadata_store()
            if previous is not None:
                try:
                    previous.close()
                except Exception:
                    logger.debug("MetadataStore.close on switch raised", exc_info=True)

            legacy_db = project_path / "metadata.db"
            if legacy_db.exists():
                logger.info(
                    "ADR-038: legacy metadata.db detected at %s; superseded by lineage.db (ignored, file retained)",
                    legacy_db,
                )

            # The shim ignores ``db_path`` — pass it for repr clarity only.
            set_metadata_store(MetadataStore(legacy_db))
        except Exception:
            logger.warning(
                "ADR-038: Failed to install MetadataStore deprecation shim (non-fatal)",
                exc_info=True,
            )
            from scistudio.core.metadata_store import set_metadata_store

            set_metadata_store(None)

    def create_project(self, name: str, description: str = "", parent_path: str | None = None) -> KnownProject:
        parent_dir = _safe_parent_dir(parent_path)
        project_path = parent_dir / _slugify(name)
        if project_path.exists():
            raise FileExistsError(f"Project directory already exists: {project_path}")

        # ADR-038 §3.5 / §5.2: run history lives at ``.scistudio/lineage.db``;
        # pause/resume checkpoints live at ``.scistudio/pause/<workflow_id>/``
        # (Phase D38-2.3). The legacy top-level ``lineage/`` and
        # ``checkpoints/`` dirs are retired — :meth:`checkpoint_dir_for`
        # now returns the ``.scistudio/pause/`` location.
        for subdir in (
            "workflows",
            "data/raw",
            "data/zarr",
            "data/parquet",
            "data/artifacts",
            "data/exchange",
            "blocks",
            "types",
            ".scistudio",
            "logs",
        ):
            (project_path / subdir).mkdir(parents=True, exist_ok=True)

        project_id = f"project-{uuid4().hex[:8]}"
        project = KnownProject(
            id=project_id,
            name=name,
            path=str(project_path),
            description=description,
            last_opened=_now_iso(),
        )
        metadata = {
            "project": {
                "id": project.id,
                "name": project.name,
                "description": description,
                "version": "0.1.0",
                "created": _now_iso(),
            }
        }
        (project_path / "project.yaml").write_text(
            yaml.safe_dump(metadata, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

        # Issue #879: scaffold an empty ``workflows/main.yaml`` so the
        # default ``main`` workflow tab has a real on-disk file from the
        # moment the project is created. Without this, the in-memory
        # canvas tab is divorced from the filesystem until the user
        # presses Ctrl+S — breaking View source (#878), file-watcher
        # rehydration, and any agent / MCP introspection of "what's in
        # this project". Use the canonical serializer so the YAML schema
        # matches what ``load_yaml`` expects.
        try:
            save_yaml(WorkflowDefinition(id="main"), project_path / "workflows" / "main.yaml")
        except Exception:
            # Best-effort: a scaffold-write failure must not block project
            # creation. The user can still Ctrl+S manually to repair.
            logger.warning("Failed to scaffold workflows/main.yaml for project %s", project.id, exc_info=True)

        self.known_projects[project.id] = project
        self._save_known_projects()
        # ------------------------------------------------------------------
        # ADR-039 §3.2 auto-init hook (D39-2.2a skeleton)
        # ------------------------------------------------------------------
        # On project creation, initialize a git repository so source files
        # (workflows/*.yaml, blocks/*.py, notes/*.md, project.yaml,
        # README.md) are version-controlled from day one. The initial
        # commit captures everything that already exists.
        #
        # IMPLEMENTATION FOR D39-2.2b:
        # ----------------------------
        # 1. Import lazily to avoid circular imports during module load:
        #        from scistudio.core.versioning.git_engine import GitEngine
        #        from scistudio.core.versioning.gitignore_template import (
        #            write_default_gitignore,
        #        )
        # 2. Construct engine: ``engine = GitEngine(project_path)``.
        # 3. Guard with ``if not engine.is_repository(project_path):``
        #    (we just created the directory; should always pass — but
        #    the guard makes the call idempotent for tests).
        # 4. ``engine.init_repository(project_path)`` — performs git init
        #    + writes .gitignore + initial commit per §3.2.
        # 5. Best-effort: log at INFO; if init fails, log WARNING and
        #    proceed. Project creation must succeed even if git init
        #    fails (degraded mode per §3.9 line 384-388).
        #
        # ADR-039 §3.2 auto-init (D39-2.2b): degraded mode on failure so
        # that project creation never aborts because git is unavailable
        # (per §3.9).
        try:
            from scistudio.core.versioning.git_engine import GitEngine

            engine = GitEngine(project_path)
            if not engine.is_repository(project_path):
                engine.init_repository(project_path)
                logger.info("ADR-039: auto-initialized git repo at %s", project_path)
        except Exception:
            logger.warning(
                "ADR-039: auto-init failed at %s (degraded mode)",
                project_path,
                exc_info=True,
            )
        # ------------------------------------------------------------------
        # ADR-040 §3.8 prod-env agent provisioning wiring (create_project).
        # ------------------------------------------------------------------
        # Runs AFTER git init so the initial commit is clean of provisioned
        # files (they land in a second commit on the user's first checkpoint).
        # Failures are non-fatal per ADR §7; the project still opens.
        try:
            from scistudio.agent_provisioning import install_project_agent_assets

            provision_result = install_project_agent_assets(project_path, force=False)
            if provision_result.failed:
                logger.warning(
                    "ADR-040: agent provisioning partial failure at %s: %s",
                    project_path,
                    provision_result.failed,
                )
        except Exception:  # pragma: no cover — defensive
            logger.warning(
                "ADR-040: agent provisioning failed at %s (non-fatal)",
                project_path,
                exc_info=True,
            )
        self.open_project(project.id)
        return project

    def list_projects(self) -> list[KnownProject]:
        self._load_known_projects()
        # Prune entries whose project directory no longer exists on disk
        # ADR-039: ``Path.is_dir()`` alone can yield False positives on
        # Windows when sqlite WAL files linger after a directory was
        # deleted externally. Treat a project as stale if either the
        # directory is missing OR its ``project.yaml`` is gone.
        stale_ids = [
            pid
            for pid, entry in self.known_projects.items()
            if not Path(entry.path).is_dir() or not (Path(entry.path) / "project.yaml").is_file()
        ]
        if stale_ids:
            for pid in stale_ids:
                self.known_projects.pop(pid, None)
            self._save_known_projects()
        # Sort by last_opened descending (most recently opened first)
        return sorted(
            self.known_projects.values(),
            key=lambda item: item.last_opened or "",
            reverse=True,
        )

    def _load_project_from_path(self, project_path: Path) -> KnownProject:
        project_file = project_path / "project.yaml"
        if not project_file.exists():
            raise FileNotFoundError(f"Missing project.yaml in {project_path}")
        raw = yaml.safe_load(project_file.read_text(encoding="utf-8")) or {}
        project_data = raw.get("project", {}) if isinstance(raw, dict) else {}
        project_id = project_data.get("id") or f"project-{uuid4().hex[:8]}"
        entry = KnownProject(
            id=project_id,
            name=project_data.get("name") or project_path.name,
            path=str(project_path),
            description=project_data.get("description", ""),
            last_opened=_now_iso(),
        )
        self.known_projects[entry.id] = entry
        self._save_known_projects()
        return entry

    def open_project(self, project_id_or_path: str) -> KnownProject:
        candidate = self.known_projects.get(project_id_or_path)
        if candidate is None:
            decoded = Path(unquote(project_id_or_path)).expanduser()
            resolved = decoded.resolve()
            if not (resolved / "project.yaml").is_file():
                raise FileNotFoundError(f"Not a valid SciStudio project (no project.yaml): {resolved}")
            candidate = self._load_project_from_path(resolved)
        candidate.last_opened = _now_iso()
        self.known_projects[candidate.id] = candidate
        self._save_known_projects()
        self.active_project = candidate
        self.data_catalog = {}
        # Issue #1332 / ARCHITECTURE.md §10 + §10.5: rescan TypeRegistry so
        # the project's ``types/`` drop-in DataObject subclasses register,
        # mirroring the block-registry refresh below.
        self.refresh_type_registry()
        self.refresh_block_registry()
        self._init_metadata_store(Path(candidate.path))
        # ADR-038 §3.1: open the unified lineage store alongside the legacy
        # metadata.db (Phase D38-2.3 collapsed the latter into a shim).
        # Best-effort: if this fails the project still opens; degraded
        # mode leaves ``self.lineage_store = None`` and the Lineage tab
        # surfaces an empty state.
        self._init_lineage_store(Path(candidate.path))
        # ------------------------------------------------------------------
        # ADR-039 §3.2 re-init hook
        # ------------------------------------------------------------------
        # If a project was created outside SciStudio (or .git/ was deleted
        # by the user) AND no opt-out marker is present, auto-init now.
        # Best-effort: catch BundledGitMissing / GitError, log WARNING,
        # proceed. The project must still open if git is unavailable.
        # Failures here are INDEPENDENT of the lineage init above —
        # either subsystem may be in degraded mode without affecting
        # the other (see test_open_project_degraded_modes.py).
        try:
            candidate_path = Path(candidate.path)
            no_git_marker = candidate_path / ".scistudio" / "no_git"
            if not no_git_marker.exists():
                from scistudio.core.versioning.git_engine import GitEngine

                engine = GitEngine(candidate_path)
                if not engine.is_repository(candidate_path):
                    engine.init_repository(candidate_path)
                    logger.info("ADR-039: auto-initialized git repo at %s", candidate_path)
        except Exception:
            logger.warning(
                "ADR-039: re-init failed at %s (degraded mode)",
                candidate.path,
                exc_info=True,
            )
        # ------------------------------------------------------------------
        # ADR-040 §3.8 idempotent top-up wiring (open_project).
        # ------------------------------------------------------------------
        # Same provisioning entry, called with force=False so existing
        # user-edited files (CLAUDE.md tweaks, hook customizations) are
        # preserved on every project open. This is how alpha-stage
        # projects created before ADR-040 lands acquire the new assets.
        try:
            from scistudio.agent_provisioning import install_project_agent_assets

            provision_result = install_project_agent_assets(Path(candidate.path), force=False)
            if provision_result.failed:
                logger.warning(
                    "ADR-040: agent provisioning top-up partial failure at %s: %s",
                    candidate.path,
                    provision_result.failed,
                )
        except Exception:  # pragma: no cover — defensive
            logger.warning(
                "ADR-040: agent provisioning top-up failed at %s (non-fatal)",
                candidate.path,
                exc_info=True,
            )
        # ADR-034: republish the MCP server port file into the newly active
        # project so the per-project ``mcp-bridge`` (spawned by the
        # embedded claude/codex TUI for THIS project) can discover it.
        self._publish_mcp_port(Path(candidate.path))
        return candidate

    def set_mcp_port(self, port: int | None) -> None:
        """Register the live MCP server port for publishing on project switch.

        Called once from the FastAPI ``lifespan`` after ``MCPServer.start()``.
        ``None`` clears the registration (used during shutdown).
        """
        self._mcp_port = port
        if port is not None and self.active_project is not None:
            self._publish_mcp_port(Path(self.active_project.path))

    def _publish_mcp_port(self, project_dir: Path) -> None:
        """Write the live MCP port into ``<project>/.scistudio/mcp.sock.port``.

        Best-effort: failures are logged and swallowed (e.g. read-only
        project root) so they cannot break ``open_project``. The file is
        owned by the backend's MCP server lifecycle; ``MCPServer.stop``
        cleans up its own home-fallback copy but not these per-project
        copies, so we additionally clear stale ones on next start (see
        the matching cleanup hook in ``app.lifespan``).
        """
        if self._mcp_port is None:
            return
        try:
            target_dir = project_dir / ".scistudio"
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "mcp.sock.port").write_text(str(self._mcp_port), encoding="utf-8")
        except OSError:
            import logging

            logging.getLogger(__name__).warning(
                "ApiRuntime: could not publish MCP port to %s/.scistudio/mcp.sock.port",
                project_dir,
                exc_info=True,
            )

    def update_project(
        self, project_id_or_path: str, *, name: str | None = None, description: str | None = None
    ) -> KnownProject:
        project = self.open_project(project_id_or_path)
        project_file = Path(project.path) / "project.yaml"
        raw = yaml.safe_load(project_file.read_text(encoding="utf-8")) or {}
        raw.setdefault("project", {})
        if name is not None:
            raw["project"]["name"] = name
            project.name = name
        if description is not None:
            raw["project"]["description"] = description
            project.description = description
        project_file.write_text(
            yaml.safe_dump(raw, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        self.known_projects[project.id] = project
        self._save_known_projects()
        return project

    def delete_project(self, project_id_or_path: str) -> None:
        project = self.open_project(project_id_or_path)
        project_path = Path(project.path).resolve()
        if not project_path.exists():
            self.known_projects.pop(project.id, None)
            self._save_known_projects()
            return
        if project_path == Path(project_path.anchor):
            raise ValueError("Refusing to delete drive root")
        if not (project_path / "project.yaml").is_file():
            # Not a valid project directory — remove from registry but don't
            # delete the directory (it may contain user files).
            logger.warning("Removing invalid project entry (no project.yaml): %s", project_path)
            self.known_projects.pop(project.id, None)
            if self.active_project is not None and self.active_project.id == project.id:
                self.active_project = None
                self.data_catalog = {}
            self._save_known_projects()
            return
        logger.warning("Deleting project directory: %s", project_path)
        # P1-3 (Phase 3.5 integration audit): UNION of ADR-038 lineage close
        # + ADR-039 _rmtree_force. We MUST do both:
        #
        #   * ADR-038: close the lineage SQLite handle before rmtree,
        #     otherwise Windows refuses to remove `.scistudio/lineage.db`
        #     (PermissionError [WinError 32]).
        #   * ADR-039: use `_rmtree_force` (not bare `shutil.rmtree`)
        #     because `.git/` contains read-only refs / pack files that
        #     plain rmtree cannot remove on Windows.
        #
        # The MetadataStore.get_metadata_store() block from the 039 source
        # is dropped — D38-2.3 collapsed `MetadataStore` into a deprecation
        # shim, so closing it is a no-op. The live store is `lineage_store`.
        if self.active_project is not None and self.active_project.id == project.id:
            store = getattr(self, "lineage_store", None)
            if store is not None:
                try:
                    store.close()
                except Exception:
                    logger.debug(
                        "ApiRuntime: close lineage store before delete failed",
                        exc_info=True,
                    )
                self.lineage_store = None
        _rmtree_force(project_path)
        self.known_projects.pop(project.id, None)
        if self.active_project is not None and self.active_project.id == project.id:
            self.active_project = None
            self.data_catalog = {}
        self._save_known_projects()

    def project_response(self, project: KnownProject) -> dict[str, Any]:
        workflows = self.list_project_workflows(project)
        return {
            "id": project.id,
            "name": project.name,
            "path": project.path,
            "description": project.description,
            "last_opened": project.last_opened,
            "workflow_count": len(workflows),
            "workflows": workflows,
            "current_workflow_id": workflows[0] if workflows else None,
        }

    def require_active_project(self) -> KnownProject:
        if self.active_project is None:
            raise RuntimeError("No project is currently open.")
        return self.active_project

    def list_project_workflows(self, project: KnownProject | None = None) -> list[str]:
        project = project or self.require_active_project()
        workflows_dir = Path(project.path) / "workflows"
        return sorted(path.stem for path in workflows_dir.glob("*.yaml"))

    def workflow_path(self, workflow_id: str) -> Path:
        project = self.require_active_project()
        return Path(project.path) / "workflows" / f"{workflow_id}.yaml"

    def save_workflow(self, payload: dict[str, Any]) -> WorkflowDefinition:
        # #506: relativify paths in node configs before persisting YAML.
        project_dir = self.active_project.path if self.active_project else None

        definition = WorkflowDefinition(
            id=payload["id"],
            version=payload.get("version", "1.0.0"),
            description=payload.get("description", ""),
            metadata=payload.get("metadata", {}),
            nodes=[
                NodeDef(
                    id=node["id"],
                    block_type=node["block_type"],
                    config=self._relativify_node_config(node.get("config", {}), node["block_type"], project_dir),
                    execution_mode=node.get("execution_mode"),
                    layout=node.get("layout"),
                )
                for node in payload.get("nodes", [])
            ],
            edges=[EdgeDef(source=edge["source"], target=edge["target"]) for edge in payload.get("edges", [])],
        )
        from scistudio.workflow.validator import validate_workflow

        errors = validate_workflow(definition, registry=self.block_registry)
        if errors:
            import logging

            logging.getLogger(__name__).warning(
                "Workflow validation warnings: %s",
                "; ".join(str(e) for e in errors),
            )

        path = self.workflow_path(definition.id)
        save_yaml(definition, path)
        # ADR-034 Phase 2: tell the FS watcher this write came from us so it
        # does not echo a ``workflow.changed`` event back to the canvas.
        try:
            from scistudio.api.routes.workflow_watcher import mark_self_write

            mark_self_write(path)
        except Exception:
            logger.warning("workflow_watcher: mark_self_write failed for %s", path, exc_info=True)
        return definition

    def load_workflow(self, workflow_id: str) -> WorkflowDefinition:
        path = self.workflow_path(workflow_id)
        if not path.exists():
            raise FileNotFoundError(f"Workflow not found: {workflow_id}")
        definition = load_yaml(path)

        # #506: resolve relative paths back to absolute using project dir.
        project_dir = self.active_project.path if self.active_project else None
        if project_dir:
            for node in definition.nodes:
                node.config = self._absolutify_node_config(node.config, node.block_type, project_dir)

        return definition

    def _config_schema_for_block(self, block_type: str) -> dict[str, Any]:
        """Look up the config_schema for a block type from the registry."""
        spec = self.block_registry.get_spec(block_type)
        if spec is not None:
            return spec.config_schema
        return {"type": "object", "properties": {}}

    def _relativify_node_config(
        self, config: dict[str, Any], block_type: str, project_dir: str | None
    ) -> dict[str, Any]:
        """Convert absolute paths in node config to relative paths (#506)."""
        if not project_dir:
            return config
        schema = self._config_schema_for_block(block_type)
        return relativify_paths(config, project_dir, schema)

    def _absolutify_node_config(
        self, config: dict[str, Any], block_type: str, project_dir: str | None
    ) -> dict[str, Any]:
        """Resolve relative paths in node config to absolute paths (#506)."""
        if not project_dir:
            return config
        schema = self._config_schema_for_block(block_type)
        return absolutify_paths(config, project_dir, schema)

    def delete_workflow(self, workflow_id: str) -> None:
        path = self.workflow_path(workflow_id)
        if path.exists():
            path.unlink()

    # ------------------------------------------------------------------
    # ADR-039 §5.2: ``current_revision`` / ``bump_revision`` removed in
    # D39-2.1. Git commit SHA plus working-tree dirty state replace the
    # optimistic-concurrency model.
    # ------------------------------------------------------------------

    def upload_file(self, filename: str, content: bytes) -> dict[str, Any]:
        project = self.require_active_project()
        safe_name = Path(filename).name  # strips all directory components
        if not safe_name or safe_name.startswith("."):
            raise ValueError(f"Invalid filename: {filename!r}")
        destination = Path(project.path) / "data" / "raw" / safe_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

        # T-TRK-004 / ADR-028 §D2: the legacy ``AdapterRegistry`` /
        # ``adapter.create_reference()`` dispatch was removed. Build the
        # ``StorageReference`` directly from the destination path; the
        # format is the file extension without the leading dot, falling
        # back to the bytes-stream sentinel for unknown payloads.
        extension = destination.suffix.lower().lstrip(".") or "bin"
        ref = StorageReference(
            backend="filesystem",
            path=str(destination),
            format=extension,
        )
        record = self.register_data_ref(ref)
        return {
            "ref": record.id,
            "type_name": record.type_name,
            "metadata": record.metadata,
        }

    def register_data_ref(
        self,
        ref: StorageReference,
        *,
        type_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DataRecord:
        resolved_type_name = type_name or _infer_type_name_from_ref(ref)
        # ADR-027 D2 / #407: propagate type_chain from the wire-format metadata
        # so that preview_data() can use TypeRegistry.resolve() + issubclass()
        # rather than hardcoded class name comparisons.
        ref_type_chain: list[str] = []
        if ref.metadata:
            tc = ref.metadata.get("type_chain")
            if isinstance(tc, list):
                ref_type_chain = [str(n) for n in tc]
        record = DataRecord(
            id=f"data-{uuid4().hex}",
            ref=ref,
            type_name=resolved_type_name,
            metadata=metadata or self.describe_ref(ref),
            type_chain=ref_type_chain,
        )
        self.data_catalog[record.id] = record
        return record

    def register_output_payload(self, payload: Any) -> Any:
        if isinstance(payload, dict) and {"backend", "path"}.issubset(payload.keys()):
            ref = StorageReference(
                backend=str(payload["backend"]),
                path=str(payload["path"]),
                format=payload.get("format"),
                metadata=payload.get("metadata"),
            )
            # ADR-027 D2 / #407: extract type_chain from wire-format metadata
            # and pass as explicit type_name so _infer_type_name_from_ref() is
            # bypassed entirely for worker-produced payloads.  This preserves
            # plugin type identity (e.g. "Image" instead of "Array").
            explicit_type_name: str | None = None
            raw_meta = payload.get("metadata") or {}
            tc = raw_meta.get("type_chain") if isinstance(raw_meta, dict) else None
            if tc and isinstance(tc, list) and tc:
                explicit_type_name = str(tc[-1])
            record = self.register_data_ref(ref, type_name=explicit_type_name, metadata=self.describe_ref(ref))
            return {
                "data_ref": record.id,
                "type_name": record.type_name,
                "metadata": record.metadata,
            }
        if isinstance(payload, dict) and payload.get("_collection") is True:
            items = [self.register_output_payload(item) for item in payload.get("items", [])]
            return {
                "kind": "collection",
                "count": len(items),
                "item_type": payload.get("item_type"),
                "items": items,
            }
        if isinstance(payload, dict):
            return {key: self.register_output_payload(value) for key, value in payload.items()}
        if isinstance(payload, list):
            return [self.register_output_payload(item) for item in payload]
        return payload

    def get_data_record(self, data_ref: str) -> DataRecord:
        if data_ref not in self.data_catalog:
            raise KeyError(f"Unknown data reference: {data_ref}")
        return self.data_catalog[data_ref]

    def describe_ref(self, ref: StorageReference) -> dict[str, Any]:
        path = Path(ref.path)
        metadata: dict[str, Any] = {
            "backend": ref.backend,
            "path": ref.path,
            "format": ref.format,
            "exists": path.exists(),
        }
        if path.exists():
            metadata["size_bytes"] = path.stat().st_size
        if ref.metadata:
            metadata.update(ref.metadata)
        if path.suffix.lower() == ".parquet" and path.exists():
            try:
                table = pq.read_table(path)
                metadata["columns"] = table.column_names
                metadata["row_count"] = table.num_rows
            except Exception:
                logger.debug("Failed to read parquet metadata for %s", ref.path, exc_info=True)
        return metadata

    def _resolve_record_class(self, record: DataRecord) -> type | None:
        """Resolve the DataObject class for *record* via TypeRegistry.

        ADR-027 D2 / #405: Consults ``record.type_chain`` (populated by
        ``register_data_ref`` from wire-format metadata) via
        ``TypeRegistry.resolve(list)``, falling back to a single-name lookup
        on ``record.type_name``.  Returns ``None`` when the type is not
        registered (e.g. a plugin that is not installed in this environment).
        """
        chain = record.type_chain or [record.type_name]
        try:
            return self.type_registry.resolve(chain)
        except Exception:
            return None

    def preview_data(
        self,
        data_ref: str,
        slice_index: int = 0,
        page: int = 1,
        page_size: int = 50,
        sort_by: str | None = None,
        sort_dir: str = "asc",
    ) -> dict[str, Any]:
        """Return a lightweight preview for a stored data object.

        Parameters
        ----------
        data_ref:
            Catalog identifier returned by ``register_data_ref``.
        slice_index:
            Index into the slider axis (3D viewer, #899). Clamped to
            ``[0, slice_axis_size - 1]``. Ignored for 2D arrays / non-image
            previews.
        page, page_size, sort_by, sort_dir:
            DataFrame paging + sort. Page is 1-based and clamped server-side;
            ``page_size`` is capped at ``MAX_TABLE_PAGE_SIZE``. ``sort_by`` is
            ignored when the column is missing. Non-table previews ignore
            these.
        """
        record = self.get_data_record(data_ref)
        ref = record.ref
        path = Path(ref.path)
        suffix = path.suffix.lower()

        # ADR-027 D2 / #405: resolve the concrete class via TypeRegistry so
        # plugin types (Image, Spectrum, …) are matched by subclass relationship
        # rather than by exact class name equality.
        resolved_cls = self._resolve_record_class(record)

        # ------------------------------------------------------------------
        # DataFrame / tabular
        # ------------------------------------------------------------------
        is_dataframe = record.type_name == DataFrame.__name__ or (
            resolved_cls is not None and issubclass(resolved_cls, DataFrame)
        )
        if is_dataframe or suffix in {".csv", ".parquet"}:
            # Page bounds. ``page_size`` is capped to keep response
            # payloads small. ``page`` is clamped after we know the total.
            effective_page_size = max(1, min(int(page_size), MAX_TABLE_PAGE_SIZE))

            # Column-name validation has to happen on the unsorted base — we
            # don't want a typo'd sort_by to force a useless read.
            base = _get_preview_table(path, sort_by=None, sort_dir="asc")
            columns = list(base.column_names)
            total_rows = base.num_rows

            effective_sort_dir = sort_dir if sort_dir in {"asc", "desc"} else "asc"
            effective_sort_by: str | None = None
            if sort_by and sort_by in columns:
                try:
                    table = _get_preview_table(path, sort_by=sort_by, sort_dir=effective_sort_dir)
                    effective_sort_by = sort_by
                except Exception:
                    logger.debug("Sort failed on column %s; returning unsorted", sort_by, exc_info=True)
                    table = base
            else:
                table = base

            total_pages = max(1, (total_rows + effective_page_size - 1) // effective_page_size)
            effective_page = max(1, min(int(page), total_pages))
            offset = (effective_page - 1) * effective_page_size
            page_table = table.slice(offset, effective_page_size)
            rows = page_table.to_pylist()
            return {
                "kind": "table",
                "columns": columns,
                "rows": rows,
                "total_rows": total_rows,
                "row_count": total_rows,  # backward-compat alias
                "page": effective_page,
                "page_size": effective_page_size,
                "total_pages": total_pages,
                "sort_by": effective_sort_by,
                "sort_dir": effective_sort_dir if effective_sort_by else None,
            }

        # ------------------------------------------------------------------
        # Text / artifact (text-based formats only)
        # ------------------------------------------------------------------
        is_text = record.type_name in {Text.__name__, Artifact.__name__} or (
            resolved_cls is not None and (issubclass(resolved_cls, Text) or issubclass(resolved_cls, Artifact))
        )
        if is_text and suffix in {
            ".txt",
            ".json",
            ".yaml",
            ".yml",
            ".md",
        }:
            text = path.read_text(encoding="utf-8", errors="replace")
            return {
                "kind": "text",
                "content": text[:5000],
                "language": suffix.lstrip(".") or "text",
            }

        # ------------------------------------------------------------------
        # Array / image (raster data)
        # ------------------------------------------------------------------
        is_array = record.type_name == Array.__name__ or (resolved_cls is not None and issubclass(resolved_cls, Array))
        if is_array or suffix in {".tif", ".tiff", ".zarr"}:
            # T-TRK-004 / ADR-028 §D2: ``TIFFAdapter`` is gone. Read the
            # tiff directly via the ``tifffile`` package, which was the
            # adapter's only dependency. The imaging plugin's
            # ``LoadImage`` block will own this code path post-Phase 11
            # (T-IMG-002).
            try:
                matrix = _load_preview_matrix(ref)
                full_shape = list(matrix.shape)
                # #899 — 3D viewer with single slider. Pick the (y, x) plane
                # using the Array's declared axes (from
                # ``_serialise_extra_metadata`` in core/types/array.py:410).
                # When axes are unavailable, fall back to numpy convention
                # (last two dims = (y, x)). The first remaining axis
                # becomes the slider axis; anything beyond that peels
                # ``[0]`` as a v1 ndim>3 fallback.
                axes_raw = ref.metadata.get("axes") if ref.metadata else None
                axes: list[str] = [str(a) for a in axes_raw] if isinstance(axes_raw, list) else []
                ndim = matrix.ndim
                if axes and "y" in axes and "x" in axes:
                    y_idx = axes.index("y")
                    x_idx = axes.index("x")
                else:
                    y_idx = max(0, ndim - 2)
                    x_idx = max(0, ndim - 1)
                # First non-(y, x) dim; None if 2-D.
                extra_dims = [i for i in range(ndim) if i not in (y_idx, x_idx)]
                slice_axis_idx: int | None = extra_dims[0] if extra_dims else None
                slice_axis_size: int | None = full_shape[slice_axis_idx] if slice_axis_idx is not None else None
                slice_axis_name: str | None
                if slice_axis_idx is None:
                    slice_axis_name = None
                elif axes and slice_axis_idx < len(axes):
                    slice_axis_name = axes[slice_axis_idx]
                else:
                    slice_axis_name = f"axis {slice_axis_idx}"
                # Clamp slice request to valid range. Negative or
                # out-of-range values become a valid slice rather than 400.
                clamped_slice: int | None
                if slice_axis_size is not None and slice_axis_size > 0:
                    clamped_slice = max(0, min(int(slice_index), slice_axis_size - 1))
                else:
                    clamped_slice = None
                # Extract a 2-D slab.
                slab = matrix
                if slice_axis_idx is not None and clamped_slice is not None:
                    sel: list[Any] = [slice(None)] * slab.ndim
                    sel[slice_axis_idx] = clamped_slice
                    slab = slab[tuple(sel)]
                # ndim > 3 fallback: peel further extra dims with [0].
                while getattr(slab, "ndim", 0) > 2:
                    slab = slab[0]
                # If axes declared (x, y) instead of (y, x), transpose so
                # the rendered image is right-side-up.
                if axes and "y" in axes and "x" in axes and axes.index("y") > axes.index("x"):
                    slab = slab.T
                thumbnail = _downsample_matrix(slab)
                return {
                    "kind": "image",
                    "shape": full_shape,
                    "axes": axes,
                    "slice_axis_name": slice_axis_name,
                    "slice_axis_size": slice_axis_size,
                    "slice_index": clamped_slice,
                    "thumbnail": thumbnail,
                    "src": _image_data_uri_from_matrix(thumbnail),
                }
            except Exception:
                logger.debug("Failed to read raster preview for %s", ref.path, exc_info=True)
            return {
                "kind": "artifact",
                "path": ref.path,
                "mime_type": "image/tiff" if suffix in {".tif", ".tiff"} else "application/zarr",
            }

        # ------------------------------------------------------------------
        # Series / spectral (chart preview)
        # ADR-027 D2 / #405: replaced the "Spectrum" substring hack with a
        # proper issubclass check via TypeRegistry.  Plugin-provided spectra
        # still hit this path because Spectrum is a Series subclass.
        # ------------------------------------------------------------------
        is_series = record.type_name == Series.__name__ or (
            resolved_cls is not None and issubclass(resolved_cls, Series)
        )
        if is_series:
            values = record.metadata.get("values", [])
            return {
                "kind": "chart",
                "points": [{"x": index, "y": value} for index, value in enumerate(values[:256])],
            }

        # ------------------------------------------------------------------
        # CompositeData
        # ------------------------------------------------------------------
        is_composite = record.type_name == CompositeData.__name__ or (
            resolved_cls is not None and issubclass(resolved_cls, CompositeData)
        )
        if is_composite:
            # Try to render the raster slot as an image preview (e.g. Label)
            composite_path = Path(ref.path)
            for slot_name in ("raster",):
                slot_path = composite_path / slot_name
                if slot_path.exists():
                    try:
                        slot_ref = StorageReference(backend="zarr", path=str(slot_path))
                        raster_matrix = _load_preview_matrix(slot_ref)
                        while getattr(raster_matrix, "ndim", 0) > 2:
                            raster_matrix = raster_matrix[0]
                        full_shape = list(raster_matrix.shape)
                        thumbnail = _downsample_matrix(raster_matrix)
                        return {
                            "kind": "image",
                            "shape": full_shape,
                            "thumbnail": thumbnail,
                            "src": _image_data_uri_from_matrix(thumbnail),
                        }
                    except Exception:
                        logger.debug("Failed to read raster slot '%s' for composite preview", slot_name, exc_info=True)
            return {
                "kind": "composite",
                "slots": record.metadata.get("slots", {}),
            }

        return {
            "kind": "artifact",
            "path": ref.path,
            "mime_type": path.suffix.lower().lstrip(".") or "application/octet-stream",
        }

    def _ancestors_of(self, workflow: WorkflowDefinition, block_id: str) -> set[str]:
        from scistudio.engine.dag import build_dag

        dag = build_dag(workflow)
        visited: set[str] = set()
        queue = list(dag.reverse_adjacency.get(block_id, []))
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            queue.extend(dag.reverse_adjacency.get(current, []))
        return visited

    def checkpoint_dir_for(self, workflow_id: str) -> Path:
        """Return the per-workflow pause/resume checkpoint directory.

        Per ADR-038 §5.2 (Phase D38-2.3) the checkpoint files relocate
        from ``<project>/checkpoints/<workflow_id>/`` to
        ``<project>/.scistudio/pause/<workflow_id>/``. The semantics
        (single-slot, overwrite-on-terminal-event per ADR-012) are
        unchanged — only the path moves so the user-visible top-level
        project directory stays clean.

        Backward compatibility: when a legacy ``checkpoints/<workflow_id>/``
        directory exists from a pre-Phase 2 run it is **not** migrated
        (per the ADR-038 §6 Phase 2 no-migration policy). The user can
        delete it manually; new runs overwrite into the new location.
        """
        project = self.require_active_project()
        return Path(project.path) / ".scistudio" / "pause" / workflow_id

    # ------------------------------------------------------------------
    # ADR-038: per-run lineage construction
    # ------------------------------------------------------------------

    def _build_lineage_recorder(
        self,
        *,
        workflow_id: str,
        workflow: WorkflowDefinition,
        execute_from: str | None,
        parent_run_id: str | None = None,
        workflow_git_commit: str | None = None,
        workflow_dirty: bool = False,
    ) -> Any:
        """Construct a per-run :class:`LineageRecorder` and seed its ``runs`` row.

        Returns ``None`` when the lineage store is unavailable. Failures during
        construction or the initial ``insert_run`` are logged and swallowed
        (best-effort per ADR-038 §3.2).

        D38-3.2 (closes D38-3.1a P2 / D38-3.1b P2-4): ``parent_run_id`` is
        threaded through from :meth:`start_workflow` so re-runs link back
        to the historical run per ADR §3.6. ``None`` for fresh runs.

        Phase 3.5 integration audit P1-1 + P1-2: ``workflow_git_commit``
        and ``workflow_dirty`` are now threaded into the ``RunRecord``
        constructor at INSERT time. This is the audit-recommended fix —
        previously the SHA was UPDATEd into the row by a separate
        ``set_pending_git_commit`` call which (a) raced with the
        scheduler's lineage init and could stamp the SHA onto the
        PREVIOUS run, and (b) left ``workflow_dirty`` permanently 0 so
        the "auto-commit failed → tree was dirty" safety net was dead.
        Both fields now arrive on the same row as the rest of the
        run metadata.
        """
        if self.lineage_store is None:
            return None
        try:
            from scistudio.core.lineage.environment import EnvironmentSnapshot
            from scistudio.core.lineage.record import RunRecord
            from scistudio.core.lineage.recorder import LineageRecorder

            run_id = uuid4().hex
            workflow_yaml_snapshot = self._serialise_workflow_snapshot(workflow_id, workflow)
            # Capture env without the full freeze for now — Phase D38-2.3
            # / D39-2.5 may tune this; the freeze on every run is expensive
            # for short workflows. The recorder schema mandates full=True
            # per ADR-038 §5.2; we honour that here.
            env_snapshot = EnvironmentSnapshot.capture(full=True).to_dict()
            triggered_by = "execute_from" if execute_from is not None else "user"
            run = RunRecord(
                run_id=run_id,
                workflow_id=workflow_id,
                workflow_yaml_snapshot=workflow_yaml_snapshot,
                started_at=_now_iso(),
                status="running",
                environment_snapshot=env_snapshot,
                triggered_by=triggered_by,
                execute_from_block_id=execute_from,
                parent_run_id=parent_run_id,
                workflow_git_commit=workflow_git_commit,
                workflow_dirty=1 if workflow_dirty else 0,
            )
            recorder = LineageRecorder(self.event_bus, self.lineage_store, run_id=run_id)
            recorder.begin_run(run)
            return recorder
        except Exception:
            logger.warning("ADR-038: failed to construct LineageRecorder (non-fatal)", exc_info=True)
            return None

    def _serialise_workflow_snapshot(self, workflow_id: str, workflow: WorkflowDefinition) -> str:
        """Return the on-disk workflow YAML, falling back to a re-serialisation."""
        try:
            path = self.workflow_path(workflow_id)
            if path.exists():
                return path.read_text(encoding="utf-8")
        except Exception:
            logger.debug("ADR-038: workflow yaml snapshot disk read failed", exc_info=True)
        try:
            return yaml.safe_dump(
                {
                    "id": workflow.id,
                    "nodes": [{"id": n.id, "block_type": n.block_type, "config": n.config} for n in workflow.nodes],
                    "edges": [{"source": e.source, "target": e.target} for e in workflow.edges],
                },
                default_flow_style=False,
                sort_keys=False,
            )
        except Exception:
            return ""

    def _derive_lineage_run_status(
        self,
        scheduler: DAGScheduler,
        task: asyncio.Task[None],
    ) -> str:
        """Return the ADR-038 ``runs.status`` for a finished workflow task.

        ``DAGScheduler`` treats block-level failures as normal terminal
        workflow completion: it records the failed block as ``ERROR``,
        propagates ``SKIPPED`` downstream, and resolves the workflow task
        without re-raising the block exception. Therefore task exception
        state alone is insufficient for lineage run status.
        """
        if task.cancelled():
            return "cancelled"

        exc = task.exception()
        if exc is not None:
            return "failed"

        state_values = {str(getattr(state, "value", state)) for state in scheduler.block_states().values()}
        if "error" in state_values:
            return "failed"
        if "cancelled" in state_values:
            return "cancelled"
        return "completed"

    def _finalize_lineage_run(
        self,
        recorder: Any,
        task: asyncio.Task[None],
        scheduler: DAGScheduler,
    ) -> None:
        """Update the ``runs`` row when the workflow task finishes.

        D38-3.2 (closes Codex P1 on PR #926 / D38-3.1b P1-2): also
        ``dispose()`` the recorder so it unsubscribes from
        :attr:`event_bus`. Without this, every successive
        ``start_workflow`` call accumulates one more terminal-event
        subscriber, polluting later runs' lineage rows with cross-run
        callbacks. Dispose is idempotent and best-effort.
        """
        try:
            status = self._derive_lineage_run_status(scheduler, task)
            recorder.finalize_run(status=status)
        except Exception:
            logger.debug("ADR-038: lineage run finalisation failed", exc_info=True)
        # Unsubscribe regardless of whether finalize succeeded — a leaked
        # subscription is worse than a missing finished_at column.
        try:
            recorder.dispose()
        except Exception:
            logger.debug("ADR-038: lineage recorder dispose failed", exc_info=True)

    def start_workflow(
        self,
        workflow_id: str,
        *,
        execute_from: str | None = None,
        parent_run_id: str | None = None,
    ) -> dict[str, Any]:
        """Schedule a workflow run.

        D38-3.2 (closes D38-3.1a P2 / D38-3.1b P2-4): ``parent_run_id``
        is a new optional parameter used by the ``/api/runs/{run_id}/rerun``
        endpoint to stamp the new run's ``runs.parent_run_id`` column
        pointing at the historical run that triggered the rerun.

        Phase 3.5 integration: also drives the ADR-039 §3.4 pre-run
        auto-commit path. The captured SHA + the post-commit dirty
        flag are threaded into :meth:`_build_lineage_recorder` so the
        ADR-038 ``runs`` row carries ``workflow_git_commit`` /
        ``workflow_dirty`` at INSERT time. This eliminates the
        previous ``set_pending_git_commit`` UPDATE race (Phase 3.5
        audit P1-1) and populates the previously-dead ``workflow_dirty``
        field (audit P1-2).
        """
        # ------------------------------------------------------------------
        # ADR-039 §3.4 pre-run auto-commit
        # ------------------------------------------------------------------
        # Best-effort: if git is unavailable / not a repo, the workflow
        # still runs without versioning (degraded mode per §3.9).
        #
        # The captured ``workflow_git_commit`` and ``workflow_dirty``
        # values are passed into ``_build_lineage_recorder`` below so the
        # ADR-038 ``runs`` row carries them on the INSERT for THIS run.
        workflow_git_commit: str | None = None
        workflow_dirty: bool = False
        try:
            if self.active_project is not None:
                from datetime import datetime

                from scistudio.core.versioning.git_engine import GitEngine

                project_path = Path(self.active_project.path)
                engine = GitEngine(project_path)
                if engine.is_repository(project_path):
                    state = engine.head_state()
                    if state.dirty:
                        short_id = uuid4().hex[:8]
                        ts = datetime.now(UTC).isoformat()
                        msg = f"pre-run @ {ts} (run={short_id}, workflow={workflow_id})"
                        try:
                            new_sha = engine.commit(msg, prefix="auto")
                            workflow_git_commit = new_sha
                            # Auto-commit succeeded; tree is clean post-commit.
                            workflow_dirty = False
                        except Exception:
                            # Codex P1 on PR #959: when the dirty-tree
                            # auto-commit fails we MUST NOT fall back to
                            # the prior HEAD SHA. The workflow is about
                            # to execute against an uncommitted working
                            # tree, so the prior SHA does not represent
                            # what actually ran — persisting it would
                            # let "Restore this run's workflow" restore
                            # the wrong revision and silently corrupt
                            # reproducibility. Degrade to ``None`` so
                            # the lineage row's ``workflow_dirty=1``
                            # safety net (ADR-038 §3.1 + ADR-039 §3.4 +
                            # Phase 3.5 audit P1-2) is the source of
                            # truth instead.
                            logger.warning(
                                "ADR-039: pre-run auto-commit failed for %s — "
                                "treating run as degraded (workflow_git_commit=None, "
                                "workflow_dirty=1)",
                                workflow_id,
                                exc_info=True,
                            )
                            workflow_git_commit = None
                            workflow_dirty = True
                    else:
                        workflow_git_commit = state.commit_sha or None
                        workflow_dirty = False
        except Exception:
            logger.warning(
                "ADR-039: pre-run auto-commit path errored for %s",
                workflow_id,
                exc_info=True,
            )

        if workflow_git_commit:
            logger.debug(
                "ADR-039: captured workflow_git_commit=%s for workflow %s (workflow_dirty=%s)",
                workflow_git_commit,
                workflow_id,
                workflow_dirty,
            )

        workflow = self.load_workflow(workflow_id)
        checkpoint_manager = CheckpointManager(self.checkpoint_dir_for(workflow_id))
        checkpoint = checkpoint_manager.load(workflow_id) if execute_from is not None else None
        if execute_from is not None and checkpoint is None:
            raise ValueError("Run the full workflow at least once before using 'Run from here'")

        # ADR-038 §3.2: create a ``runs`` row, build a LineageRecorder, and
        # pass it to the scheduler. Best-effort: when the lineage store is
        # unavailable (no project open in a test, init failure), the
        # recorder is None and the scheduler skips the lineage path.
        #
        # Phase 3.5 integration audit P1-1 + P1-2: ``workflow_git_commit`` and
        # ``workflow_dirty`` are threaded through so the runs row carries
        # them at INSERT time (not via a follow-up UPDATE that would race
        # with the previous run).
        lineage_recorder = self._build_lineage_recorder(
            workflow_id=workflow_id,
            workflow=workflow,
            execute_from=execute_from,
            parent_run_id=parent_run_id,
            workflow_git_commit=workflow_git_commit,
            workflow_dirty=workflow_dirty,
        )

        scheduler = DAGScheduler(
            workflow=workflow,
            event_bus=self.event_bus,
            resource_manager=self.resource_manager,
            process_registry=self.process_registry,
            runner=self.runner,
            registry=self.block_registry,
            checkpoint_manager=checkpoint_manager,
            lineage_recorder=lineage_recorder,
            project_dir=str(self.active_project.path) if self.active_project else None,
        )

        async def _run() -> None:
            if execute_from is not None:
                await self.log_broadcaster.publish(
                    level="info",
                    message=f"execute from {execute_from}",
                    workflow_id=workflow_id,
                )
                await scheduler.execute_from(execute_from)
            else:
                await self.log_broadcaster.publish(
                    level="info",
                    message="workflow execution started",
                    workflow_id=workflow_id,
                )
                await scheduler.execute()

        task = asyncio.create_task(_run())
        task.add_done_callback(
            lambda finished: asyncio.create_task(self._log_workflow_task_failure(workflow_id, finished))
        )
        if lineage_recorder is not None:
            recorder_for_callback = lineage_recorder

            def _on_done(finished: asyncio.Task[None]) -> None:
                self._finalize_lineage_run(recorder_for_callback, finished, scheduler)

            task.add_done_callback(_on_done)
        self.workflow_runs[workflow_id] = WorkflowRun(
            scheduler=scheduler,
            task=task,
            checkpoint_manager=checkpoint_manager,
            workflow_git_commit=workflow_git_commit,
        )

        reused_blocks: list[str] = []
        if execute_from is not None:
            reused_blocks = sorted(self._ancestors_of(workflow, execute_from))

        reset_blocks = sorted(set(node.id for node in workflow.nodes) - set(reused_blocks))
        # ADR-039 §3.4 D39-2.5: the captured ``workflow_git_commit`` is
        # carried on ``WorkflowRun.workflow_git_commit`` for the
        # LineageRecorder (ADR-038) join. ``WorkflowExecutionResponse``
        # remains schema-stable (no new field) — the Lineage tab reads
        # the SHA from the ``runs.workflow_git_commit`` column once the
        # lineage row lands, not from this start-response.
        return {
            "workflow_id": workflow_id,
            "status": "started",
            "message": "Workflow execution has been scheduled.",
            "reused_blocks": reused_blocks,
            "reset_blocks": reset_blocks,
        }

    async def _log_workflow_task_failure(self, workflow_id: str, task: asyncio.Task[None]) -> None:
        """Surface unexpected workflow task failures to logs and SSE clients."""
        if task.cancelled():
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc is None:
            return
        logger.error(
            "Workflow %s task failed: %s",
            workflow_id,
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        await self.log_broadcaster.publish(
            level="error",
            message=str(exc),
            workflow_id=workflow_id,
        )

    def get_run(self, workflow_id: str) -> WorkflowRun:
        if workflow_id not in self.workflow_runs:
            raise KeyError(f"Workflow is not running: {workflow_id}")
        return self.workflow_runs[workflow_id]
