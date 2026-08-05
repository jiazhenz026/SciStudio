"""``scistudio storage`` — inspect and reclaim persisted workflow artifacts (#1983).

Two subcommands:

* ``storage usage`` reports how much disk each workflow's artifacts occupy.
* ``storage gc`` applies the retention rule from
  :mod:`scistudio.core.lineage.retention`: keep the artifacts produced by each
  workflow's most recent successful run, reclaim the rest.

``gc`` previews by default and only deletes when given ``--apply``, because a
sweep is not reversible.
"""

from __future__ import annotations

from pathlib import Path

import typer

from scistudio.core.lineage.retention import (
    ARTIFACT_ROOTS,
    RetentionPlan,
    apply_retention,
    plan_retention,
)
from scistudio.core.lineage.store import LineageStore, artifact_size_bytes

storage_app = typer.Typer(name="storage", help="Inspect and reclaim persisted workflow artifacts.")


def _format_bytes(value: int) -> str:
    """Render *value* as a human-readable size."""
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024.0
    return f"{size:.1f} TB"


def _resolve_project(project: str | None) -> Path:
    """Return the project root, defaulting to the current directory."""
    root = Path(project) if project else Path.cwd()
    if not (root / ".scistudio").is_dir():
        typer.echo(f"Not a SciStudio project (no .scistudio directory): {root}", err=True)
        raise typer.Exit(code=1)
    return root


def _echo_plan(plan: RetentionPlan) -> None:
    """Print the retained/reclaimable summary for *plan*."""
    if plan.is_blocked:
        typer.echo(f"Retention did not run: {plan.blocked_reason}")
        return

    typer.echo("Retained runs (most recent successful run per workflow):")
    for workflow_id, run_id in sorted(plan.retained_runs.items()):
        typer.echo(f"  {workflow_id}: {run_id[:12]}")

    for workflow_id, reason in sorted(plan.protected_workflows.items()):
        typer.echo(f"  {workflow_id}: SKIPPED — {reason}")

    if not plan.candidates:
        typer.echo("\nNothing to reclaim.")
        return

    by_workflow: dict[str, tuple[int, int]] = {}
    for candidate in plan.candidates:
        count, size = by_workflow.get(candidate.workflow_id, (0, 0))
        by_workflow[candidate.workflow_id] = (count + 1, size + candidate.size_bytes)

    typer.echo("\nReclaimable:")
    for workflow_id, (count, size) in sorted(by_workflow.items(), key=lambda kv: -kv[1][1]):
        typer.echo(f"  {workflow_id}: {count} artifacts, {_format_bytes(size)}")
    typer.echo(f"\nTotal: {len(plan.candidates)} artifacts, {_format_bytes(plan.total_bytes)}")


@storage_app.command("usage")
def usage(
    project: str = typer.Option(None, "--project", help="Project root (defaults to the current directory)."),
) -> None:
    """Report artifact disk usage per workflow."""
    root = _resolve_project(project)

    totals: dict[str, int] = {}
    for artifact_root in ARTIFACT_ROOTS:
        base = root / artifact_root
        if not base.is_dir():
            continue
        for workflow_dir in sorted(base.iterdir()):
            if workflow_dir.is_dir():
                size = artifact_size_bytes(str(workflow_dir)) or 0
                totals[workflow_dir.name] = totals.get(workflow_dir.name, 0) + size

    if not totals:
        typer.echo("No persisted artifacts found.")
        return

    for workflow_id, size in sorted(totals.items(), key=lambda kv: -kv[1]):
        typer.echo(f"{_format_bytes(size):>12}  {workflow_id}")
    typer.echo(f"{_format_bytes(sum(totals.values())):>12}  TOTAL")


@storage_app.command("gc")
def gc(
    project: str = typer.Option(None, "--project", help="Project root (defaults to the current directory)."),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Delete the reclaimable artifacts. Without this flag the command only previews.",
    ),
) -> None:
    """Keep each workflow's most recent successful run; reclaim older artifacts."""
    root = _resolve_project(project)
    store = LineageStore(str(root / ".scistudio" / "lineage.db"))
    try:
        plan = plan_retention(store, root)
        _echo_plan(plan)

        if plan.is_blocked:
            raise typer.Exit(code=1)
        if not plan.candidates:
            return
        if not apply:
            typer.echo("\nPreview only. Re-run with --apply to delete.")
            return

        removed, freed = apply_retention(plan)
        typer.echo(f"\nRemoved {removed} artifacts, freed {_format_bytes(freed)}.")
    finally:
        store.close()


def register(app: typer.Typer) -> None:
    """Register the ``storage`` command group on the given Typer app."""
    app.add_typer(storage_app, name="storage")
