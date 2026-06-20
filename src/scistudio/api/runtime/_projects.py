"""Project-management method implementations.

Issue #1430 / umbrella #1427: extracted verbatim from the original
``api/runtime.py`` god-file. Each function is a free function whose
first parameter is ``self`` — they are bound onto ``ApiRuntime`` in
``runtime/__init__.py`` via class-body static assignment so griffe
emits the canonical ``scistudio.api.runtime.ApiRuntime.<method>`` fact
(see ADR-042 + the doc/closure audit walker).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote
from uuid import uuid4

import yaml

from scistudio.blocks.registry import BlockRegistry
from scistudio.core.types.registry import TypeRegistry
from scistudio.workflow.definition import WorkflowDefinition
from scistudio.workflow.serializer import save_yaml

from ._helpers import _now_iso, _rmtree_force, _safe_parent_dir, _slugify

if TYPE_CHECKING:
    from . import ApiRuntime, KnownProject

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Registry refresh + lineage/metadata store wiring
# ----------------------------------------------------------------------


def _load_known_projects(self: ApiRuntime) -> None:
    from . import KnownProject

    if not self.known_projects_path.exists():
        self.known_projects = {}
        return
    raw = json.loads(self.known_projects_path.read_text(encoding="utf-8"))
    self.known_projects = {
        entry["id"]: KnownProject(**entry)
        for entry in raw.get("projects", [])
        if isinstance(entry, dict) and entry.get("id") and entry.get("path")
    }


def _save_known_projects(self: ApiRuntime) -> None:
    payload = {"projects": [asdict(entry) for entry in self.known_projects.values()]}
    self.known_projects_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def refresh_block_registry(self: ApiRuntime) -> None:
    import os

    registry = BlockRegistry()
    if self.active_project is not None:
        registry.add_scan_dir(Path(self.active_project.path) / "blocks")
        registry.add_scan_dir(Path.home() / ".scistudio" / "blocks")
    registry.scan(include_monorepo=os.environ.get("SCISTUDIO_DEV") == "1")
    self.block_registry = registry


def refresh_type_registry(self: ApiRuntime) -> None:
    """Re-scan the TypeRegistry with the current active project's types dir.

    Issue #1332 / ARCHITECTURE.md §10 + §10.5: mirrors
    :func:`refresh_block_registry` so a project switch picks up
    ``<project>/types`` drop-in :class:`DataObject` subclasses and the
    user-wide ``~/.scistudio/types`` dir. Always rebuilds from scratch
    so a switch from project A to project B does not leak project A's
    types into project B.
    """
    import os

    registry = TypeRegistry()
    if self.active_project is not None:
        registry.add_scan_dir(Path(self.active_project.path) / "types")
    registry.add_scan_dir(Path.home() / ".scistudio" / "types")
    registry.scan_all(include_monorepo=os.environ.get("SCISTUDIO_DEV") == "1")
    self.type_registry = registry


def _init_lineage_store(self: ApiRuntime, project_path: Path) -> None:
    """Open the unified ADR-038 lineage store for the active project.

    The DB lives at ``<project>/.scistudio/lineage.db``. Schema creation is
    idempotent so first-time opens auto-bootstrap. Best-effort: a failure
    is logged and the store is set to ``None``, which makes the lineage
    recorder a no-op for this project.
    """
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
    try:
        from scistudio.core.metadata_store import _set_active_lineage_store

        _set_active_lineage_store(self.lineage_store)
    except Exception:
        logger.debug(
            "ADR-038: failed to publish lineage store to shim (non-fatal)",
            exc_info=True,
        )


def _init_metadata_store(self: ApiRuntime, project_path: Path) -> None:
    """Install the deprecation-shim :class:`MetadataStore` (ADR-038 §6)."""
    try:
        from scistudio.core.metadata_store import (
            MetadataStore,
            get_metadata_store,
            set_metadata_store,
        )

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

        set_metadata_store(MetadataStore(legacy_db))
    except Exception:
        logger.warning(
            "ADR-038: Failed to install MetadataStore deprecation shim (non-fatal)",
            exc_info=True,
        )
        from scistudio.core.metadata_store import set_metadata_store

        set_metadata_store(None)


# ----------------------------------------------------------------------
# Project CRUD
# ----------------------------------------------------------------------


def create_project(
    self: ApiRuntime,
    name: str,
    description: str = "",
    parent_path: str | None = None,
) -> KnownProject:
    from . import KnownProject

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

    # Issue #879: scaffold an empty workflows/main.yaml so the
    # default 'main' workflow tab has a real on-disk file from the
    # moment the project is created.
    try:
        save_yaml(WorkflowDefinition(id="main"), project_path / "workflows" / "main.yaml")
    except Exception:
        logger.warning("Failed to scaffold workflows/main.yaml for project %s", project.id, exc_info=True)

    self.known_projects[project.id] = project
    self._save_known_projects()
    # ADR-039 §3.2 auto-init (D39-2.2b): degraded mode on failure so
    # that project creation never aborts because git is unavailable.
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
    # ADR-040 §3.8 prod-env agent provisioning wiring (create_project).
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


def list_projects(self: ApiRuntime) -> list[KnownProject]:
    self._load_known_projects()
    stale_ids = [
        pid
        for pid, entry in self.known_projects.items()
        if not Path(entry.path).is_dir() or not (Path(entry.path) / "project.yaml").is_file()
    ]
    if stale_ids:
        for pid in stale_ids:
            self.known_projects.pop(pid, None)
        self._save_known_projects()
    return sorted(
        self.known_projects.values(),
        key=lambda item: item.last_opened or "",
        reverse=True,
    )


def _load_project_from_path(self: ApiRuntime, project_path: Path) -> KnownProject:
    from . import KnownProject

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


def open_project(self: ApiRuntime, project_id_or_path: str) -> KnownProject:
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
    self.refresh_type_registry()
    self.refresh_block_registry()
    # ADR-048 SPEC 1: rebuild the previewer service so project-local
    # previewers and default declarations track the active project (FR-002).
    self.refresh_preview_service()
    self._init_metadata_store(Path(candidate.path))
    self._init_lineage_store(Path(candidate.path))
    self.reset_version_state_for_project(Path(candidate.path))
    # ADR-039 §3.2 re-init hook
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
    # ADR-040 §3.8 idempotent top-up wiring (open_project).
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
    # ADR-034: republish the MCP server port file into the newly active project.
    self._publish_mcp_port(Path(candidate.path))
    # ADR-040 Addendum 5 / #1488: restore ``active_workflow_id`` from the
    # newly opened project's ``.scistudio/active_workflow.json`` so the
    # chat agent's ``get_active_workflow_context`` tool reflects what the
    # user had last open in this project (not a stale value from the
    # previously opened project).
    self._load_active_workflow_id_from_disk()
    return candidate


def set_mcp_port(self: ApiRuntime, port: int | None, *, socket_path: Path | None = None) -> None:
    """Register the live MCP transport for publishing on project switch.

    Called once from the FastAPI ``lifespan`` after ``MCPServer.start()``.
    ``None`` clears the registration when no ``socket_path`` is provided
    (used during shutdown). On Windows, ``port`` points to the loopback MCP
    transport. On POSIX, ``socket_path`` points to the bound Unix socket.
    """
    self._mcp_port = port
    self._mcp_socket_path = socket_path
    if self.active_project is not None:
        self._publish_mcp_port(Path(self.active_project.path))


def _publish_mcp_port(self: ApiRuntime, project_dir: Path) -> None:
    """Publish the live MCP transport under ``<project>/.scistudio/``.

    Best-effort: failures are logged and swallowed (e.g. read-only
    project root) so they cannot break ``open_project``.
    """
    try:
        target_dir = project_dir / ".scistudio"
        target_dir.mkdir(parents=True, exist_ok=True)
        port_file = target_dir / "mcp.sock.port"
        path_file = target_dir / "mcp.sock.path"
        if self._mcp_port is not None:
            port_file.write_text(str(self._mcp_port), encoding="utf-8")
            if path_file.exists():
                path_file.unlink()
        elif self._mcp_socket_path is not None:
            path_file.write_text(str(self._mcp_socket_path), encoding="utf-8")
            if port_file.exists():
                port_file.unlink()
        else:
            for stale in (port_file, path_file):
                if stale.exists():
                    stale.unlink()
    except OSError:
        logger.warning(
            "ApiRuntime: could not publish MCP transport to %s/.scistudio/",
            project_dir,
            exc_info=True,
        )


# ADR-040 Addendum 5 / #1488: active-workflow-id persistence.
#
# The chat agent's ``get_active_workflow_context`` MCP tool reads
# ``ApiRuntime.active_workflow_id`` so the agent knows which workflow the
# user is editing. We mirror that field to disk at
# ``<project>/.scistudio/active_workflow.json`` so:
#   * the value survives backend restart (the GUI does not have to
#     re-POST on every reconnect), and
#   * project switches restore the workflow the user had last open in
#     that project rather than carrying the prior project's id over.
#
# The file uses the same ``<project>/.scistudio/`` directory as the
# MCP port file (see ``_publish_mcp_port``) and is .gitignored as
# per-developer state, not workflow source.
_ACTIVE_WORKFLOW_FILENAME = "active_workflow.json"


def _load_active_workflow_id_from_disk(self: ApiRuntime) -> None:
    """Read the persisted ``active_workflow_id`` for the active project.

    Called from :func:`open_project` after the MCP port publish so the
    field reflects the workflow that was last active in the newly
    opened project. Missing file / malformed JSON / OSError leave the
    field at ``None`` — a stale or absent persistence file MUST NOT
    break project open.
    """
    if self.active_project is None:
        self.active_workflow_id = None
        return
    target = Path(self.active_project.path) / ".scistudio" / _ACTIVE_WORKFLOW_FILENAME
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError:
        self.active_workflow_id = None
        return
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning(
            "ApiRuntime: malformed %s — clearing active_workflow_id",
            target,
        )
        self.active_workflow_id = None
        return
    value = parsed.get("workflow_id") if isinstance(parsed, dict) else None
    self.active_workflow_id = value if isinstance(value, str) and value else None


def _publish_active_workflow_id(self: ApiRuntime) -> None:
    """Write the current ``active_workflow_id`` to the active project's
    ``.scistudio/active_workflow.json``.

    Best-effort: failures are logged and swallowed (e.g. read-only
    project root) so a persistence-layer issue cannot break the chat
    agent's POST-to-update flow.
    """
    if self.active_project is None:
        return
    target_dir = Path(self.active_project.path) / ".scistudio"
    target = target_dir / _ACTIVE_WORKFLOW_FILENAME
    payload = {"workflow_id": self.active_workflow_id}
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        logger.warning(
            "ApiRuntime: could not publish active_workflow_id to %s",
            target,
            exc_info=True,
        )


def set_active_workflow_id(self: ApiRuntime, workflow_id: str | None) -> None:
    """Update the in-memory ``active_workflow_id`` and persist to disk.

    Callers must pass either a non-empty workflow id or ``None``; empty
    strings are normalised to ``None`` so the MCP tool never reports
    a meaningless empty value to the agent. Persistence is best-effort
    — see :func:`_publish_active_workflow_id`.
    """
    normalised = workflow_id if isinstance(workflow_id, str) and workflow_id else None
    self.active_workflow_id = normalised
    self._publish_active_workflow_id()


def update_project(
    self: ApiRuntime,
    project_id_or_path: str,
    *,
    name: str | None = None,
    description: str | None = None,
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


def delete_project(self: ApiRuntime, project_id_or_path: str) -> None:
    project = self.open_project(project_id_or_path)
    project_path = Path(project.path).resolve()
    if not project_path.exists():
        self.known_projects.pop(project.id, None)
        self._save_known_projects()
        return
    if project_path == Path(project_path.anchor):
        raise ValueError("Refusing to delete drive root")
    if not (project_path / "project.yaml").is_file():
        logger.warning("Removing invalid project entry (no project.yaml): %s", project_path)
        self.known_projects.pop(project.id, None)
        if self.active_project is not None and self.active_project.id == project.id:
            self.active_project = None
            self.data_catalog = {}
        self._save_known_projects()
        return
    logger.warning("Deleting project directory: %s", project_path)
    # P1-3 (Phase 3.5 integration audit): UNION of ADR-038 lineage close
    # + ADR-039 _rmtree_force.
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


def project_response(self: ApiRuntime, project: KnownProject) -> dict[str, Any]:
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


def require_active_project(self: ApiRuntime) -> KnownProject:
    if self.active_project is None:
        raise RuntimeError("No project is currently open.")
    return self.active_project


def list_project_workflows(self: ApiRuntime, project: KnownProject | None = None) -> list[str]:
    project = project or self.require_active_project()
    workflows_dir = Path(project.path) / "workflows"
    return sorted(path.stem for path in workflows_dir.glob("*.yaml"))
