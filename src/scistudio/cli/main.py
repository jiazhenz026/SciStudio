"""CLI entry point -- scistudio init, validate, run, blocks, serve."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import typer
import yaml

app = typer.Typer(name="scistudio", help="SciStudio -- AI-native scientific workflow runtime")

# Register subcommands provided by sibling modules.
# These were dropped during the ADR-033 rollback (PR #808) but the
# underlying modules (`install`, `mcp_bridge`) survived intact.
# See PR #794 for original integration context.
from scistudio.cli import install as _install_cli  # noqa: E402
from scistudio.cli import mcp_bridge as _mcp_bridge_cli  # noqa: E402

_install_cli.register(app)
_mcp_bridge_cli.register(app)


def _version_callback(value: bool) -> None:
    # #1742: ``scistudio --version`` prints the human display string.
    if value:
        from scistudio.version import get_version

        typer.echo(get_version().display)
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    """SciStudio -- AI-native scientific workflow runtime."""


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
        from scistudio.workflow.serializer import load_yaml

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
        from scistudio.workflow.validator import validate_workflow

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
    # ADR-038 §3.5 / §5.2: lineage history lives at ``.scistudio/lineage.db``;
    # the legacy ``lineage/`` and ``checkpoints/`` top-level dirs are retired
    # in favour of ``.scistudio/``. Symmetric with ``api/runtime.py::create_project``.
    subdirs = [
        "workflows",
        "data/raw",
        "data/zarr",
        "data/parquet",
        "data/artifacts",
        "data/exchange",
        "blocks",
        "types",
        ".scistudio",
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

    # --------------------------------------------------------------
    # ADR-039 §6 Phase 1 — CLI git-init parity (D39-2.2a skeleton)
    # --------------------------------------------------------------
    # Projects created via ``scistudio init`` must get the same auto-init
    # treatment as those created via the GUI (``ApiRuntime.create_project``).
    # Otherwise CLI-created projects open in the GUI without git history,
    # confusing the ADR-038 lineage join.
    #
    # IMPLEMENTATION FOR D39-2.2b:
    # ----------------------------
    # 1. Lazy import (so ``scistudio init`` doesn't pay the import cost
    #    of the versioning package until needed):
    #        from scistudio.core.versioning.git_engine import GitEngine
    # 2. ``engine = GitEngine(project_path)``
    # 3. Best-effort:
    #        try:
    #            engine.init_repository(project_path)
    #            typer.echo("Initialized git repository.")
    #        except BundledGitMissing:
    #            typer.echo("WARNING: git binary unavailable; project "
    #                       "created without version control.", err=True)
    #        except GitError as exc:
    #            typer.echo(f"WARNING: git init failed: {exc}", err=True)
    #
    # The CLI must NOT abort on git failure — degraded-mode projects
    # (no .git/) are explicitly supported per ADR-039 §3.9.
    try:
        from scistudio.core.versioning.git_binary import BundledGitMissing
        from scistudio.core.versioning.git_engine import GitEngine, GitError

        try:
            engine = GitEngine(project_path)
            engine.init_repository(project_path)
            typer.echo("Initialized git repository.")
        except BundledGitMissing as exc:
            typer.echo(
                f"WARNING: git binary unavailable ({exc}); project created without version control.",
                err=True,
            )
        except GitError as exc:
            typer.echo(f"WARNING: git init failed: {exc}", err=True)
        except FileExistsError:
            # .git already present — already a repo, that's fine.
            pass
    except Exception as exc:  # pragma: no cover — defensive
        typer.echo(f"WARNING: git auto-init errored: {exc}", err=True)

    # ------------------------------------------------------------------
    # ADR-040 §3.8 prod-env agent provisioning wiring (cli init).
    # ------------------------------------------------------------------
    # Runs AFTER git init so the initial commit is clean of provisioned
    # files. Failures are non-fatal per ADR §7 and surfaced via
    # ``typer.echo`` on stderr, mirroring the ADR-039 degraded-mode
    # pattern above.
    try:
        from scistudio.agent_provisioning import install_project_agent_assets

        provision_result = install_project_agent_assets(project_path, force=False)
        if provision_result.failed:
            typer.echo(
                f"WARNING: ADR-040 agent provisioning partial failure: {provision_result.failed}",
                err=True,
            )
    except Exception as exc:  # pragma: no cover — defensive
        typer.echo(
            f"WARNING: ADR-040 agent provisioning failed: {exc}",
            err=True,
        )

    typer.echo(f"Created project workspace: {name}/")


@app.command()
def validate(workflow: str = typer.Argument(..., help="Path to workflow YAML")) -> None:
    """Validate a workflow YAML file."""
    path = _check_file_exists(workflow)
    definition = _load_workflow(path)
    from scistudio.blocks.registry import BlockRegistry

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
    import os

    from scistudio.utils.logging import configure_logging

    # #1741: headless runs previously configured no logging, so engine/block
    # errors were silent. Configure console + file logging up front.
    configure_logging(os.environ.get("SCISTUDIO_LOG_LEVEL", "INFO").upper())
    path = _check_file_exists(workflow)
    definition = _load_workflow(path)
    from scistudio.blocks.registry import BlockRegistry

    registry = BlockRegistry()
    try:
        registry.scan()
    except Exception as exc:
        typer.echo(f"Warning: registry scan encountered errors: {exc}", err=True)

    errors = _validate_workflow(definition, exit_on_stub=False, registry=registry)
    _report_validation_errors(errors)

    # Build DAG and show execution order.
    try:
        from scistudio.engine.dag import build_dag, topological_sort

        dag = build_dag(definition)
        order = topological_sort(dag)
        typer.echo(f"Execution order: {' -> '.join(order)}")
    except Exception as exc:
        typer.echo(f"Error building DAG: {exc}", err=True)
        raise typer.Exit(code=1) from None

    # Execute workflow via DAGScheduler.
    try:
        import asyncio

        from scistudio.engine.events import EventBus
        from scistudio.engine.resources import ResourceManager
        from scistudio.engine.runners.local import LocalRunner
        from scistudio.engine.scheduler import DAGScheduler

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
    from scistudio.blocks.registry import BlockRegistry

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
    name: str = typer.Argument(..., help="Package name (e.g. scistudio-blocks-srs)"),
    display_name: str = typer.Option("", "--display-name", help="Human-readable display name"),
    author: str = typer.Option("", "--author", help="Author name"),
    description: str = typer.Option("", "--description", help="One-line package description"),
) -> None:
    """Scaffold a new SciStudio block package.

    Creates a ready-to-develop package directory with pyproject.toml,
    entry-points configuration, example block, and tests.
    """
    from scistudio.cli._scaffold import scaffold_block_package

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
    typer.echo("  scistudio blocks  # verify registration")


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start the FastAPI server."""
    import os

    import uvicorn

    from scistudio.utils.logging import configure_logging

    # #1741: console + persistent file logging; log_config=None lets uvicorn's
    # access/error loggers propagate to the root handlers (so they hit the file).
    configure_logging(os.environ.get("SCISTUDIO_LOG_LEVEL", "INFO").upper())
    typer.echo(f"Starting SciStudio server on {host}:{port}...")
    # ADR-035 §3.10: see comment in `gui` for why this is needed.
    os.environ.setdefault("SCISTUDIO_ENGINE_API_URL", f"http://127.0.0.1:{port}")
    uvicorn.run("scistudio.api.app:create_app", host=host, port=port, factory=True, log_config=None)


def _ephemeral_port(host: str) -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


@app.command()
def gui(
    port: int = typer.Option(8000, help="Port for the API server"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open browser automatically"),
    bundled: bool = typer.Option(False, "--bundled", help="Run in desktop bundled mode"),
) -> None:
    """Launch SciStudio GUI in your default browser."""
    import json
    import os
    import threading
    import webbrowser

    import uvicorn

    from scistudio.utils.logging import configure_logging

    # #1741: console + persistent JSON-line file logging (replaces bare
    # basicConfig). Backend/engine/event-bus/websocket logs now land on disk for
    # alpha bug reproduction. Idempotent with the create_app fallback.
    log_level = os.environ.get("SCISTUDIO_LOG_LEVEL", "INFO").upper()
    log_file = configure_logging(log_level)
    if log_file is not None and not bundled:
        typer.echo(f"Logging to {log_file}")

    server_host = "127.0.0.1" if bundled else "0.0.0.0"
    public_host = "127.0.0.1" if bundled else "localhost"
    bound_port = _ephemeral_port(public_host) if port == 0 else port
    url = f"http://{public_host}:{bound_port}"
    if bundled:
        os.environ.setdefault("SCISTUDIO_BUNDLED", "1")
        typer.echo(
            json.dumps(
                {
                    "event": "scistudio.ready",
                    "host": public_host,
                    "port": bound_port,
                    "url": url,
                },
                separators=(",", ":"),
            )
        )
    else:
        typer.echo(f"Starting SciStudio GUI on {url} ...")
    # ADR-035 §3.10: workers spawned by the engine call back via this URL to
    # request PTY tabs. The engine alone knows the bound port at startup, so
    # export it here before uvicorn forks any worker. Companion to
    # SCISTUDIO_ENGINE_IPC_TOKEN (set in api.app:lifespan).
    os.environ.setdefault("SCISTUDIO_ENGINE_API_URL", f"http://127.0.0.1:{bound_port}")
    if not no_browser and not bundled:
        threading.Timer(1.5, webbrowser.open, args=[url]).start()
    # #1741: log_config=None lets uvicorn loggers propagate to our root handlers.
    uvicorn.run(
        "scistudio.api.app:create_app",
        host=server_host,
        port=bound_port,
        factory=True,
        log_config=None,
    )


if __name__ == "__main__":
    app()
