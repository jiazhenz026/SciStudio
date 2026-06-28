"""First-class plot engine — the ``render(collection)`` authoring contract + runtime.

Relocated out of ``scistudio.ai.agent.mcp.tools_plot`` in #1824 (ADR-052 §9):
plots are a first-class user feature, not an AI-agent concern. The user-facing
REST route (``scistudio.api.routes.plots``) and the MCP plot tools
(``scistudio.ai.agent.mcp.tools_plot.tools``) both depend on this package; this
package depends on neither (no import of ``scistudio.api`` or ``scistudio.ai``).

Callers inject a :class:`PlotRuntimeContext` (REST: ``ApiRuntime``; MCP: the
agent context) into the engine entry points, replacing the previous global
``mcp._context`` coupling. The ``render(collection)`` shape + return contract are
unchanged (behavior-preserving relocation).
"""

from __future__ import annotations

from scistudio.plot._context import (
    PlotRuntimeContext,
    resolve_project_path,
    resolve_project_root,
    safe_under,
)
from scistudio.plot.examples import list_examples
from scistudio.plot.models import (
    ListPlotExamplesResult,
    ListPlotTargetsResult,
    PlotArtifact,
    PlotExample,
    PlotFormat,
    PlotLanguage,
    PlotManifest,
    PlotManifestTarget,
    PlotPreviewTarget,
    PlotRunResult,
    PlotStatus,
    PlotTarget,
    ReadPlotSourceResult,
    ScaffoldPlotResult,
    ValidatePlotResult,
)
from scistudio.plot.relink import PlotRelinkError, RelinkOutcome, relink_plot
from scistudio.plot.runtime import cache_key_for, preview_cache_dir, run_plot_job
from scistudio.plot.scaffold import (
    PlotScaffoldError,
    render_manifest_yaml,
    scaffold_plot_files,
    validate_plot_id,
)
from scistudio.plot.targets import discover_targets, make_target_id, resolve_target_by_id
from scistudio.plot.validation import (
    LoadedPlot,
    PlotNotFoundError,
    ValidationOutcome,
    load_plot,
    resolve_manifest_path,
    resolve_script_path,
    validate_plot,
)

__all__ = [
    "ListPlotExamplesResult",
    "ListPlotTargetsResult",
    "LoadedPlot",
    "PlotArtifact",
    "PlotExample",
    "PlotFormat",
    "PlotLanguage",
    # Models
    "PlotManifest",
    "PlotManifestTarget",
    "PlotNotFoundError",
    "PlotPreviewTarget",
    "PlotRelinkError",
    "PlotRunResult",
    # Injected context contract
    "PlotRuntimeContext",
    "PlotScaffoldError",
    "PlotStatus",
    "PlotTarget",
    "ReadPlotSourceResult",
    "RelinkOutcome",
    "ScaffoldPlotResult",
    "ValidatePlotResult",
    "ValidationOutcome",
    "cache_key_for",
    # Target discovery
    "discover_targets",
    # Examples
    "list_examples",
    # Load / validate
    "load_plot",
    "make_target_id",
    "preview_cache_dir",
    "relink_plot",
    "render_manifest_yaml",
    "resolve_manifest_path",
    "resolve_project_path",
    "resolve_project_root",
    "resolve_script_path",
    "resolve_target_by_id",
    # Execution
    "run_plot_job",
    "safe_under",
    # Authoring (scaffold / relink)
    "scaffold_plot_files",
    "validate_plot",
    "validate_plot_id",
]
