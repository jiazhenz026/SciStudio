"""CLI entry point -- scieasy init, validate, run, blocks, serve."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import typer
import yaml

app = typer.Typer(name="scieasy", help="SciEasy -- AI-native scientific workflow runtime")


# ---------------------------------------------------------------------------
# Shared helpers for validate / run commands
# ---------------------------------------------------------------------------


def _check_file_exists(workflow: str) -> Path:
    """Return a resolved Path, or exit with code 1 if the file does not exist."""
    path = Path(workflow)
    if not path.exists():
        typer.echo(f"Error: file not found: {workflow}", err=True)
        raise typer.Exit(code=1)
    return path


def _load_workflow(path: Path) -> Any:
    """Load a workflow definition via the YAML serializer, or exit on error."""
    try:
        from scieasy.workflow.serializer import load_yaml

        return load_yaml(path)
    except NotImplementedError:
        typer.echo("Error: YAML serializer not yet implemented.", err=True)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        typer.echo(f"Error loading workflow: {exc}", err=True)
        raise typer.Exit(code=1) from None


def _validate_workflow(
    definition: Any,
    *,
    exit_on_stub: bool = True,
    registry: Any = None,
) -> list[str]:
    """Run workflow validation, returning a list of errors.

    When *exit_on_stub* is ``True`` (the ``validate`` command), a stub
    validator causes an immediate exit.  When ``False`` (the ``run``
    command), a stub validator is silently skipped so execution can proceed.

    When *registry* is provided, the validator can perform type-compatibility
    and dangling-port checks (Checks 5-6).
    """
    try:
        from scieasy.workflow.validator import validate_workflow

        return validate_workflow(definition, registry=registry)
    except NotImplementedError:
        if exit_on_stub:
            typer.echo("Error: workflow validator not yet implemented.", err=True)
            raise typer.Exit(code=1) from None
        return []


def _report_validation_errors(errors: list[str]) -> None:
    """Print validation errors and exit if the list is non-empty."""
    if errors:
        typer.echo("Validation errors:")
        for err in errors:
            typer.echo(f"  - {err}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def init(name: str = typer.Argument("my_project", help="Project workspace name")) -> None:
    """Create a new project workspace."""
    project_path = Path(name)
    if project_path.exists():
        typer.echo(f"Error: directory '{name}' already exists.", err=True)
        raise typer.Exit(code=1)

    # Create directory structure per ARCHITECTURE.md Section 10.
    subdirs = [
        "workflows",
        "data/raw",
        "data/zarr",
        "data/parquet",
        "data/artifacts",
        "data/exchange",
        "blocks",
        "types",
        "checkpoints",
        "lineage",
        "logs",
    ]
    for subdir in subdirs:
        (project_path / subdir).mkdir(parents=True, exist_ok=True)

    project_meta = {
        "project": {
            "name": name,
            "version": "0.1.0",
            "created": date.today().isoformat(),
        }
    }
    (project_path / "project.yaml").write_text(yaml.safe_dump(project_meta, default_flow_style=False, sort_keys=False))

    typer.echo(f"Created project workspace: {name}/")


@app.command()
def validate(workflow: str = typer.Argument(..., help="Path to workflow YAML")) -> None:
    """Validate a workflow YAML file."""
    path = _check_file_exists(workflow)
    definition = _load_workflow(path)
    from scieasy.blocks.registry import BlockRegistry

    registry = BlockRegistry()
    try:
        registry.scan()
    except Exception as exc:
        typer.echo(f"Warning: registry scan encountered errors: {exc}", err=True)

    errors = _validate_workflow(definition, exit_on_stub=True, registry=registry)
    _report_validation_errors(errors)
    typer.echo("Valid.")


@app.command()
def run(workflow: str = typer.Argument(..., help="Path to workflow YAML")) -> None:
    """Run a workflow headless."""
    path = _check_file_exists(workflow)
    definition = _load_workflow(path)
    from scieasy.blocks.registry import BlockRegistry

    registry = BlockRegistry()
    try:
        registry.scan()
    except Exception as exc:
        typer.echo(f"Warning: registry scan encountered errors: {exc}", err=True)

    errors = _validate_workflow(definition, exit_on_stub=False, registry=registry)
    _report_validation_errors(errors)

    # Build DAG and show execution order.
    try:
        from scieasy.engine.dag import build_dag, topological_sort

        dag = build_dag(definition)
        order = topological_sort(dag)
        typer.echo(f"Execution order: {' -> '.join(order)}")
    except Exception as exc:
        typer.echo(f"Error building DAG: {exc}", err=True)
        raise typer.Exit(code=1) from None

    # Execute workflow via DAGScheduler.
    try:
        import asyncio

        from scieasy.engine.events import EventBus
        from scieasy.engine.resources import ResourceManager
        from scieasy.engine.runners.local import LocalRunner
        from scieasy.engine.scheduler import DAGScheduler

        event_bus = EventBus()
        resource_mgr = ResourceManager()
        runner = LocalRunner(event_bus=event_bus)
        scheduler = DAGScheduler(
            workflow=definition,
            event_bus=event_bus,
            resource_manager=resource_mgr,
            process_registry=None,
            runner=runner,
            registry=registry,
        )
        asyncio.run(scheduler.execute())
        typer.echo("Workflow completed.")
    except Exception as exc:
        typer.echo(f"Execution error: {exc}")
        typer.echo("Note: Full block execution requires all block types to be installed and configured.")
        raise typer.Exit(code=1) from None


@app.command()
def blocks() -> None:
    """List all installed blocks."""
    from scieasy.blocks.registry import BlockRegistry

    registry = BlockRegistry()
    try:
        registry.scan()
    except Exception as exc:
        typer.echo(f"Warning: registry scan encountered errors: {exc}", err=True)

    specs = registry.all_specs()
    if not specs:
        typer.echo("No blocks found.")
        return

    all_specs = sorted(specs.values(), key=lambda s: (s.base_category, s.subcategory, s.name))

    name_w = max(max(len(s.name) for s in all_specs), 4)
    base_w = max(max(len(s.base_category) for s in all_specs), 8)
    sub_w = max(max(len(s.subcategory) for s in all_specs), 11)
    ver_w = max(max(len(s.version) for s in all_specs), 7)

    header = f"{'Name':<{name_w}}  {'Category':<{base_w}}  {'Subcategory':<{sub_w}}  {'Version':<{ver_w}}  Description"
    typer.echo(header)
    typer.echo("-" * len(header))

    for spec in all_specs:
        desc = spec.description[:60] if spec.description else ""
        typer.echo(
            f"{spec.name:<{name_w}}  {spec.base_category:<{base_w}}  "
            f"{spec.subcategory:<{sub_w}}  {spec.version:<{ver_w}}  {desc}"
        )

    typer.echo(f"\nFound {len(all_specs)} block(s)")


@app.command("init-block-package")
def init_block_package(
    name: str = typer.Argument(..., help="Package name (e.g. scieasy-blocks-srs)"),
    display_name: str = typer.Option("", "--display-name", help="Human-readable display name"),
    author: str = typer.Option("", "--author", help="Author name"),
    description: str = typer.Option("", "--description", help="One-line package description"),
) -> None:
    """Scaffold a new SciEasy block package.

    Creates a ready-to-develop package directory with pyproject.toml,
    entry-points configuration, example block, and tests.
    """
    from scieasy.cli._scaffold import scaffold_block_package

    output_dir = Path.cwd()
    try:
        result = scaffold_block_package(
            output_dir,
            name,
            author=author,
            description=description,
            display_name=display_name,
        )
    except FileExistsError:
        typer.echo(f"Error: directory '{name}' already exists.", err=True)
        raise typer.Exit(code=1) from None

    root: Path = result["root"]
    files: list[str] = result["files"]

    typer.echo(f"Created block package: {root.name}/")
    for f in files:
        typer.echo(f"  {f}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo(f"  cd {root.name}")
    typer.echo("  pip install -e '.[dev]'")
    typer.echo("  pytest")
    typer.echo("  scieasy blocks  # verify registration")


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start the FastAPI server."""
    import uvicorn

    typer.echo(f"Starting SciEasy server on {host}:{port}...")
    uvicorn.run("scieasy.api.app:create_app", host=host, port=port, factory=True)


@app.command()
def gui(
    port: int = typer.Option(8000, help="Port for the API server"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open browser automatically"),
) -> None:
    """Launch SciEasy GUI in your default browser."""
    import logging
    import os
    import threading
    import webbrowser

    import uvicorn

    # Configure root logger so all getLogger(__name__) calls produce output.
    # ``force=True`` ensures this works even if a library or framework has
    # already attached a handler (e.g. uvicorn).
    log_level = os.environ.get("SCIEASY_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )

    url = f"http://localhost:{port}"
    typer.echo(f"Starting SciEasy GUI on {url} ...")
    if not no_browser:
        threading.Timer(1.5, webbrowser.open, args=[url]).start()
    uvicorn.run("scieasy.api.app:create_app", host="0.0.0.0", port=port, factory=True)
