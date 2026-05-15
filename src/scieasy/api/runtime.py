"""Shared runtime services for the FastAPI layer."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

import pyarrow.parquet as pq
import yaml

from scieasy.blocks.registry import BlockRegistry
from scieasy.core.storage.ref import StorageReference
from scieasy.core.types.array import Array
from scieasy.core.types.artifact import Artifact
from scieasy.core.types.composite import CompositeData
from scieasy.core.types.dataframe import DataFrame
from scieasy.core.types.registry import TypeRegistry
from scieasy.core.types.series import Series
from scieasy.core.types.text import Text
from scieasy.engine.checkpoint import CheckpointManager
from scieasy.engine.events import EventBus
from scieasy.engine.resources import ResourceManager
from scieasy.engine.runners.local import LocalRunner
from scieasy.engine.runners.process_handle import ProcessRegistry
from scieasy.engine.scheduler import DAGScheduler
from scieasy.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition
from scieasy.workflow.serializer import absolutify_paths, load_yaml, relativify_paths, save_yaml

logger = logging.getLogger(__name__)


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
    """Track a live scheduler task for a workflow."""

    scheduler: DAGScheduler
    task: asyncio.Task[None]
    checkpoint_manager: CheckpointManager


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
        self.registry_dir = Path.home() / ".scieasy"
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.known_projects_path = self.registry_dir / "projects.json"
        self.known_projects: dict[str, KnownProject] = {}

        self.active_project: KnownProject | None = None
        self.data_catalog: dict[str, DataRecord] = {}
        self.workflow_runs: dict[str, WorkflowRun] = {}
        # ADR-034: the MCP server's TCP/socket port is published into the
        # active project's ``.scieasy/`` so the per-project ``mcp-bridge``
        # subprocess can discover it. Held here so ``open_project`` can
        # republish on project switch (otherwise the bridge keeps looking
        # in the previous project and falls back to standalone mode,
        # which has no ApiRuntime and breaks ``run_workflow``).
        self._mcp_port: int | None = None
        # #718 part (a): in-memory monotonic revision counter per workflow_id.
        # Used for optimistic concurrency on the PUT /api/workflows/{id} path.
        # Single-process, single-user scope (matches ADR-033 §3 D2.1); resets
        # on server restart and is re-seeded to 0 on the next load.
        self._workflow_revisions: dict[str, int] = {}

        self.event_bus = EventBus()
        self.resource_manager = ResourceManager(event_bus=self.event_bus)
        self.process_registry = ProcessRegistry()
        self.runner = LocalRunner(event_bus=self.event_bus, registry=self.process_registry)
        self.block_registry = BlockRegistry()
        self.type_registry = TypeRegistry()
        self.log_broadcaster = LogBroadcaster()

        self._load_known_projects()
        self._configure_static_registries()
        self._bind_event_logging()

    def _configure_static_registries(self) -> None:
        include_monorepo = os.environ.get("SCIEASY_DEV") == "1"
        if include_monorepo:
            logger.info("SCIEASY_DEV=1: monorepo package scan enabled")
        self.type_registry.scan_all(include_monorepo=include_monorepo)
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
            registry.add_scan_dir(Path.home() / ".scieasy" / "blocks")
        registry.scan(include_monorepo=os.environ.get("SCIEASY_DEV") == "1")
        self.block_registry = registry

    def _init_metadata_store(self, project_path: Path) -> None:
        """Initialize the project-level MetadataStore (ADR-032).

        Creates or opens the SQLite database at ``<project>/metadata.db``
        and sets the module-level singleton so that the engine scheduler
        can persist DataObject metadata after block execution.

        Non-fatal: if initialization fails the store is set to None and
        the system degrades to pre-ADR-032 behaviour (no metadata persistence).
        """
        try:
            from scieasy.core.metadata_store import MetadataStore, set_metadata_store

            db_path = project_path / "metadata.db"
            store = MetadataStore(db_path)
            set_metadata_store(store)
            logger.info("ADR-032: MetadataStore opened at %s", db_path)
        except Exception:
            logger.warning("ADR-032: Failed to initialize MetadataStore (non-fatal)", exc_info=True)
            from scieasy.core.metadata_store import set_metadata_store

            set_metadata_store(None)

    def create_project(self, name: str, description: str = "", parent_path: str | None = None) -> KnownProject:
        parent_dir = _safe_parent_dir(parent_path)
        project_path = parent_dir / _slugify(name)
        if project_path.exists():
            raise FileExistsError(f"Project directory already exists: {project_path}")

        for subdir in (
            "workflows",
            "data/raw",
            "data/zarr",
            "data/parquet",
            "data/artifacts",
            "data/exchange",
            "blocks",
            "types",
            "checkpoints",
            "lineage",
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
        self.open_project(project.id)
        return project

    def list_projects(self) -> list[KnownProject]:
        self._load_known_projects()
        # Prune entries whose project directory no longer exists on disk
        stale_ids = [pid for pid, entry in self.known_projects.items() if not Path(entry.path).is_dir()]
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
                raise FileNotFoundError(f"Not a valid SciEasy project (no project.yaml): {resolved}")
            candidate = self._load_project_from_path(resolved)
        candidate.last_opened = _now_iso()
        self.known_projects[candidate.id] = candidate
        self._save_known_projects()
        self.active_project = candidate
        self.data_catalog = {}
        # #718 part (a): revisions are project-scoped — reset on project switch
        # so a workflow_id in the new project starts at revision 0.
        self._workflow_revisions = {}
        self.refresh_block_registry()
        self._init_metadata_store(Path(candidate.path))
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
        """Write the live MCP port into ``<project>/.scieasy/mcp.sock.port``.

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
            target_dir = project_dir / ".scieasy"
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "mcp.sock.port").write_text(str(self._mcp_port), encoding="utf-8")
        except OSError:
            import logging

            logging.getLogger(__name__).warning(
                "ApiRuntime: could not publish MCP port to %s/.scieasy/mcp.sock.port",
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
        shutil.rmtree(project_path)
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
        from scieasy.workflow.validator import validate_workflow

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
            from scieasy.api.routes.workflow_watcher import mark_self_write

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
        # #718 part (a): clear the in-memory revision so a future workflow
        # with the same id starts fresh at 0.
        self._workflow_revisions.pop(workflow_id, None)

    # ------------------------------------------------------------------
    # #718 part (a): in-memory workflow revision tracking.
    # ------------------------------------------------------------------

    def current_revision(self, workflow_id: str) -> int:
        """Return the current monotonic revision for *workflow_id*.

        Returns 0 when the workflow has never been written or has not been
        observed in this process lifetime.
        """
        return self._workflow_revisions.get(workflow_id, 0)

    def bump_revision(self, workflow_id: str) -> int:
        """Increment and return the revision for *workflow_id*.

        Called by the route layer after every successful write to the
        workflow YAML (PUT, POST, import-path).
        """
        next_rev = self._workflow_revisions.get(workflow_id, 0) + 1
        self._workflow_revisions[workflow_id] = next_rev
        return next_rev

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

    def preview_data(self, data_ref: str) -> dict[str, Any]:
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
            if suffix == ".parquet":
                table = pq.read_table(path).slice(0, 100)
            else:
                import pyarrow.csv as pcsv

                table = pcsv.read_csv(str(path)).slice(0, 100)
            rows = table.to_pylist()
            return {
                "kind": "table",
                "columns": table.column_names,
                "rows": rows,
                "row_count": len(rows),
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
                while getattr(matrix, "ndim", 0) > 2:
                    matrix = matrix[0]
                full_shape = list(matrix.shape)
                thumbnail = _downsample_matrix(matrix)
                return {
                    "kind": "image",
                    "shape": full_shape,
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
        from scieasy.engine.dag import build_dag

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
        project = self.require_active_project()
        return Path(project.path) / "checkpoints" / workflow_id

    def start_workflow(self, workflow_id: str, *, execute_from: str | None = None) -> dict[str, Any]:
        workflow = self.load_workflow(workflow_id)
        checkpoint_manager = CheckpointManager(self.checkpoint_dir_for(workflow_id))
        checkpoint = checkpoint_manager.load(workflow_id) if execute_from is not None else None
        if execute_from is not None and checkpoint is None:
            raise ValueError("Run the full workflow at least once before using 'Run from here'")

        scheduler = DAGScheduler(
            workflow=workflow,
            event_bus=self.event_bus,
            resource_manager=self.resource_manager,
            process_registry=self.process_registry,
            runner=self.runner,
            registry=self.block_registry,
            checkpoint_manager=checkpoint_manager,
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
        self.workflow_runs[workflow_id] = WorkflowRun(
            scheduler=scheduler,
            task=task,
            checkpoint_manager=checkpoint_manager,
        )

        reused_blocks: list[str] = []
        if execute_from is not None:
            reused_blocks = sorted(self._ancestors_of(workflow, execute_from))

        reset_blocks = sorted(set(node.id for node in workflow.nodes) - set(reused_blocks))
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
