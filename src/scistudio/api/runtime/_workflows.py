"""Workflow + file-upload method implementations."""
# Maintainer context (kept outside generated API documentation):
# Workflow + file-upload method implementations.
#
# Issue #1430 / umbrella #1427: behavior unchanged. See ``_projects.py``
# docstring for the free-function-bound-as-method pattern.
# Development references: #1427, #1430.

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import yaml

from scistudio.core.storage.ref import StorageReference
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition
from scistudio.workflow.identity import (
    declared_id_for_file_name,
    is_path_identity,
    project_relative_path_for_identity,
    workflow_identity_for_path,
)
from scistudio.workflow.serializer import absolutify_paths, load_yaml, relativify_paths, save_yaml

if TYPE_CHECKING:
    from . import ApiRuntime

logger = logging.getLogger(__name__)


class WorkflowIdConflictError(ValueError):
    """A different project workflow file already declares this workflow id.

    a project must hold at most one file per workflow id — the
    canonical ``workflows/{id}.yaml``. A second file with a different
    filename but the same internal ``id`` breaks the per-project unique-id
    invariant: target/workflow discovery walks every ``workflows/*.yaml`` and
    surfaces phantom plot targets (whose nodes are not on the open canvas),
    and "which workflow is open" is tracked by id, not path. We reject the
    save/import that would create or perpetuate the collision instead of
    silently merging.
    """

    # Development references: #1836.

    def __init__(self, workflow_id: str, existing_path: Path) -> None:
        self.workflow_id = workflow_id
        self.existing_path = existing_path
        super().__init__(
            f"Workflow id {workflow_id!r} is already declared by "
            f"{existing_path.name!r} in this project. Workflow ids must be "
            "unique per project; rename or remove the conflicting file."
        )


def _read_declared_workflow_id(path: Path) -> str | None:
    """Best-effort read of a workflow file's declared ``id``.

    Lenient on purpose: a malformed or unreadable sibling must not block
    saving a well-formed workflow, so parse failures degrade to ``None``.
    """
    # Development references: #1836.
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    # Workflow YAML wraps its body under a top-level ``workflow:`` envelope
    # (see ``serializer.dump_yaml_str``); tolerate a flat shape too.
    body = data.get("workflow")
    if not isinstance(body, dict):
        body = data
    wid = body.get("id")
    return str(wid) if wid is not None else None


def workflow_path(self: ApiRuntime, workflow_id: str) -> Path:
    """Return the file a workflow run identity names.

    A stem names ``workflows/<stem>.yaml``; the path form (``@subworkflows@qc.yaml``)
    names that project-relative file. See :mod:`scistudio.workflow.identity`.
    The path form is confined to the project root.
    """
    # Development references: #2394.
    project = self.require_active_project()
    root = Path(project.path)
    relative = project_relative_path_for_identity(workflow_id)
    if not is_path_identity(workflow_id):
        return root / relative
    candidate = (root / relative).resolve()
    resolved_root = root.resolve()
    if resolved_root not in candidate.parents:
        raise ValueError(f"Workflow path escapes the project: {relative}")
    return root / relative


def workflow_identity_for_file(self: ApiRuntime, path: str | Path) -> str:
    """Return the run identity of a workflow file inside the active project.

    *path* may be absolute or project-relative. Raises ``ValueError`` when it is
    outside the project.
    """
    # Development references: #2394.
    project = self.require_active_project()
    return workflow_identity_for_path(project.path, path)


def canonical_workflow_identity(self: ApiRuntime, workflow_id: str) -> str:
    """Return the canonical spelling of a run identity.

    Two spellings can name one file (``@workflows@main.yaml`` and ``main``);
    the run guard, lineage and events must all see the same one.
    """
    # Development references: #2394.
    try:
        return self.workflow_identity_for_file(self.workflow_path(workflow_id))
    except ValueError:
        return workflow_id


def workflow_relative_path(self: ApiRuntime, workflow_id: str) -> str:
    """Return the project-relative POSIX path a run identity names."""
    # Development references: #2394.
    return str(project_relative_path_for_identity(workflow_id))


def find_workflow_id_conflict(self: ApiRuntime, workflow_id: str) -> Path | None:
    """Return an existing project workflow file that declares *workflow_id*
    at a non-canonical path, else ``None``.

    The canonical home for a workflow is ``workflows/{id}.yaml``; that file
    (if present) is never a conflict with itself. Any *other* ``workflows/
    *.yaml`` whose internal ``id`` equals *workflow_id* is a duplicate-id
    collision and is returned so the caller can reject the save/import.
    """
    # Development references: #1836, #2394.
    project = self.active_project
    if project is None or is_path_identity(workflow_id):
        # A file outside ``workflows/<stem>.yaml`` is addressed by its path,
        # so its declared id cannot collide with a top-level workflow.
        return None
    workflows_dir = Path(project.path) / "workflows"
    if not workflows_dir.is_dir():
        return None
    try:
        canonical = self.workflow_path(workflow_id).resolve()
    except Exception:
        canonical = workflows_dir / f"{workflow_id}.yaml"
    for path in sorted(workflows_dir.glob("*.yaml")):
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved == canonical:
            continue
        if _read_declared_workflow_id(path) == workflow_id:
            return path
    return None


def save_workflow(self: ApiRuntime, payload: dict[str, Any]) -> WorkflowDefinition:
    """Validate and write a workflow addressed by the run identity ``payload["id"]``.

    A top-level workflow is written to ``workflows/<id>.yaml`` declaring that id.
    A file addressed by its path form keeps the ``id:`` it already declares (the
    file name when it declares none), so saving an expanded subworkflow tab
    never renames the subworkflow or writes ``workflows/<declared id>.yaml``.
    The returned definition carries the declared id that was written.
    """
    # Development references: #506, #2394.
    # #506: relativify paths in node configs before persisting YAML.
    project_dir = self.active_project.path if self.active_project else None
    identity = str(payload["id"])
    path = self.workflow_path(identity)
    declared_id = identity
    if is_path_identity(identity):
        # The path form only addresses files that already exist (an opened
        # subworkflow); new workflows are created under ``workflows/``.
        if not path.is_file():
            raise FileNotFoundError(f"Workflow file not found: {self.workflow_relative_path(identity)}")
        declared_id = _read_declared_workflow_id(path) or declared_id_for_file_name(path.name)

    definition = WorkflowDefinition(
        id=declared_id,
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
    # ``project_dir`` (#1967): node configs were just relativified above, so any
    # project-relative path in them (CodeBlock ``script_path``) needs the active
    # project root to resolve. Passing it keeps the validator off its
    # process-working-directory fallback, which in the packaged desktop app is
    # the app's ``Resources`` directory rather than the user's project.
    diagnostics = validate_workflow(
        definition,
        registry=self.block_registry,
        mode="draft",
        project_dir=project_dir,
    )
    warnings = [d for d in diagnostics if str(d).startswith("Warning:")]
    hard_errors = [d for d in diagnostics if not str(d).startswith("Warning:")]
    if warnings:
        logger.warning("Workflow validation warnings: %s", "; ".join(str(w) for w in warnings))
    if hard_errors:
        raise ValueError("Workflow validation failed: " + "; ".join(str(e) for e in hard_errors))

    # #1836: enforce per-project unique workflow id at save time.
    conflict = find_workflow_id_conflict(self, identity)
    if conflict is not None:
        raise WorkflowIdConflictError(definition.id, conflict)

    # #1953: register a *pending* first-party write signature BEFORE the atomic
    # rename inside ``save_yaml``. ``save_yaml`` writes a tempfile then
    # ``os.replace``s it onto ``path``; on Linux/inotify that rename surfaces to
    # the watchdog observer thread immediately, before the route layer's
    # ``_emit_workflow_changed`` runs its post-write ``mark_workflow_first_party_write``.
    # The observer thread then races ahead of the signature and emits a phantom
    # ``source=external`` event, which the canvas surfaces as a spurious
    # "Workflow changed elsewhere" dialog. A pending signature is path-only
    # matched (``exists is None`` -> match) so it suppresses the echo regardless
    # of the race, mtime, or event kind. This mirrors the already-correct pattern
    # in ``routes/projects.py`` (file write) and the agent MCP ``write_workflow``
    # tool.
    kind = "modified" if path.exists() else "created"
    # Import the entity-class constant lazily: ``runtime/__init__`` imports this
    # module during its own initialisation, so a top-level import would cycle.
    from scistudio.api.runtime import WORKFLOW_ENTITY_CLASS

    self.mark_entity_first_party_write(
        WORKFLOW_ENTITY_CLASS,
        identity,
        self.current_workflow_version(identity),
        path=path,
        kind=kind,
        pending=True,
    )
    save_yaml(definition, path)
    # ADR-034 Phase 2: tell the FS watcher this write came from us so it
    # does not echo a workflow.changed event back to the canvas.
    self.mark_workflow_self_write(path)
    return definition


def mark_workflow_self_write(self: ApiRuntime, path: Path) -> None:
    """Tell the FS watcher *path* was a first-party write; suppress its echo.

    Centralised on the runtime so first-party writers — the
    canvas save here and the agent MCP workflow-write tool — call it through the
    injected runtime instead of importing ``api.routes.workflow_watcher``
    directly. The latter inverts the ai->api layer boundary (the AI MCP tool
    lives in the ``ai`` layer); routing through the runtime keeps the import
    edge inside the ``api`` layer.
    """
    # Development references: #1591, #1597, ADR-034.
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
    """Load a workflow YAML by project-relative path.

    Unlike :func:`load_workflow` (which resolves ``workflows/<id>.yaml`` by id),
    this opens any workflow file under the project — notably a referenced
    subworkflow under ``<project>/subworkflows/`` — so double-clicking a
    SubWorkflowBlock can open its ``config.ref.path`` regardless of folder.
    The path is constrained to stay inside the project root.
    """
    # Maintainer context:
    # Load a workflow YAML by project-relative path (US1 AS3).
    # Development references: ADR-044.
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
    """Copy an external workflow file into the project.

    Copies *source_path* into ``<project>/subworkflows/`` (creating it if
    needed) and returns the project-relative path to record in a
    ``SubWorkflowBlock``'s ``config.ref.path``. On filename collision a numeric
    suffix is appended so two imports of the same external file produce two
    distinct project copies. The returned path uses forward slashes
    for cross-platform YAML portability.
    """
    # Maintainer context:
    # Copies *source_path* into ``<project>/subworkflows/`` (creating it if
    # needed) and returns the project-relative path to record in a
    # ``SubWorkflowBlock``'s ``config.ref.path``. On filename collision a numeric
    # suffix is appended so two imports of the same external file produce two
    # distinct project copies (US5 AS2). The returned path uses forward slashes
    # for cross-platform YAML portability.
    # Development references: #506, ADR-044, FR-011.
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

    # ADR-044 Addendum 1: a referenced file with no authored ``exposed_ports``
    # surfaces zero handles on the parent canvas and leaves its open boundary
    # ports unconnectable (so the flattened run fails with "required input port
    # has no incoming connection"). On import, auto-derive an exposed-port
    # surface from the pipeline's open ports — every input with no incoming edge
    # and every output with no outgoing edge — and write it into the project
    # copy. Only when the file declares none, so a hand-authored surface stays
    # authoritative.
    from scistudio.workflow.subworkflow_ports import derive_exposed_ports

    try:
        imported = load_yaml(dest)
    except Exception:
        imported = None
    if imported is not None and imported.exposed_ports is None:
        derived = derive_exposed_ports(imported, registry=self.block_registry)
        if derived.inputs or derived.outputs:
            imported.exposed_ports = derived
            save_yaml(imported, dest)

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
    """Convert absolute paths in node config to relative paths."""
    # Development references: #506.
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
    """Resolve relative paths in node config to absolute paths."""
    # Development references: #506.
    if not project_dir:
        return config
    schema = self._config_schema_for_block(block_type)
    return absolutify_paths(config, project_dir, schema)


def delete_workflow(self: ApiRuntime, workflow_id: str) -> bool:
    """Delete a workflow's YAML from disk.

    Returns ``True`` when a file was actually removed, ``False`` when no
    workflow file existed. The route uses this to decide whether to emit the
    versioned ``workflow.changed`` ``kind="deleted"`` event so a user-initiated delete is attributed to ``source="canvas"``
    rather than being mis-tagged ``source="external"`` by the FS watcher.
    """
    # Development references: #1462, #2448, ADR-045.
    path = self.workflow_path(workflow_id)
    if path.exists():
        identity = self.canonical_workflow_identity(workflow_id)
        path.unlink()
        # #2448: the pause checkpoint belongs to the deleted file; a new
        # workflow later saved under the same name must not inherit it.
        self.remove_workflow_pause_state(identity)
        return True
    return False


def remove_workflow_pause_state(self: ApiRuntime, workflow_id: str) -> None:
    """Delete the pause/resume checkpoint directory of a workflow identity.

    Called when the workflow file is deleted or moved: the checkpoint
    describes that file's last run, and "Run from here" must not reuse it for
    whatever later takes the identity. A missing directory is not an error.
    """
    # Development references: #2448.
    project = self.require_active_project()
    remove_pause_dir(project.path, workflow_id)


def remove_pause_dir(project_root: str | Path, workflow_id: str) -> None:
    """Delete ``<project_root>/.scistudio/pause/<workflow_id>/`` when it exists."""
    # Development references: #2448.
    from ._runs import pause_dir_for

    pause_dir = pause_dir_for(project_root, workflow_id)
    if pause_dir.is_dir():
        shutil.rmtree(pause_dir, ignore_errors=True)


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
