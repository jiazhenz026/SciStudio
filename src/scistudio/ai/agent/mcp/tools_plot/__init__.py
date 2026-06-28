"""Category (e) MCP tools — preview-side plot authoring (ADR-048 SPEC 2).

Importing this package runs the ``@mcp.tool`` decorators in :mod:`tools` as a
side effect, registering the six ``category:plot`` tools on the shared FastMCP
instance (FR-002). The eager import lives in
``scistudio.ai.agent.mcp.__init__`` alongside the other tool modules.

A plot job is PREVIEW-ONLY: it never becomes a workflow block, never edits
workflow YAML, and never claims lineage (FR-025). The plot tools deliberately
do NOT reuse block-reuse / reload semantics — plot targets are workflow output
ports, not reusable block types.
"""

from __future__ import annotations

# Side-effect import: registers the six @mcp.tool functions.
from scistudio.ai.agent.mcp.tools_plot.tools import (
    list_plot_examples,
    list_plot_targets,
    read_plot_source,
    run_plot_job,
    scaffold_plot,
    validate_plot,
)

# Models moved to the first-class ``scistudio.plot`` package (#1824); re-exported
# here for back-compat so existing ``...tools_plot import <Model>`` imports keep
# working. The canonical home is ``scistudio.plot.models``.
from scistudio.plot.models import (
    ListPlotExamplesResult,
    ListPlotTargetsResult,
    PlotArtifact,
    PlotExample,
    PlotManifest,
    PlotPreviewTarget,
    PlotRunResult,
    PlotTarget,
    ReadPlotSourceResult,
    ScaffoldPlotResult,
    ValidatePlotResult,
)

__all__ = [
    "ListPlotExamplesResult",
    "ListPlotTargetsResult",
    "PlotArtifact",
    "PlotExample",
    "PlotManifest",
    "PlotPreviewTarget",
    "PlotRunResult",
    "PlotTarget",
    "ReadPlotSourceResult",
    "ScaffoldPlotResult",
    "ValidatePlotResult",
    "list_plot_examples",
    "list_plot_targets",
    "read_plot_source",
    "run_plot_job",
    "scaffold_plot",
    "validate_plot",
]
