"""Markdown methods export for a lineage run (ADR-038 §3.7, §5.1).

Renders a human-readable Methods-section markdown document that answers the
four user questions surfaced in ADR-038 §3.7:

1. Which run? (run_id, started_at, status, workflow_id, git commit + dirty,
   environment snapshot)
2. Which workflow was running? (workflow_yaml_snapshot literal)
3. Which blocks ran? (per-block list: block_id, block_type, version, timing,
   termination)
4a. Per-block params? (block_config_resolved per block)
4b. Per-block I/O DataObjects? (block_io ↔ data_objects join per block)

The renderer is **read-only** against the :class:`LineageStore` — it does
not modify any rows. Callers (the `/api/runs/{run_id}/methods` route)
serve the returned string as ``text/markdown``.

The output is intentionally plain markdown — no YAML/HTML scaffolding, no
front-matter — so users can paste it directly into a Methods section of a
paper, a notebook, or a plain markdown editor without post-processing.
"""

from __future__ import annotations

import json
from typing import Any

from scieasy.core.lineage.store import LineageStore


def render_methods_markdown(store: LineageStore, run_id: str) -> str:
    """Render the methods-section markdown body for a single run.

    Parameters
    ----------
    store:
        Open lineage store. Caller owns lifecycle.
    run_id:
        Primary key into ``runs``.

    Returns
    -------
    Markdown body, plain UTF-8 text. Returned even when the run row is
    missing — in that case the body is a single-line "Run not found"
    message so callers can serve a useful 404 body.

    Raises
    ------
    Nothing — all exceptions from the underlying store are propagated up;
    this function does not catch them. The 404-on-missing case returns a
    string (not an exception) because the route may want to surface it
    inside a 200 envelope for debugging.
    """
    run = store.get_run(run_id)
    if run is None:
        return f"# Run not found\n\nNo run with `run_id = {run_id}` exists in this project's lineage store.\n"

    lines: list[str] = []
    lines.extend(_render_run_header(run))
    lines.extend(_render_environment(run))
    lines.extend(_render_workflow_snapshot(run))
    lines.extend(_render_block_executions(store, run_id))
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Section renderers — each returns a list of lines (no trailing newline).
# ---------------------------------------------------------------------------


def _render_run_header(run: dict[str, Any]) -> list[str]:
    """Q1 + Q2 header — run identity, workflow identity, git commit, status."""
    started = run.get("started_at") or "?"
    finished = run.get("finished_at") or "(still running)"
    status = run.get("status") or "?"
    workflow_id = run.get("workflow_id") or "?"
    git_commit = run.get("workflow_git_commit") or "(not under git)"
    dirty = bool(run.get("workflow_dirty"))
    dirty_marker = " (dirty)" if dirty else ""
    triggered_by = run.get("triggered_by") or "user"
    parent_run = run.get("parent_run_id")
    execute_from = run.get("execute_from_block_id")

    lines = [
        "# Methods",
        "",
        f"**Run ID**: `{run.get('run_id')}`  ",
        f"**Workflow**: `{workflow_id}`  ",
        f"**Started**: {started}  ",
        f"**Finished**: {finished}  ",
        f"**Status**: {status}  ",
        f"**Git commit**: `{git_commit}`{dirty_marker}  ",
        f"**Triggered by**: {triggered_by}",
    ]
    if parent_run:
        lines.append(f"**Parent run**: `{parent_run}`  ")
    if execute_from:
        lines.append(f"**Execute-from block**: `{execute_from}`  ")
    if run.get("user_notes"):
        lines.extend(["", "## Notes", "", str(run["user_notes"])])
    return lines


def _render_environment(run: dict[str, Any]) -> list[str]:
    """Environment snapshot — pretty-printed JSON code-fence."""
    raw = run.get("environment_snapshot")
    if not raw:
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        body = json.dumps(parsed, indent=2, sort_keys=True, default=str)
    except (TypeError, ValueError):
        body = str(raw)
    return [
        "",
        "## Environment",
        "",
        "```json",
        body,
        "```",
    ]


def _render_workflow_snapshot(run: dict[str, Any]) -> list[str]:
    """Q2 — workflow YAML literal (the recipe)."""
    snapshot = run.get("workflow_yaml_snapshot") or ""
    if not snapshot.strip():
        return []
    return [
        "",
        "## Workflow definition (YAML snapshot)",
        "",
        "```yaml",
        snapshot.rstrip(),
        "```",
    ]


def _render_block_executions(store: LineageStore, run_id: str) -> list[str]:
    """Q3 + Q4a + Q4b — per-block params + I/O DataObjects."""
    block_execs = store.list_block_executions(run_id)
    if not block_execs:
        return ["", "## Blocks", "", "_No blocks executed in this run._"]

    lines: list[str] = ["", "## Blocks", ""]
    for be in block_execs:
        lines.extend(_render_one_block(store, be))
    return lines


def _render_one_block(store: LineageStore, be: dict[str, Any]) -> list[str]:
    """Render one block_execution row with its params + I/O DataObjects."""
    block_id = be.get("block_id") or "?"
    block_type = be.get("block_type") or "?"
    block_version = be.get("block_version") or "?"
    started_at = be.get("started_at") or "?"
    finished_at = be.get("finished_at") or "(in progress)"
    duration_ms = be.get("duration_ms")
    termination = be.get("termination") or "?"
    termination_detail = be.get("termination_detail") or ""
    block_execution_id = be.get("block_execution_id") or "?"

    duration_str = f"{duration_ms} ms" if duration_ms is not None else "n/a"

    lines = [
        f"### `{block_id}` ({block_type} v{block_version})",
        "",
        f"- **Block execution ID**: `{block_execution_id}`",
        f"- **Started**: {started_at}",
        f"- **Finished**: {finished_at}",
        f"- **Duration**: {duration_str}",
        f"- **Termination**: `{termination}`" + (f" — {termination_detail}" if termination_detail else ""),
        "",
    ]

    # Q4a — block_config_resolved (the post-template-expansion config).
    config_raw = be.get("block_config_resolved")
    if config_raw:
        try:
            parsed = json.loads(config_raw) if isinstance(config_raw, str) else config_raw
            body = json.dumps(parsed, indent=2, sort_keys=True, default=str)
        except (TypeError, ValueError):
            body = str(config_raw)
        lines.extend(
            [
                "**Config:**",
                "",
                "```json",
                body,
                "```",
                "",
            ]
        )

    # Q4b — per-port I/O DataObjects.
    io_rows = store.list_block_io(block_execution_id)
    if io_rows:
        lines.extend(_render_io_table(store, io_rows))

    return lines


def _render_io_table(store: LineageStore, io_rows: list[dict[str, Any]]) -> list[str]:
    """Render the inputs + outputs as two grouped tables."""
    inputs = [row for row in io_rows if row.get("direction") == "input"]
    outputs = [row for row in io_rows if row.get("direction") == "output"]

    lines: list[str] = []
    if inputs:
        lines.append("**Inputs:**")
        lines.append("")
        lines.extend(_io_section_lines(store, inputs))
        lines.append("")
    if outputs:
        lines.append("**Outputs:**")
        lines.append("")
        lines.extend(_io_section_lines(store, outputs))
        lines.append("")
    return lines


def _io_section_lines(store: LineageStore, io_rows: list[dict[str, Any]]) -> list[str]:
    """Render a single direction (inputs OR outputs) as a markdown table."""
    lines = [
        "| Port | Position | Type | Storage path | Object ID |",
        "|---|---|---|---|---|",
    ]
    for row in io_rows:
        port = row.get("port_name", "?")
        position = row.get("position", 0)
        object_id = row.get("object_id", "?")
        obj = store.get_data_object(object_id)
        if obj is None:
            type_name = "?"
            storage_path = "?"
        else:
            type_name = obj.get("type_name") or "?"
            storage_path = obj.get("storage_path") or "(in-memory)"
        lines.append(f"| `{port}` | {position} | `{type_name}` | `{storage_path}` | `{object_id}` |")
    return lines
