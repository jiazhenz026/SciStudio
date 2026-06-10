"""YAML serialisation -- load and save workflow definitions."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from scistudio.utils.atomic_io import atomic_write_text
from scistudio.workflow.definition import WorkflowDefinition
from scistudio.workflow.schema import WorkflowFileModel, WorkflowModel

# ---------------------------------------------------------------------------
# Path portability helpers (#506)
# ---------------------------------------------------------------------------


def _path_config_keys(config_schema: dict[str, Any]) -> set[str]:
    """Return config keys whose ``ui_widget`` indicates a path field."""
    props = config_schema.get("properties", {})
    keys: set[str] = set()
    for key, schema in props.items():
        widget = schema.get("ui_widget", "")
        if widget in ("file_browser", "directory_browser"):
            keys.add(key)
    return keys


def relativify_paths(
    config: dict[str, Any],
    project_dir: str | Path,
    config_schema: dict[str, Any],
) -> dict[str, Any]:
    """Convert absolute paths under *project_dir* to forward-slash relative paths.

    Only fields identified by ``ui_widget`` in *config_schema* are considered.
    Paths outside *project_dir* are left unchanged.
    """
    path_keys = _path_config_keys(config_schema)
    if not path_keys:
        return config

    project = Path(project_dir).resolve()
    result = dict(config)
    for key in path_keys:
        value = result.get(key)
        if not isinstance(value, str) or not value:
            continue
        try:
            resolved = Path(value).resolve()
            relative = resolved.relative_to(project)
            # Always use forward slashes in YAML regardless of OS.
            result[key] = str(PurePosixPath(relative))
        except (ValueError, OSError):
            # Path is not under project_dir -- keep as-is.
            pass
    return result


def absolutify_paths(
    config: dict[str, Any],
    project_dir: str | Path,
    config_schema: dict[str, Any],
) -> dict[str, Any]:
    """Resolve relative paths in *config* to absolute paths under *project_dir*.

    Already-absolute paths are returned unchanged (backward compatible with
    workflows saved before #506).
    """
    path_keys = _path_config_keys(config_schema)
    if not path_keys:
        return config

    project = Path(project_dir).resolve()
    result = dict(config)
    for key in path_keys:
        value = result.get(key)
        if not isinstance(value, str) or not value:
            continue
        p = Path(value)
        if not p.is_absolute():
            result[key] = str((project / value).resolve())
    return result


def load_yaml(path: str | Path) -> WorkflowDefinition:
    """Deserialise a workflow definition from a YAML file.

    Parameters
    ----------
    path:
        Path to the YAML file to read.

    Returns
    -------
    WorkflowDefinition
        A validated ``WorkflowDefinition`` instance.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    yaml.YAMLError
        If the file is not valid YAML.
    pydantic.ValidationError
        If the YAML content does not match the expected schema.
    """
    text = Path(path).read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    validated = WorkflowFileModel.model_validate(raw)
    return validated.workflow.to_definition()


def save_yaml(workflow: WorkflowDefinition, path: str | Path) -> None:
    """Serialise a workflow definition to a YAML file.

    Parameters
    ----------
    workflow:
        The workflow object to persist.
    path:
        Destination file path (will be created or overwritten).
    """
    model = WorkflowModel.from_definition(workflow)
    file_model = WorkflowFileModel(workflow=model)
    data = file_model.model_dump(exclude_none=True)
    # BUG-8 (#1543): the FS watcher and concurrent readers (canvas + agent
    # via update_workflow / import_* routes) read this file while it is
    # written. A direct ``Path.write_text`` let a reader observe truncated
    # YAML (surfaced as a 422 from get_workflow's yaml.YAMLError handler),
    # and two writers raced last-write-wins. Atomic temp-then-os.replace
    # makes every reader see either the whole old file or the whole new one.
    atomic_write_text(
        Path(path),
        yaml.safe_dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
