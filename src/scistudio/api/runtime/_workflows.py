"""Workflow + file-upload method implementations.

Issue #1430 / umbrella #1427: behavior unchanged. See ``_projects.py``
docstring for the free-function-bound-as-method pattern.
"""

from __future__ import annotations

import logging
from pathlib import Path
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
    # persisted cleanly and only failed deep inside a block at run time. Now
    # we partition the diagnostics: messages the validator prefixes with
    # ``"Warning:"`` (unknown block type, missing port — intentionally
    # non-fatal so an agent can save a partial graph mid-edit) stay as log
    # warnings; everything else (duplicate node id, cycle, type-incompatible
    # edge, dangling required input, variadic cardinality, duplicate
    # extension, CodeBlock/boundary capability errors) is a hard error that
    # rejects the save. The route layer maps the raised ``ValueError`` to
    # HTTP 422 (api/routes/workflows.py create/update handlers).
    diagnostics = validate_workflow(definition, registry=self.block_registry)
    warnings = [d for d in diagnostics if str(d).startswith("Warning:")]
    hard_errors = [d for d in diagnostics if not str(d).startswith("Warning:")]
    if warnings:
        logger.warning(
            "Workflow validation warnings: %s",
            "; ".join(str(w) for w in warnings),
        )
    if hard_errors:
        raise ValueError("Workflow validation failed: " + "; ".join(str(e) for e in hard_errors))

    path = self.workflow_path(definition.id)
    save_yaml(definition, path)
    # ADR-034 Phase 2: tell the FS watcher this write came from us so it
    # does not echo a workflow.changed event back to the canvas.
    try:
        from scistudio.api.routes.workflow_watcher import mark_self_write

        mark_self_write(path)
    except Exception:
        logger.warning("workflow_watcher: mark_self_write failed for %s", path, exc_info=True)
    return definition


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


def delete_workflow(self: ApiRuntime, workflow_id: str) -> None:
    path = self.workflow_path(workflow_id)
    if path.exists():
        path.unlink()


def upload_file(self: ApiRuntime, filename: str, content: bytes) -> dict[str, Any]:
    project = self.require_active_project()
    safe_name = Path(filename).name  # strips all directory components
    if not safe_name or safe_name.startswith("."):
        raise ValueError(f"Invalid filename: {filename!r}")
    destination = Path(project.path) / "data" / "raw" / safe_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)

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
