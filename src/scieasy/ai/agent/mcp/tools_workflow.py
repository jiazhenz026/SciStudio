"""Category (a) MCP tools — workflow inspection and execution (9 stubs).

T-ECA-201 (scaffold). Implementation lands in T-ECA-202. See
``docs/specs/embedded-coding-agent-spec.md`` §6 T-ECA-202 for the
per-tool implementation notes.

All stubs raise :class:`NotImplementedError`. Signatures, return-type
annotations, and docstrings are the contract for T-ECA-202.
"""

from __future__ import annotations

from typing import Any


def list_blocks() -> list[dict[str, Any]]:
    """List every block type registered in the active block registry.

    Calls ``get_block_registry().all_specs()`` and serialises each
    ``BlockSpec`` to a JSON-safe dict (name, base_category, subcategory,
    version, description, ports, config_schema).

    Returns
    -------
    list of dict
        One entry per registered block type; order is implementation-
        defined but stable within a process lifetime.

    Side effects
    ------------
    None. Read-only.

    Raises
    ------
    NotImplementedError
        Until T-ECA-202 lands.
    """
    raise NotImplementedError("list_blocks lands in T-ECA-202")


def get_block_schema(type_name: str) -> dict[str, Any]:
    """Return the I/O ports and ``config_schema`` for one block type.

    Parameters
    ----------
    type_name
        The block's registered type name (matches ``BlockSpec.name``).

    Returns
    -------
    dict
        ``{"ports": {...}, "config_schema": {...}, "metadata": {...}}``
        — ``ports`` describes input and output port type signatures;
        ``config_schema`` is the JSON Schema produced by the block's
        ``ConfigModel``; ``metadata`` carries description, version,
        and other static fields.

    Side effects
    ------------
    None. Read-only.

    Raises
    ------
    KeyError
        If *type_name* is not registered (implementation should map
        this to a JSON-RPC error in the dispatcher).
    NotImplementedError
        Until T-ECA-202 lands.
    """
    raise NotImplementedError("get_block_schema lands in T-ECA-202")


def list_types() -> dict[str, Any]:
    """Return the full data-type registry hierarchy.

    Calls ``get_type_registry().all_types()``. Includes base types and
    every plugin-registered subtype with parentage edges so the agent
    can reason about type compatibility for port wiring.

    Returns
    -------
    dict
        Hierarchical representation; exact shape defined in
        T-ECA-202. At minimum each entry has ``name``, ``parent``,
        ``description``.

    Side effects
    ------------
    None. Read-only.

    Raises
    ------
    NotImplementedError
        Until T-ECA-202 lands.
    """
    raise NotImplementedError("list_types lands in T-ECA-202")


def get_workflow(path: str) -> dict[str, Any]:
    """Load a workflow YAML and return its decoded representation.

    Calls ``workflow.serializer.load_yaml(path)`` then
    ``WorkflowDefinition.model_dump()``. Used by the agent to read
    current node configuration before proposing edits.

    Parameters
    ----------
    path
        Filesystem path to the workflow YAML file. Resolved relative
        to the active project workspace.

    Returns
    -------
    dict
        Pydantic-dumped workflow definition (nodes, edges, metadata).

    Side effects
    ------------
    None. Read-only.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    NotImplementedError
        Until T-ECA-202 lands.
    """
    raise NotImplementedError("get_workflow lands in T-ECA-202")


def validate_workflow(yaml_or_path: str) -> dict[str, Any]:
    """Validate a workflow (inline YAML or path) against the runtime rules.

    Heuristic: if *yaml_or_path* starts with ``name:`` or contains
    ``nodes:``, treat as inline YAML; otherwise treat as a filesystem
    path. Calls ``workflow.validator.validate_workflow()``.

    Parameters
    ----------
    yaml_or_path
        Either an inline YAML document or a path to one.

    Returns
    -------
    dict
        ``{"valid": bool, "errors": [str, ...]}``. Errors are
        human-readable strings produced by the validator.

    Side effects
    ------------
    None. Read-only.

    Raises
    ------
    NotImplementedError
        Until T-ECA-202 lands.
    """
    raise NotImplementedError("validate_workflow lands in T-ECA-202")


def write_workflow(path: str, yaml: str) -> dict[str, Any]:
    """Persist a workflow YAML to disk with a file lock.

    File-locked atomic write per ADR-033 OQ7: acquire ``path + ".lock"``
    via ``filelock.FileLock`` (timeout 10s), write to a temp file, then
    rename. Logs an INFO line summarising the diff (per Phase 2 audit
    item).

    Goes through the permission policy: this is a write-class tool and
    triggers ``PreToolUse`` approval in STRICT mode.

    Parameters
    ----------
    path
        Destination filesystem path.
    yaml
        The full new workflow YAML document.

    Returns
    -------
    dict
        ``{"path": str, "bytes_written": int, "diff_summary": str}``.

    Side effects
    ------------
    Writes to disk. Acquires a file lock.

    Raises
    ------
    PermissionError
        If the permission policy denies the call.
    NotImplementedError
        Until T-ECA-202 lands.
    """
    raise NotImplementedError("write_workflow lands in T-ECA-202")


def run_workflow(path: str) -> dict[str, Any]:
    """Submit a workflow for execution and return its run identifier.

    Calls ``await scheduler.execute(workflow)`` and returns the
    assigned ``run_id`` *immediately*; does not wait for the run to
    finish. Progress is observable via :func:`get_run_status` and the
    main event bus.

    Write-class tool: requires permission approval in STRICT mode.

    Parameters
    ----------
    path
        Filesystem path to the workflow YAML file.

    Returns
    -------
    dict
        ``{"run_id": str, "status": "queued"}``.

    Side effects
    ------------
    Spawns a workflow run on the DAG scheduler.

    Raises
    ------
    PermissionError
        If the permission policy denies the call.
    NotImplementedError
        Until T-ECA-202 lands.
    """
    raise NotImplementedError("run_workflow lands in T-ECA-202")


def cancel_run(run_id: str) -> dict[str, Any]:
    """Request cancellation of an in-flight workflow run.

    Emits a ``CANCEL_WORKFLOW_REQUEST`` event on the engine event bus.
    Cancellation is cooperative; the call returns once the request has
    been queued, not once the run actually stops.

    Write-class tool: requires permission approval in STRICT mode.

    Parameters
    ----------
    run_id
        Identifier returned by :func:`run_workflow`.

    Returns
    -------
    dict
        ``{"run_id": str, "cancel_requested": bool}``.

    Side effects
    ------------
    Emits an event on the engine event bus.

    Raises
    ------
    KeyError
        If *run_id* is not known to the scheduler.
    NotImplementedError
        Until T-ECA-202 lands.
    """
    raise NotImplementedError("cancel_run lands in T-ECA-202")


def get_run_status(run_id: str) -> dict[str, Any]:
    """Return the current status of a workflow run.

    Reads the scheduler's in-memory run-state dict. Used by the agent
    to poll for completion after :func:`run_workflow`.

    Parameters
    ----------
    run_id
        Identifier returned by :func:`run_workflow`.

    Returns
    -------
    dict
        ``{"run_id": str, "state": str, "progress": dict, "errors": [...]}``
        where ``state`` is one of ``"queued"``, ``"running"``,
        ``"succeeded"``, ``"failed"``, ``"cancelled"``.

    Side effects
    ------------
    None. Read-only.

    Raises
    ------
    KeyError
        If *run_id* is not known.
    NotImplementedError
        Until T-ECA-202 lands.
    """
    raise NotImplementedError("get_run_status lands in T-ECA-202")
