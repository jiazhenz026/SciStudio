"""Workflow + file-upload method implementations.

Issue #1430 / umbrella #1427: behavior unchanged. See ``_projects.py``
docstring for the free-function-bound-as-method pattern.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from scistudio.core.storage.ref import StorageReference
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition
from scistudio.workflow.serializer import absolutify_paths, load_yaml, relativify_paths, save_yaml

if TYPE_CHECKING:
    from . import ApiRuntime

logger = logging.getLogger(__name__)


def workflow_path(self: ApiRuntime, workflow_id: str) -> Path:
    project = self.require_active_project()
    return Path(project.path) / "workflows" / f"{workflow_id}.yaml"


def save_workflow(self: ApiRuntime, payload: dict[str, Any]) -> WorkflowDefinition:
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

    # #1518 (DSN-2): ``validate_workflow`` previously only ``logger.warning``-ed
    # and saved anyway, so an ill-typed / cyclic / contract-violating graph
    # persisted cleanly and only failed deep inside a block at run time. Editor
    # saves still need to accept incomplete draft graphs, so we validate in
    # ``draft`` mode: structural / edge / cycle / type / cardinality / boundary
    # problems remain hard errors, but config- and connection-completeness
    # checks (unconnected required ports, a not-yet-configured CodeBlock
    # ``script_path``, etc.) are deferred to run start, which re-validates the
    # loaded graph in strict mode (``runtime._runs.start_workflow``). This stops
    # the editor from throwing "Field required" while the user is still wiring up
    # a freshly dropped node. The route layer maps raised ``ValueError`` to HTTP
    # 422 (api/routes/workflows.py create/update handlers).
    diagnostics = validate_workflow(definition, registry=self.block_registry, mode="draft")
    warnings = [d for d in diagnostics if str(d).startswith("Warning:")]
    hard_errors = [d for d in diagnostics if not str(d).startswith("Warning:")]
    if warnings:
        logger.warning("Workflow validation warnings: %s", "; ".join(str(w) for w in warnings))
    if hard_errors:
        raise ValueError("Workflow validation failed: " + "; ".join(str(e) for e in hard_errors))

    path = self.workflow_path(definition.id)
    save_yaml(definition, path)
    # ADR-034 Phase 2: tell the FS watcher this write came from us so it
    # does not echo a workflow.changed event back to the canvas.
    self.mark_workflow_self_write(path)
    return definition


def mark_workflow_self_write(self: ApiRuntime, path: Path) -> None:
    """Tell the FS watcher *path* was a first-party write; suppress its echo.

    ADR-034 Phase 2. Centralised on the runtime so first-party writers — the
    canvas save here and the agent MCP workflow-write tool — call it through the
    injected runtime instead of importing ``api.routes.workflow_watcher``
    directly. The latter inverts the ai->api layer boundary (the AI MCP tool
    lives in the ``ai`` layer); routing through the runtime keeps the import
    edge inside the ``api`` layer (#1591 / #1597).
    """
    try:
        from scistudio.api.routes.workflow_watcher import mark_self_write

        mark_self_write(path)
    except Exception:
        logger.warning("workflow_watcher: mark_self_write failed for %s", path, exc_info=True)


def load_workflow(self: ApiRuntime, workflow_id: str) -> WorkflowDefinition:
    path = self.workflow_path(workflow_id)
    if not path.exists():
        raise FileNotFoundError(f"Workflow not found: {workflow_id}")
    definition = load_yaml(path)

    project_dir = self.active_project.path if self.active_project else None
    if project_dir:
        for node in definition.nodes:
            node.config = self._absolutify_node_config(node.config, node.block_type, project_dir)

    return definition


def load_workflow_by_path(self: ApiRuntime, rel_path: str) -> WorkflowDefinition:
    """Load a workflow YAML by project-relative path (ADR-044 US1 AS3).

    Unlike :func:`load_workflow` (which resolves ``workflows/<id>.yaml`` by id),
    this opens any workflow file under the project — notably a referenced
    subworkflow under ``<project>/subworkflows/`` — so double-clicking a
    SubWorkflowBlock can open its ``config.ref.path`` regardless of folder.
    The path is constrained to stay inside the project root.
    """
    project = self.require_active_project()
    project_root = Path(project.path).resolve()
    candidate = (project_root / rel_path).resolve()
    if project_root != candidate and project_root not in candidate.parents:
        raise ValueError(f"Subworkflow path escapes the project: {rel_path!r}")
    if not candidate.is_file():
        raise FileNotFoundError(f"Workflow file not found: {rel_path}")

    definition = load_yaml(candidate)
    for node in definition.nodes:
        node.config = self._absolutify_node_config(node.config, node.block_type, str(project_root))
    return definition


def import_subworkflow_file(self: ApiRuntime, source_path: str) -> str:
    """ADR-044 FR-011: copy an external workflow file into the project.

    Copies *source_path* into ``<project>/subworkflows/`` (creating it if
    needed) and returns the project-relative path to record in a
    ``SubWorkflowBlock``'s ``config.ref.path``. On filename collision a numeric
    suffix is appended so two imports of the same external file produce two
    distinct project copies (US5 AS2). The returned path uses forward slashes
    for cross-platform YAML portability (#506).
    """
    project = self.require_active_project()
    src = Path(source_path)
    if not src.is_file():
        raise FileNotFoundError(f"Subworkflow file not found: {source_path}")

    dest_dir = Path(project.path) / "subworkflows"
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / src.name
    if dest.exists():
        counter = 1
        while True:
            candidate = dest_dir / f"{src.stem}_{counter}{src.suffix}"
            if not candidate.exists():
                dest = candidate
                break
            counter += 1

    shutil.copy2(src, dest)
    return str(PurePosixPath(dest.relative_to(Path(project.path))))


def _config_schema_for_block(self: ApiRuntime, block_type: str) -> dict[str, Any]:
    """Look up the config_schema for a block type from the registry."""
    spec = self.block_registry.get_spec(block_type)
    if spec is not None:
        return spec.config_schema
    return {"type": "object", "properties": {}}


def _relativify_node_config(
    self: ApiRuntime,
    config: dict[str, Any],
    block_type: str,
    project_dir: str | None,
) -> dict[str, Any]:
    """Convert absolute paths in node config to relative paths (#506)."""
    if not project_dir:
        return config
    schema = self._config_schema_for_block(block_type)
    return relativify_paths(config, project_dir, schema)


def _absolutify_node_config(
    self: ApiRuntime,
    config: dict[str, Any],
    block_type: str,
    project_dir: str | None,
) -> dict[str, Any]:
    """Resolve relative paths in node config to absolute paths (#506)."""
    if not project_dir:
        return config
    schema = self._config_schema_for_block(block_type)
    return absolutify_paths(config, project_dir, schema)


def delete_workflow(self: ApiRuntime, workflow_id: str) -> bool:
    """Delete a workflow's YAML from disk.

    Returns ``True`` when a file was actually removed, ``False`` when no
    workflow file existed. The route uses this to decide whether to emit the
    versioned ``workflow.changed`` ``kind="deleted"`` event (#1462 / ADR-045
    §3.4) so a user-initiated delete is attributed to ``source="canvas"``
    rather than being mis-tagged ``source="external"`` by the FS watcher.
    """
    path = self.workflow_path(workflow_id)
    if path.exists():
        path.unlink()
        return True
    return False


def _upload_destination(self: ApiRuntime, filename: str) -> Path:
    project = self.require_active_project()
    safe_name = Path(filename).name  # strips all directory components
    if not safe_name or safe_name.startswith("."):
        raise ValueError(f"Invalid filename: {filename!r}")
    destination = Path(project.path) / "data" / "raw" / safe_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def stage_upload_file(self: ApiRuntime, filename: str) -> tuple[Path, Path]:
    """Return final and temporary same-directory paths for a streamed upload."""
    destination = self._upload_destination(filename)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".upload",
        delete=False,
    ) as staged:
        staged_path = Path(staged.name)
    return destination, staged_path


def discard_staged_upload(self: ApiRuntime, staged_path: Path) -> None:
    try:
        staged_path.unlink()
    except FileNotFoundError:
        return


def finish_staged_upload(self: ApiRuntime, destination: Path, staged_path: Path) -> dict[str, Any]:
    if destination.parent != staged_path.parent:
        raise ValueError("staged upload must live beside the destination")
    staged_path.replace(destination)

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


def upload_file(self: ApiRuntime, filename: str, content: bytes) -> dict[str, Any]:
    destination, staged_path = self.stage_upload_file(filename)
    try:
        staged_path.write_bytes(content)
        return self.finish_staged_upload(destination, staged_path)
    except Exception:
        self.discard_staged_upload(staged_path)
        raise
