"""Write-class workflow tools (3 of 4 — ``finish_ai_block`` lives in its own module).

Tools: ``write_workflow``, ``run_workflow``, ``cancel_run``.

Extracted from the original single-file ``tools_workflow.py`` (#1431,
umbrella #1427). No behavior change.
"""

from __future__ import annotations

import contextlib
import difflib
import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any

import yaml as yaml_module
from filelock import FileLock, Timeout
from pydantic import BaseModel, Field, ValidationError

from scistudio.ai.agent.mcp._context import _resolve_project_path, get_context
from scistudio.ai.agent.mcp.server import mcp
from scistudio.ai.agent.mcp.tools_workflow._errors import (
    _ensure_error_subscriber,
    _run_block_errors,
)
from scistudio.ai.agent.mcp.tools_workflow._helpers import (
    _LOCK_TIMEOUT_SECONDS,
    _atomic_write_text,
    _core_io_equivalent,
    _diff_summary,
    _get_workflow_runtime,
    _is_package_io_block,
)
from scistudio.ai.agent.mcp.tools_workflow._models import (
    CancelRunResult,
    EditWorkflowResult,
    RunWorkflowResult,
    WriteWorkflowResult,
)
from scistudio.engine.events import WORKFLOW_CHANGED, EngineEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# (a.6) write_workflow  (write-class)
# ---------------------------------------------------------------------------


@mcp.tool(name="write_workflow", tags={"category:workflow", "write"})
async def write_workflow(
    path: str = Field(description="Project-relative path under workflows/."),
    yaml: str = Field(description="Full workflow YAML content; will be schema-validated before write."),
) -> WriteWorkflowResult:
    """Persist a workflow YAML to disk with a file lock and pre-write schema validation.

    Use when:
      - You're creating a new workflow or replacing an existing one.

    Do NOT use to:
      - Patch one block's config (use ``update_block_config`` — preserves
        comments and key order via ruamel.yaml round-trip).
      - Edit ``workflows/*.yaml`` via Bash/Edit/Write tools — the
        protect_workflow_yaml hook (ADR-040 §3.6) will block such calls.
        This tool is the ONLY supported write path for workflows.

    Returns ``WriteWorkflowResult`` with ``next_step`` pointing at
    ``validate_workflow`` for canonical post-write verification.
    """
    from scistudio.workflow.schema import WorkflowFileModel

    # Pre-write validation: parse YAML and run through the same pydantic
    # model the runtime + GET route use. Failure raises ValueError with
    # JSON-embedded structured pydantic errors.
    try:
        parsed = yaml_module.safe_load(yaml)
    except yaml_module.YAMLError as exc:
        raise ValueError(f"write_workflow: YAML parse failure: {exc}") from exc
    try:
        wf_file = WorkflowFileModel.model_validate(parsed)
    except ValidationError as exc:
        raise ValueError(
            "write_workflow: refusing to write — workflow does not match "
            "the SciStudio schema. Errors (JSON):\n" + json.dumps(exc.errors(), indent=2, default=str)
        ) from exc

    # Resolve every node's block_type against the live registry (#1900).
    # Unknown/unresolvable types hard-fail here so the agent cannot persist a
    # workflow the GUI would render as an unresolved grey node. Package-specific
    # IO blocks are allowed but surfaced as non-blocking warnings that point at
    # the core Load/Save block.
    block_type_warnings = _reconcile_node_block_types(wf_file)

    p = _resolve_project_path(path)
    lock_path = str(p) + ".lock"
    version_context = _workflow_change_context()
    version: int | None = None
    try:
        with FileLock(lock_path, timeout=_LOCK_TIMEOUT_SECONDS):
            old = p.read_text(encoding="utf-8") if p.exists() else ""
            existed = p.exists()
            if version_context is not None:
                _, runtime = version_context
                version = runtime.bump_workflow_version(p.stem)
                mark_entity_write = getattr(runtime, "mark_entity_first_party_write", None)
                if mark_entity_write is not None:
                    with contextlib.suppress(TypeError):
                        mark_entity_write(
                            "workflow",
                            p.stem,
                            version,
                            path=p,
                            kind="modified" if existed else "created",
                            pending=True,
                        )
            bytes_written = _atomic_write_text(p, yaml)
            summary = _diff_summary(old, yaml)
    except Timeout as exc:
        raise TimeoutError(
            f"write_workflow: could not acquire lock for {p} within {_LOCK_TIMEOUT_SECONDS}s (someone else is editing?)"
        ) from exc

    await _emit_agent_workflow_changed(
        workflow_id=p.stem,
        path=p,
        kind="modified" if existed else "created",
        version=version,
        version_context=version_context,
    )
    logger.info("write_workflow: wrote %s (%s)", p, summary)
    return WriteWorkflowResult(
        path=str(p),
        bytes_written=bytes_written,
        diff_summary=summary,
        warnings=block_type_warnings,
    )


# ---------------------------------------------------------------------------
# (a.6b) edit_workflow  (write-class, surgical search/replace)
# ---------------------------------------------------------------------------


class WorkflowEdit(BaseModel):
    """One search/replace edit applied to a workflow YAML's text."""

    old_string: str = Field(description="Exact text to find in the workflow YAML.")
    new_string: str = Field(description="Text to replace it with.")
    replace_all: bool = Field(
        default=False,
        description=(
            "When true, replace every occurrence of old_string. When false "
            "(default), old_string must match exactly once (like the Edit tool)."
        ),
    )


def _apply_edits(text: str, edits: Sequence[WorkflowEdit | dict[str, Any]]) -> str:
    """Apply ordered search/replace *edits* to *text*.

    Each edit's ``old_string`` must match exactly once unless
    ``replace_all`` is set. A zero-match or (non-``replace_all``)
    multi-match edit raises ``ValueError`` before any write, mirroring the
    Edit tool's uniqueness contract. Edits are applied in order to the
    running text so a later edit sees the result of earlier ones;
    everything the edits do not touch is preserved verbatim.
    """
    result = text
    for index, raw in enumerate(edits):
        # Coerce plain dicts (direct callers / non-FastMCP invocation) into the
        # typed model. FastMCP coerces via the annotation, but internal callers
        # and tests may pass dicts.
        edit = raw if isinstance(raw, WorkflowEdit) else WorkflowEdit.model_validate(raw)
        if edit.old_string == edit.new_string:
            raise ValueError(
                f"edit_workflow: edit #{index + 1} has identical old_string and new_string (no-op edits are rejected)."
            )
        count = result.count(edit.old_string)
        if count == 0:
            raise ValueError(
                f"edit_workflow: edit #{index + 1} old_string not found in the "
                f"workflow. Read the current YAML (get_workflow) and copy the exact "
                f"text to replace, including indentation."
            )
        if count > 1 and not edit.replace_all:
            raise ValueError(
                f"edit_workflow: edit #{index + 1} old_string matched {count} times; "
                f"it must match exactly once. Add more surrounding context to make it "
                f"unique, or set replace_all=true to replace every occurrence."
            )
        result = result.replace(edit.old_string, edit.new_string)
    return result


@mcp.tool(name="edit_workflow", tags={"category:workflow", "write"})
async def edit_workflow(
    workflow_path: Annotated[str, Field(description="Project-relative path under workflows/.")],
    edits: Annotated[
        list[WorkflowEdit],
        Field(description="Ordered search/replace edits applied atomically to the workflow YAML text."),
    ],
) -> EditWorkflowResult:
    """Surgically edit part of an existing workflow YAML via search/replace patches.

    Applies one or more ``{old_string, new_string}`` edits to the file's
    text and preserves everything the edits do not touch — user-set block
    ``config``, comments, and key order all survive. Each ``old_string``
    must match exactly once (set ``replace_all`` to replace every match).
    All edits apply atomically: if any edit fails to match or the result
    fails schema validation, the file is left unchanged.

    Use when:
      - You're changing part of an existing workflow (add/remove a node,
        rewire an edge, tweak a description) and must NOT clobber the
        user's GUI-set block config or comments.

    Do NOT use to:
      - Create a new workflow — use ``write_workflow`` (whole-file write).
      - Patch one block's config params — use ``update_block_config``
        (schema-aware per-block patch).
      - Edit ``workflows/*.yaml`` via Bash/Edit/Write tools — the
        protect_workflow_yaml hook (ADR-040 §3.6) blocks such calls;
        this is the sanctioned partial-edit path.

    Returns ``EditWorkflowResult`` with ``next_step`` pointing at
    ``validate_workflow`` for canonical post-edit verification.
    """
    from scistudio.workflow.schema import WorkflowFileModel

    if not edits:
        raise ValueError("edit_workflow: 'edits' must contain at least one edit.")

    p = _resolve_project_path(workflow_path)
    if not p.exists():
        raise FileNotFoundError(
            f"edit_workflow: workflow file not found: {p}. Use write_workflow to create a new workflow."
        )
    lock_path = str(p) + ".lock"

    # Best-effort versioned event (GUI sync). A headless/minimal MCP context
    # without a workflow runtime must still edit the YAML, so degrade to
    # "no event" instead of raising — same pattern as update_block_config.
    try:
        version_context = _workflow_change_context()
    except Exception:
        version_context = None
    version: int | None = None

    try:
        with FileLock(lock_path, timeout=_LOCK_TIMEOUT_SECONDS):
            old = p.read_text(encoding="utf-8")

            # Apply the search/replace edits to the file TEXT. Uniqueness /
            # match errors raise before any write.
            new_text = _apply_edits(old, edits)

            # Pre-write validation: parse + validate the RESULT against the same
            # pydantic model write_workflow / the runtime / the GET route use.
            # Refuse to write on failure (leave the file unchanged).
            try:
                parsed = yaml_module.safe_load(new_text)
            except yaml_module.YAMLError as exc:
                raise ValueError(f"edit_workflow: edited YAML no longer parses: {exc}") from exc
            try:
                wf_file = WorkflowFileModel.model_validate(parsed)
            except ValidationError as exc:
                raise ValueError(
                    "edit_workflow: refusing to write — the edited workflow no longer "
                    "matches the SciStudio schema. Errors (JSON):\n" + json.dumps(exc.errors(), indent=2, default=str)
                ) from exc
            # Same block_type reconciliation write_workflow runs: unknown types
            # hard-fail, package IO blocks are non-blocking (edit_workflow does
            # not surface warnings, so we discard the return here).
            _reconcile_node_block_types(wf_file)

            if version_context is not None:
                _, runtime = version_context
                version = runtime.bump_workflow_version(p.stem)
                mark_entity_write = getattr(runtime, "mark_entity_first_party_write", None)
                if mark_entity_write is not None:
                    with contextlib.suppress(TypeError):
                        mark_entity_write(
                            "workflow",
                            p.stem,
                            version,
                            path=p,
                            kind="modified",
                            pending=True,
                        )

            bytes_written = _atomic_write_text(p, new_text)
            summary = _diff_summary(old, new_text)
    except Timeout as exc:
        raise TimeoutError(
            f"edit_workflow: could not acquire lock for {p} within {_LOCK_TIMEOUT_SECONDS}s (someone else is editing?)"
        ) from exc

    if version_context is not None:
        await _emit_agent_workflow_changed(
            workflow_id=p.stem,
            path=p,
            kind="modified",
            version=version,
            version_context=version_context,
        )

    logger.info("edit_workflow: edited %s with %d edit(s) (%s)", p, len(edits), summary)
    return EditWorkflowResult(
        path=str(p),
        bytes_written=bytes_written,
        diff_summary=summary,
        edits_applied=len(edits),
    )


def _reconcile_node_block_types(wf_file: Any) -> list[str]:
    """Validate node ``block_type`` values against the live block registry (#1900).

    Two problems this closes:

    * The agent copies a display name (e.g. ``"Load"``) or invents a dotted name
      (e.g. ``"imaging.segmentation"``) into ``block_type``. The GUI resolves
      nodes by their canonical ``type_name`` only, so such a node renders as an
      unresolved grey node. We **hard-fail** with the nearest valid ``type_name``.
    * The agent uses a package-specific IO block the core Load/Save block already
      covers. That is allowed but inconsistent, so we return a non-blocking
      **warning** naming the core equivalent.

    Returns the list of warnings. Raises ``ValueError`` when any node references
    an unregistered ``block_type``.
    """
    context = get_context()
    registry = getattr(context, "block_registry", None)
    if registry is None:
        return []
    try:
        specs = registry.all_specs()
    except Exception:  # pragma: no cover - defensive: registry not ready
        return []
    if not specs:
        # An empty/unscanned registry cannot judge block_type validity; skip
        # rather than reject an otherwise-valid workflow.
        return []

    by_type_name = {spec.type_name: spec for spec in specs.values() if spec.type_name}
    display_to_type = {spec.name: spec.type_name for spec in specs.values() if spec.name}
    valid_type_names = sorted(by_type_name)

    errors: list[str] = []
    warnings: list[str] = []
    for node in wf_file.workflow.nodes:
        block_type = node.block_type
        spec = by_type_name.get(block_type)
        if spec is None:
            hint = display_to_type.get(block_type)
            if hint is not None:
                detail = (
                    f"'{block_type}' is a block's display name; its type_name is "
                    f"'{hint}'. Put the type_name in 'block_type'."
                )
            else:
                close = difflib.get_close_matches(block_type, valid_type_names, n=3, cutoff=0.4)
                detail = (
                    ("Did you mean: " + ", ".join(repr(c) for c in close) + "? ") if close else ""
                ) + "Call list_blocks and copy a block's 'type_name'."
            errors.append(f"node '{node.id}': block_type '{block_type}' is not a registered block type. {detail}")
            continue
        if _is_package_io_block(spec):
            core_block, core_type = _core_io_equivalent(spec)
            core_hint = (
                f"'{core_block}' with core_type='{core_type}'"
                if core_type
                else f"'{core_block}' with the matching core_type"
            )
            warnings.append(
                f"node '{node.id}': block_type '{block_type}' is a package-specific "
                f"IO block. Prefer the core {core_hint} — it delegates to the same "
                f"package loader/saver and keeps one consistent GUI node."
            )

    if errors:
        raise ValueError(
            "write_workflow: refusing to write — one or more nodes reference a "
            "block_type the GUI cannot resolve (the GUI resolves nodes by their "
            "canonical type_name):\n- " + "\n- ".join(errors)
        )
    return warnings


def _workflow_change_context() -> tuple[Any, Any] | None:
    context = _get_workflow_runtime()
    event_bus = getattr(context, "event_bus", None)
    runtime = getattr(event_bus, "runtime", context)
    if event_bus is None or not all(
        hasattr(runtime, name)
        for name in (
            "bump_workflow_version",
            "mark_workflow_first_party_write",
            "versioned_change_payload",
        )
    ):
        return None
    return event_bus, runtime


async def _emit_agent_workflow_changed(
    *,
    workflow_id: str,
    path: Any,
    kind: str,
    version: int | None = None,
    version_context: tuple[Any, Any] | None = None,
) -> None:
    """Emit ADR-045 versioned workflow change events for MCP writes."""
    if version_context is None:
        version_context = _workflow_change_context()
    if version_context is None:
        return
    event_bus, runtime = version_context

    resolved = Path(path)
    if version is None:
        version = runtime.bump_workflow_version(workflow_id)
    runtime.mark_workflow_first_party_write(workflow_id, version, path=resolved, kind=kind)
    # #1591/#1597: route the FS-watcher self-write through the injected runtime
    # rather than importing api.routes.workflow_watcher here (this MCP tool is in
    # the ``ai`` layer; the direct import inverts the ai->api boundary).
    runtime.mark_workflow_self_write(resolved)

    project_dir = getattr(runtime, "project_dir", None)
    relative_path = str(resolved).replace("\\", "/")
    if project_dir is not None:
        with contextlib.suppress(ValueError):
            relative_path = str(resolved.resolve().relative_to(Path(project_dir).resolve())).replace("\\", "/")

    payload = runtime.versioned_change_payload(
        entity_class="workflow",
        entity_id=workflow_id,
        version=version,
        source="agent",
        source_id=None,
        kind=kind,
        workflow_id=workflow_id,
        path=relative_path,
        changed_by="mcp.write_workflow",
    )
    await event_bus.emit(EngineEvent(event_type=WORKFLOW_CHANGED, data=payload))


# ---------------------------------------------------------------------------
# (a.7) run_workflow  (write-class)
# ---------------------------------------------------------------------------


@mcp.tool(name="run_workflow", tags={"category:workflow", "write"})
async def run_workflow(
    path: str = Field(description="Project-relative path to the workflow YAML to execute."),
) -> RunWorkflowResult:
    """Submit a workflow for execution and return its run identifier.

    Use when:
      - You've written/validated a workflow and want to execute it.

    Do NOT use to:
      - Re-run a previously failed run with code fixes — write the fix
        first (``write_workflow`` or block source edit + ``reload_blocks``),
        then call this.
      - Inspect run progress — poll ``get_run_status`` with the returned
        ``run_id``.

    Returns immediately with status='queued'. Progress is observable via
    ``get_run_status``.
    """
    runtime = _get_workflow_runtime()
    _ensure_error_subscriber()
    resolved = _resolve_project_path(path)
    workflow_id = resolved.stem
    # Clear stale errors from a prior failed run with the same id.
    for key in list(_run_block_errors.keys()):
        if key[0] == workflow_id:
            del _run_block_errors[key]
    result = runtime.start_workflow(workflow_id)
    run_id = result.get("workflow_id", workflow_id) if isinstance(result, dict) else workflow_id
    logger.info("run_workflow: started run %s for %s", run_id, resolved)
    return RunWorkflowResult(run_id=str(run_id), status="queued")


# ---------------------------------------------------------------------------
# (a.8) cancel_run  (write-class)
# ---------------------------------------------------------------------------


@mcp.tool(name="cancel_run", tags={"category:workflow", "write"})
async def cancel_run(
    run_id: str = Field(description="Identifier returned by run_workflow."),
) -> CancelRunResult:
    """Request cancellation of an in-flight workflow run.

    Use when:
      - A run is producing wrong results and you want to stop it early.
      - A run is hung and needs to be terminated.

    Do NOT use to:
      - Inspect run state — use ``get_run_status``.

    Raises ``KeyError`` if the run_id is unknown.
    """
    import asyncio

    from scistudio.engine.events import CANCEL_WORKFLOW_REQUEST, EngineEvent

    runtime = _get_workflow_runtime()
    runs = getattr(runtime, "workflow_runs", None)
    if not isinstance(runs, dict) or run_id not in runs:
        raise KeyError(f"Unknown run: {run_id}")

    run = runs[run_id]
    event_bus = getattr(run.scheduler, "_event_bus", None) if hasattr(run, "scheduler") else None
    if event_bus is None:
        if hasattr(run, "task") and not run.task.done():
            run.task.cancel()
        cancel_requested = True
    else:
        coro = event_bus.emit(EngineEvent(event_type=CANCEL_WORKFLOW_REQUEST, data={"workflow_id": run_id}))
        try:
            loop = asyncio.get_running_loop()
            run._cancel_task = loop.create_task(coro)  # type: ignore[attr-defined]
        except RuntimeError:
            await coro
        cancel_requested = True

    logger.info("cancel_run: requested cancellation for %s", run_id)
    return CancelRunResult(run_id=run_id, cancel_requested=cancel_requested)


__all__: list[str] = [
    "WorkflowEdit",
    "_apply_edits",
    "cancel_run",
    "edit_workflow",
    "run_workflow",
    "write_workflow",
]
