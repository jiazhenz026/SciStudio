"""Category (e) MCP tools — preview-side plot authoring (6 tools, ADR-048 SPEC 2).

Read-class (4): ``list_plot_targets``, ``list_plot_examples``,
``read_plot_source``, ``validate_plot``.
Write/run-class (2): ``scaffold_plot``, ``run_plot_job`` (both expose
``next_step`` per FR-009 / FR-030).

All six register on the shared FastMCP instance with ``tags={"category:plot",
...}`` (FR-002, FR-003). A plot job is PREVIEW-ONLY: it never becomes a workflow
node, never edits workflow YAML, and never claims lineage (FR-025).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from pydantic import Field

import scistudio.ai.agent.mcp.tools_plot.examples as _examples
import scistudio.ai.agent.mcp.tools_plot.runtime as _runtime
import scistudio.ai.agent.mcp.tools_plot.scaffold as _scaffold
import scistudio.ai.agent.mcp.tools_plot.targets as _targets
import scistudio.ai.agent.mcp.tools_plot.validation as _validation
from scistudio.ai.agent.mcp._context import _resolve_project_root, get_context
from scistudio.ai.agent.mcp.server import mcp
from scistudio.ai.agent.mcp.tools_plot.models import (
    ListPlotExamplesResult,
    ListPlotTargetsResult,
    PlotLanguage,
    PlotRunResult,
    ReadPlotSourceResult,
    ScaffoldPlotResult,
    ValidatePlotResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# (e.1) list_plot_targets  (read)
# ---------------------------------------------------------------------------


@mcp.tool(name="list_plot_targets", tags={"category:plot", "read"})
async def list_plot_targets(
    workflow_path: Annotated[
        str | None,
        Field(description="Optional project-relative workflow file to scope discovery. None = all workflows."),
    ] = None,
    include_unavailable: Annotated[
        bool,
        Field(description="Include targets whose latest output is not yet recorded (with diagnostics)."),
    ] = True,
) -> ListPlotTargetsResult:
    """List valid plot targets (block output ports) for the project.

    Use when:
      - You are about to write a plot and need a stable target_id so you do
        not hand-type a node id or bind to the wrong repeated block.

    Do NOT use to:
      - List block types — use ``list_blocks``.
      - Read data — use ``preview_data``.

    Each target carries workflow path, node id, node label (display only),
    block type, output port, output type, and latest-output availability. Pass
    the returned ``target_id`` to ``scaffold_plot`` — never bind by node label.
    """
    targets = _targets.discover_targets(workflow_path=workflow_path, include_unavailable=include_unavailable)
    return ListPlotTargetsResult(targets=targets, count=len(targets))


# ---------------------------------------------------------------------------
# (e.2) scaffold_plot  (write)
# ---------------------------------------------------------------------------


@mcp.tool(name="scaffold_plot", tags={"category:plot", "write"})
async def scaffold_plot(
    plot_id: str = Field(description="Plot id (also the plots/<id>/ directory name); letters/digits/-/_."),
    target_id: str = Field(description="A stable target_id from list_plot_targets. Do NOT pass a node label."),
    language: Annotated[PlotLanguage, Field(description="Render-script language: 'python' or 'r'.")] = "python",
    title: Annotated[str | None, Field(description="Optional human title; defaults from plot_id.")] = None,
    overwrite: Annotated[bool, Field(description="Replace an existing plot directory if true (FR-008).")] = False,
) -> ScaffoldPlotResult:
    """Scaffold ``plots/<plot_id>/plot.yaml`` + a render script (FR-007).

    Use when:
      - ``list_plot_targets`` gave you a valid target_id and you want to start
        a new preview plot.

    Do NOT use to:
      - Author a workflow block — that is ``scaffold_block``. A plot job is
        preview-only and never becomes a DAG node.
      - Bind by block label — pass a discovered ``target_id``.

    Refuses label-only selection and refuses to overwrite an existing plot
    unless ``overwrite=true``. Returns manifest/script paths, bytes written,
    warnings, and ``next_step``.
    """
    ctx = get_context()
    root = _resolve_project_root(ctx)
    target = _targets.resolve_target_by_id(target_id)
    if target is None:
        raise ValueError(
            f"unknown target_id {target_id!r}. Call list_plot_targets and pass a returned "
            "target_id — plots must bind by workflow path + node id + output port, never a label."
        )
    warnings: list[str] = []
    if not target.latest_output_available:
        warnings.append("the bound target has no recorded output yet; run the workflow before run_plot_job.")
    try:
        manifest_path, script_path, bytes_written = _scaffold.scaffold_plot_files(
            root, plot_id, target, language, title, overwrite
        )
    except _scaffold.PlotScaffoldError as exc:
        raise ValueError(str(exc)) from exc

    def _rel(p: Path) -> str:
        try:
            return p.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:  # pragma: no cover
            return str(p)

    return ScaffoldPlotResult(
        plot_id=plot_id,
        manifest_path=_rel(manifest_path),
        script_path=_rel(script_path),
        bytes_written=bytes_written,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# (e.3) list_plot_examples  (read)
# ---------------------------------------------------------------------------


@mcp.tool(name="list_plot_examples", tags={"category:plot", "read"})
async def list_plot_examples(
    language: Annotated[str | None, Field(description="Filter by 'python' or 'r'.")] = None,
    library: Annotated[str | None, Field(description="Filter by 'matplotlib', 'seaborn', or 'ggplot2'.")] = None,
) -> ListPlotExamplesResult:
    """List curated render-script examples (FR-019).

    Use when:
      - You want a starting point for a matplotlib, seaborn, or ggplot2 plot.

    Do NOT use to:
      - Read an existing project plot — use ``read_plot_source``.
    """
    examples = _examples.list_examples(language=language, library=library)
    return ListPlotExamplesResult(examples=examples, count=len(examples))


# ---------------------------------------------------------------------------
# (e.4) read_plot_source  (read)
# ---------------------------------------------------------------------------


@mcp.tool(name="read_plot_source", tags={"category:plot", "read"})
async def read_plot_source(
    plot_id: Annotated[str | None, Field(description="Plot id under plots/. Provide this OR path, not both.")] = None,
    path: Annotated[str | None, Field(description="Project-relative manifest path. Provide this OR plot_id.")] = None,
) -> ReadPlotSourceResult:
    """Read an existing plot manifest + render-script source (FR-020).

    Use when:
      - You need to inspect or edit an existing plot before validating/running.

    Do NOT use to:
      - Discover targets — use ``list_plot_targets``.

    Requires EXACTLY one of ``plot_id`` or ``path``.
    """
    if (plot_id is None) == (path is None):
        raise ValueError("provide exactly one of plot_id or path.")
    loaded = _validation.load_plot(plot_id=plot_id, path=path)
    ctx = get_context()
    root = _resolve_project_root(ctx)

    def _rel(p: Path) -> str:
        try:
            return p.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:  # pragma: no cover
            return str(p)

    try:
        source = loaded.script_path.read_text(encoding="utf-8")
    except OSError:
        source = ""
    warnings: list[str] = []
    if not loaded.script_path.exists():
        warnings.append(f"render script missing on disk: {loaded.manifest.script.path}")
    return ReadPlotSourceResult(
        plot_id=loaded.plot_id,
        manifest_path=_rel(loaded.manifest_path),
        script_path=_rel(loaded.script_path),
        language=loaded.manifest.script.language,
        manifest=loaded.manifest,
        script_source=source,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# (e.5) validate_plot  (read)
# ---------------------------------------------------------------------------


@mcp.tool(name="validate_plot", tags={"category:plot", "read"})
async def validate_plot(
    plot_id: Annotated[str | None, Field(description="Plot id under plots/. Provide this OR path, not both.")] = None,
    path: Annotated[str | None, Field(description="Project-relative manifest path. Provide this OR plot_id.")] = None,
) -> ValidatePlotResult:
    """Validate a plot manifest + script (FR-021, FR-022).

    Use when:
      - Before ``run_plot_job``, to catch broken targets, schema errors, path
        traversal, unsupported output formats, and missing entrypoints.

    Do NOT use to:
      - Run the plot — use ``run_plot_job``.

    R runner unavailability is reported as a warning, never an error: manifests
    validate everywhere. Requires EXACTLY one of ``plot_id`` or ``path``.
    """
    outcome = _validation.validate_plot(plot_id=plot_id, path=path)
    return ValidatePlotResult(
        valid=outcome.valid,
        errors=outcome.errors,
        warnings=outcome.warnings,
        manifest=outcome.manifest,
    )


# ---------------------------------------------------------------------------
# (e.6) run_plot_job  (write/run)
# ---------------------------------------------------------------------------


@mcp.tool(name="run_plot_job", tags={"category:plot", "write"})
async def run_plot_job(
    plot_id: str = Field(description="Plot id under plots/ to execute."),
    run_id: Annotated[
        str | None,
        Field(description="Optional specific run id to source the target output from; defaults to latest."),
    ] = None,
    timeout_seconds: Annotated[
        float | None,
        Field(description="Optional override of the manifest timeout (re-clamped to the absolute ceiling)."),
    ] = None,
) -> PlotRunResult:
    """Run a plot job preview-side and write display-only artifacts (FR-023..FR-031).

    Use when:
      - ``validate_plot`` passed and you want to render the figure into the
        preview panel.

    Do NOT use to:
      - Produce workflow data — a plot job is PREVIEW-ONLY. It never registers
        a workflow node, edits workflow YAML, creates a downstream collection,
        or claims lineage (FR-025).

    Writes ``.scistudio/previews/<workflow_id>/<node_id>/<output_port>/<plot_id>/
    current.*`` + ``current.json``, overwriting any prior current artifacts.
    Enforces timeout, output-size, and file-count caps with sanitized errors.
    The artifact is consumable by the core PlotPreviewer.
    """
    return _runtime.run_plot_job(plot_id=plot_id, run_id=run_id, timeout_seconds=timeout_seconds)


__all__ = [
    "list_plot_examples",
    "list_plot_targets",
    "read_plot_source",
    "run_plot_job",
    "scaffold_plot",
    "validate_plot",
]
