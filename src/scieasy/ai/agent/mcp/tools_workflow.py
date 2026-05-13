"""Category (a) MCP tools — workflow inspection and execution (9 tools).

T-ECA-202. See ``docs/specs/embedded-coding-agent-spec.md`` §6 T-ECA-202.

All write-class tools (``write_workflow``, ``run_workflow``,
``cancel_run``) acquire a file lock per ADR-033 OQ7 and log an INFO
record with a diff summary. ``run_workflow`` returns the assigned
``run_id`` immediately — completion is observable via
:func:`get_run_status`.
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

from scieasy.ai.agent.mcp._context import _resolve_project_path, get_context

logger = logging.getLogger(__name__)


_LOCK_TIMEOUT_SECONDS = 10.0
"""ADR-033 OQ7: file lock timeout for atomic-write tools."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec_to_dict(spec: Any) -> dict[str, Any]:
    """Serialise a :class:`BlockSpec` (dataclass) to a JSON-safe dict.

    ``input_ports`` and ``output_ports`` carry :class:`Port` instances
    that are not natively JSON-serialisable; we project them to a
    minimal {name, type_name, required} envelope.
    """
    if dataclasses.is_dataclass(spec) and not isinstance(spec, type):
        raw = dataclasses.asdict(spec)
    else:  # pragma: no cover - non-dataclass spec
        raw = dict(spec.__dict__)
    raw["input_ports"] = [_port_to_dict(p) for p in (spec.input_ports or [])]
    raw["output_ports"] = [_port_to_dict(p) for p in (spec.output_ports or [])]
    return raw


def _port_to_dict(port: Any) -> dict[str, Any]:
    """Project a :class:`Port` to a JSON-safe dict."""
    if isinstance(port, dict):
        return port
    type_obj = getattr(port, "type", None)
    type_name = getattr(type_obj, "__name__", str(type_obj)) if type_obj is not None else ""
    return {
        "name": getattr(port, "name", ""),
        "type": type_name,
        "required": bool(getattr(port, "required", False)),
    }


def _atomic_write_text(path: Path, text: str) -> int:
    """Write *text* to *path* via tempfile + rename.

    Returns the number of bytes written. Acquires no lock — the caller
    must hold the :class:`FileLock` for the path before invoking this.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        # Best-effort cleanup of orphan tmp file.
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return len(text.encode("utf-8"))


def _diff_summary(old: str, new: str) -> str:
    """Compact diff summary used in INFO log + return envelope.

    Three integers ('lines_added', 'lines_removed', 'total_bytes').
    """
    old_lines = old.splitlines() if old else []
    new_lines = new.splitlines()
    # Cheap line-set diff; we don't need full diff fidelity for a log line.
    added = max(0, len(new_lines) - len(old_lines))
    removed = max(0, len(old_lines) - len(new_lines))
    return f"+{added}/-{removed} lines, {len(new.encode('utf-8'))} bytes"


# ---------------------------------------------------------------------------
# (a.1) list_blocks
# ---------------------------------------------------------------------------


def list_blocks() -> list[dict[str, Any]]:
    """List every block type registered in the active block registry.

    Returns
    -------
    list of dict
        One entry per registered block type with the fields of
        :class:`BlockSpec` (name, base_category, subcategory, version,
        description, input_ports, output_ports, config_schema, ...).
    """
    ctx = get_context()
    specs = ctx.block_registry.all_specs()
    return [_spec_to_dict(spec) for spec in specs.values()]


# ---------------------------------------------------------------------------
# (a.2) get_block_schema
# ---------------------------------------------------------------------------


def get_block_schema(type_name: str) -> dict[str, Any]:
    """Return the I/O ports and ``config_schema`` for one block type.

    Raises
    ------
    KeyError
        If *type_name* is not registered.
    """
    ctx = get_context()
    spec = ctx.block_registry.get_spec(type_name)
    if spec is None:
        raise KeyError(f"Block type '{type_name}' is not registered")
    return {
        "type_name": spec.name,
        "ports": {
            "input": [_port_to_dict(p) for p in (spec.input_ports or [])],
            "output": [_port_to_dict(p) for p in (spec.output_ports or [])],
        },
        "config_schema": spec.config_schema or {"type": "object", "properties": {}},
        "metadata": {
            "description": spec.description,
            "version": spec.version,
            "base_category": spec.base_category,
            "subcategory": spec.subcategory,
        },
    }


# ---------------------------------------------------------------------------
# (a.3) list_types
# ---------------------------------------------------------------------------


def list_types() -> dict[str, Any]:
    """Return the full data-type registry hierarchy."""
    ctx = get_context()
    types_map = ctx.type_registry.all_types()
    entries = [
        {
            "name": spec.name,
            "parent": spec.base_type,
            "description": spec.description,
            "module_path": spec.module_path,
        }
        for spec in types_map.values()
    ]
    return {"types": entries, "count": len(entries)}


# ---------------------------------------------------------------------------
# (a.4) get_workflow
# ---------------------------------------------------------------------------


def get_workflow(path: str) -> dict[str, Any]:
    """Load a workflow YAML and return its decoded representation.

    The *path* argument is resolved against the active project root
    (issue #790). Relative paths are interpreted relative to
    ``ctx.project_dir``; absolute paths must already be under the
    project root.

    Raises
    ------
    FileNotFoundError
        If the resolved path does not exist.
    PermissionError
        If *path* escapes the project root.
    RuntimeError
        If no project is currently open.
    """
    from scieasy.workflow.serializer import load_yaml

    p = _resolve_project_path(path)
    if not p.exists():
        raise FileNotFoundError(f"Workflow file not found: {p}")
    definition = load_yaml(p)
    payload = dataclasses.asdict(definition)
    # Issue #790: surface the absolute resolved path so the agent has
    # unambiguous evidence of which file was read.
    payload["path"] = str(p)
    return payload


# ---------------------------------------------------------------------------
# (a.5) validate_workflow
# ---------------------------------------------------------------------------


def _looks_like_inline_yaml(s: str) -> bool:
    """Heuristic: starts with ``name:`` or contains ``nodes:`` ⇒ inline."""
    stripped = s.lstrip()
    if stripped.startswith(("name:", "workflow:", "id:", "version:")):
        return True
    return "nodes:" in s and "\n" in s


def validate_workflow(yaml_or_path: str) -> dict[str, Any]:
    """Validate a workflow (inline YAML or path).

    Heuristic: if *yaml_or_path* starts with ``name:`` / ``workflow:`` /
    ``id:`` / ``version:`` or contains ``nodes:`` *and* a newline, treat
    as inline YAML; otherwise treat as a filesystem path.

    When *yaml_or_path* is a path, it is resolved against the active
    project root (issue #790) — relative paths are interpreted relative
    to ``ctx.project_dir``, and paths outside the project are rejected
    with :class:`PermissionError`.
    """
    import yaml as _yaml

    from scieasy.workflow.schema import WorkflowFileModel
    from scieasy.workflow.validator import validate_workflow as _validate

    ctx = get_context()
    inline = _looks_like_inline_yaml(yaml_or_path)
    try:
        if inline:
            raw = _yaml.safe_load(yaml_or_path)
            validated = WorkflowFileModel.model_validate(raw)
            definition = validated.workflow.to_definition()
        else:
            from scieasy.workflow.serializer import load_yaml

            resolved = _resolve_project_path(yaml_or_path)
            definition = load_yaml(resolved)
    except Exception as exc:
        return {"valid": False, "errors": [f"parse failure: {exc}"]}

    errors = _validate(definition, registry=ctx.block_registry)
    return {"valid": not errors, "errors": list(errors)}


# ---------------------------------------------------------------------------
# (a.6) write_workflow
# ---------------------------------------------------------------------------


def write_workflow(path: str, yaml: str) -> dict[str, Any]:
    """Persist a workflow YAML to disk with a file lock.

    File-locked atomic write per ADR-033 OQ7. Logs INFO with the diff
    summary. Write-class tool: subject to STRICT-mode approval.

    Path handling (issue #790): the *path* argument is resolved against
    the active project root via :func:`_resolve_project_path`. Relative
    paths are interpreted relative to ``ctx.project_dir`` (NOT the
    backend process's CWD). Absolute paths must already be under the
    project root or :class:`PermissionError` is raised — this also
    protects against ``../`` traversal escapes. The returned envelope
    carries the **absolute resolved path**, never the user-supplied
    input, so the agent can verify where its file actually landed.

    TODO(#732): once the workflow versioning agent's ``If-Match`` header
    lands on ``PUT /api/workflows/{id}``, the conflict-detect path here
    should call that endpoint instead of doing a raw filelock write, so
    the canvas optimistic-concurrency model and the agent's writes share
    the same arbitration code path. Today the filelock alone is the
    arbitration mechanism.
    """
    p = _resolve_project_path(path)
    lock_path = str(p) + ".lock"
    try:
        with FileLock(lock_path, timeout=_LOCK_TIMEOUT_SECONDS):
            old = p.read_text(encoding="utf-8") if p.exists() else ""
            bytes_written = _atomic_write_text(p, yaml)
            summary = _diff_summary(old, yaml)
    except Timeout as exc:
        raise TimeoutError(
            f"write_workflow: could not acquire lock for {p} within {_LOCK_TIMEOUT_SECONDS}s (someone else is editing?)"
        ) from exc

    logger.info("write_workflow: wrote %s (%s)", p, summary)
    return {"path": str(p), "bytes_written": bytes_written, "diff_summary": summary}


# ---------------------------------------------------------------------------
# (a.7) run_workflow
# ---------------------------------------------------------------------------


def _get_workflow_runtime() -> Any:
    """Locate a runtime that knows how to start workflows.

    Production: the FastAPI ``ApiRuntime`` (returned via
    :func:`get_context`) exposes ``start_workflow`` + ``workflow_runs``.
    Tests: a stub that provides the same two attributes.

    Returns the context object itself when it satisfies the duck-type;
    raises :class:`RuntimeError` otherwise.
    """
    ctx = get_context()
    if not hasattr(ctx, "start_workflow"):
        raise RuntimeError(
            "Active MCPContext does not expose start_workflow(); run_workflow requires a full ApiRuntime."
        )
    return ctx


def run_workflow(path: str) -> dict[str, Any]:
    """Submit a workflow for execution and return its run identifier.

    Returns immediately with ``run_id`` and ``status: queued``. Progress
    is observable via :func:`get_run_status`.

    Write-class tool: subject to STRICT-mode approval.

    Path handling (issue #790): *path* is resolved against the active
    project root; the runtime keys runs by ``workflow_id = file.stem``
    so this also gives us the canonical id even when the agent passes
    a project-relative path.
    """
    runtime = _get_workflow_runtime()
    # ApiRuntime keys runs by workflow_id (the file stem in
    # ``workflows/<id>.yaml``), so derive that from the path. We do not
    # mint a synthetic run_id — the runtime owns identity.
    resolved = _resolve_project_path(path)
    workflow_id = resolved.stem
    result = runtime.start_workflow(workflow_id)
    run_id = result.get("workflow_id", workflow_id)
    logger.info("run_workflow: started run %s for %s", run_id, resolved)
    return {"run_id": str(run_id), "status": "queued"}


# ---------------------------------------------------------------------------
# (a.8) cancel_run
# ---------------------------------------------------------------------------


def cancel_run(run_id: str) -> dict[str, Any]:
    """Request cancellation of an in-flight workflow run."""
    from scieasy.engine.events import CANCEL_WORKFLOW_REQUEST, EngineEvent

    runtime = _get_workflow_runtime()
    runs = getattr(runtime, "workflow_runs", None)
    if not isinstance(runs, dict) or run_id not in runs:
        raise KeyError(f"Unknown run: {run_id}")

    run = runs[run_id]
    event_bus = getattr(run.scheduler, "_event_bus", None)
    if event_bus is None:
        # Best-effort fallback: cancel the asyncio task directly.
        if hasattr(run, "task") and not run.task.done():
            run.task.cancel()
        cancel_requested = True
    else:
        # Emit on the bus so the scheduler's _on_cancel_workflow runs.
        import asyncio

        coro = event_bus.emit(EngineEvent(event_type=CANCEL_WORKFLOW_REQUEST, data={"workflow_id": run_id}))
        try:
            loop = asyncio.get_running_loop()
            # Keep a reference on the run object so the task is not
            # garbage-collected mid-flight (RUF006).
            run._cancel_task = loop.create_task(coro)  # type: ignore[attr-defined]
        except RuntimeError:
            # No running loop: fall back to a synchronous run.
            asyncio.run(coro)
        cancel_requested = True

    logger.info("cancel_run: requested cancellation for %s", run_id)
    return {"run_id": run_id, "cancel_requested": cancel_requested}


# ---------------------------------------------------------------------------
# (a.9) get_run_status
# ---------------------------------------------------------------------------


def get_run_status(run_id: str) -> dict[str, Any]:
    """Return the current status of a workflow run."""
    runtime = _get_workflow_runtime()
    runs = getattr(runtime, "workflow_runs", None)
    if not isinstance(runs, dict) or run_id not in runs:
        raise KeyError(f"Unknown run: {run_id}")

    run = runs[run_id]
    task = getattr(run, "task", None)
    if task is None:
        state = "unknown"
    elif task.done():
        if task.cancelled():
            state = "cancelled"
        elif task.exception() is not None:
            state = "failed"
        else:
            state = "succeeded"
    else:
        state = "running"

    # Per-block state map for richer progress reporting.
    block_states = {}
    scheduler = getattr(run, "scheduler", None)
    if scheduler is not None:
        raw_states = getattr(scheduler, "_block_states", {})
        # BlockState is an Enum — surface its value, not the repr.
        block_states = {
            block_id: getattr(state_obj, "name", str(state_obj)) for block_id, state_obj in raw_states.items()
        }

    return {
        "run_id": run_id,
        "state": state,
        "progress": {"block_states": block_states},
        "errors": [],
    }


# Synthesised module ID so logs can correlate even when called via dispatch.
_TOOL_MODULE_ID = f"mcp-workflow-{uuid.uuid4().hex[:8]}"
