"""Pydantic models for ADR-048 SPEC 2 plot tools (FR-005, FR-009, FR-010, FR-022, FR-028, FR-030).

These models are the wire contract for the six ``category:plot`` MCP tools and
for the ``plot.yaml`` manifest. They are deliberately strict (``extra="forbid"``
where a closed schema is meaningful) so an agent that hand-edits a manifest into
an unexpected shape gets a validation error from :mod:`validation` rather than a
silent mis-run.

Nothing here imports ``scistudio.blocks`` / ``scistudio.previewers`` at module
load time — the runtime borrows the CodeBlock subprocess primitive by a local
import inside :mod:`runtime` so this module stays cheap and side-effect free.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PlotLanguage = Literal["python", "r"]
PlotFormat = Literal["svg", "pdf", "png", "jpeg"]
PlotStatus = Literal["succeeded", "failed", "cancelled", "timed_out"]

# Default caps (FR-029). Manifest ``limits`` may tighten these; the runtime
# always re-clamps to the absolute ceilings so a hand-edited manifest cannot
# raise the caps beyond the safe envelope.
DEFAULT_TIMEOUT_SECONDS: float = 30.0
ABSOLUTE_MAX_TIMEOUT_SECONDS: float = 300.0
DEFAULT_MAX_ROWS: int = 10000
DEFAULT_MAX_OUTPUT_BYTES: int = 10 * 1024 * 1024  # 10 MiB
ABSOLUTE_MAX_OUTPUT_BYTES: int = 64 * 1024 * 1024  # 64 MiB
DEFAULT_MAX_FILES: int = 8
ABSOLUTE_MAX_FILES: int = 32
LOG_TRUNCATE_BYTES: int = 16 * 1024  # 16 KiB per stream (FR-029)


def _default_allowed_formats() -> list[PlotFormat]:
    """Default ``allowed_formats`` — all four supported export formats (FR-018)."""
    return ["svg", "pdf", "png", "jpeg"]


# ---------------------------------------------------------------------------
# Plot targets (FR-005).
# ---------------------------------------------------------------------------


class PlotTarget(BaseModel):
    """A discovered plot target — one output port of one workflow node (FR-005).

    ``target_id`` is the opaque stable selector callers pass back to
    ``scaffold_plot`` (FR-006). It is derived deterministically from
    ``workflow_path`` + ``node_id`` + ``output_port`` so repeated blocks with
    identical labels still resolve to distinct targets (SC-002).
    """

    model_config = ConfigDict(extra="forbid")

    target_id: str = Field(description="Opaque stable selector returned by list_plot_targets.")
    workflow_path: str = Field(description="Project-relative workflow file path.")
    workflow_id: str | None = Field(default=None, description="Stable workflow ID when available.")
    node_id: str = Field(description="Stable node ID.")
    node_label: str = Field(default="", description="Human display label only — never used for binding.")
    block_type: str = Field(description="Block type or package-qualified block ID.")
    output_port: str = Field(description="Output port name.")
    output_type: str = Field(default="", description="Recorded output type when known.")
    is_collection: bool = Field(default=False, description="Whether the latest output is a collection.")
    latest_run_id: str | None = Field(default=None, description="Latest run ID when available.")
    latest_output_available: bool = Field(
        default=False,
        description="Whether a plot can run immediately against a recorded output.",
    )
    diagnostics: list[str] = Field(
        default_factory=list,
        description="Missing-output or broken-target details.",
    )


class ListPlotTargetsResult(BaseModel):
    """Result envelope for ``list_plot_targets``."""

    model_config = ConfigDict(extra="forbid")

    targets: list[PlotTarget] = Field(default_factory=list)
    count: int = Field(description="Number of targets returned.")
    next_step: str = Field(
        default=(
            "Pick a target_id, then call mcp__scistudio__scaffold_plot(plot_id=..., "
            "target_id=..., language='python'|'r'). Never bind a plot by node label alone."
        ),
        description="Suggested next MCP call.",
    )


# ---------------------------------------------------------------------------
# plot.yaml manifest model (FR-010, FR-011).
# ---------------------------------------------------------------------------


class PlotManifestTarget(BaseModel):
    """The ``target:`` block of plot.yaml (FR-011) — stable identity only."""

    model_config = ConfigDict(extra="forbid")

    workflow_path: str = Field(description="Project-relative workflow file path.")
    workflow_id: str | None = Field(default=None, description="Stable workflow ID when available.")
    node_id: str = Field(description="Stable node ID — the binding key, never the label.")
    output_port: str = Field(description="Output port name.")
    display_label: str = Field(default="", description="Human display label only.")


class PlotManifestScript(BaseModel):
    """The ``script:`` block of plot.yaml (FR-012, FR-013)."""

    model_config = ConfigDict(extra="forbid")

    language: PlotLanguage = Field(description="python or r.")
    path: str = Field(description="Project-relative-to-the-plot-dir render script filename.")
    entrypoint: str = Field(default="render", description="Render function name; must be 'render'.")


class PlotManifestOutputs(BaseModel):
    """The ``outputs:`` block of plot.yaml (FR-018)."""

    model_config = ConfigDict(extra="forbid")

    preferred_format: PlotFormat = Field(default="svg")
    allowed_formats: list[PlotFormat] = Field(default_factory=_default_allowed_formats)


class PlotManifestRuntime(BaseModel):
    """The ``runtime:`` block of plot.yaml (FR-029)."""

    model_config = ConfigDict(extra="forbid")

    timeout_seconds: float = Field(default=DEFAULT_TIMEOUT_SECONDS, gt=0)


class PlotManifestLimits(BaseModel):
    """The ``limits:`` block of plot.yaml (FR-029)."""

    model_config = ConfigDict(extra="forbid")

    max_rows: int = Field(default=DEFAULT_MAX_ROWS, gt=0)
    max_output_bytes: int = Field(default=DEFAULT_MAX_OUTPUT_BYTES, gt=0)
    max_files: int = Field(default=DEFAULT_MAX_FILES, gt=0)


class PlotManifest(BaseModel):
    """Strict, versioned ``plot.yaml`` model (FR-010)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(description="Manifest schema version; must be 1.")
    id: str = Field(description="Plot ID — also the plots/<id>/ directory name.")
    title: str = Field(default="", description="Human title for the plot.")
    target: PlotManifestTarget
    script: PlotManifestScript
    outputs: PlotManifestOutputs = Field(default_factory=PlotManifestOutputs)
    runtime: PlotManifestRuntime = Field(default_factory=PlotManifestRuntime)
    limits: PlotManifestLimits = Field(default_factory=PlotManifestLimits)


# ---------------------------------------------------------------------------
# scaffold_plot (FR-009).
# ---------------------------------------------------------------------------


class ScaffoldPlotResult(BaseModel):
    """Result envelope for ``scaffold_plot`` (write-class, FR-009)."""

    model_config = ConfigDict(extra="forbid")

    plot_id: str = Field(description="Plot ID that was scaffolded.")
    manifest_path: str = Field(description="Project-relative path of plots/<id>/plot.yaml.")
    script_path: str = Field(description="Project-relative path of the render script.")
    bytes_written: int = Field(description="Total bytes written (manifest + script).")
    warnings: list[str] = Field(default_factory=list, description="Soft advisory notes.")
    next_step: str = Field(
        default=(
            "Edit the render script to draw your figure, then call "
            "mcp__scistudio__validate_plot(plot_id=...) and "
            "mcp__scistudio__run_plot_job(plot_id=...). A plot is preview-only — it "
            "never becomes a workflow node and never claims lineage."
        ),
        description="Suggested next MCP call.",
    )


# ---------------------------------------------------------------------------
# list_plot_examples (FR-019).
# ---------------------------------------------------------------------------


class PlotExample(BaseModel):
    """One curated example entry (FR-019)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    language: PlotLanguage
    library: str = Field(description="matplotlib, seaborn, or ggplot2.")
    title: str
    description: str
    source: str = Field(description="Full render-script source for the example.")
    output_formats: list[PlotFormat] = Field(default_factory=list)


class ListPlotExamplesResult(BaseModel):
    """Result envelope for ``list_plot_examples``."""

    model_config = ConfigDict(extra="forbid")

    examples: list[PlotExample] = Field(default_factory=list)
    count: int


# ---------------------------------------------------------------------------
# read_plot_source (FR-020).
# ---------------------------------------------------------------------------


class ReadPlotSourceResult(BaseModel):
    """Result envelope for ``read_plot_source`` (FR-020)."""

    model_config = ConfigDict(extra="forbid")

    plot_id: str
    manifest_path: str = Field(description="Project-relative path of plot.yaml.")
    script_path: str = Field(description="Project-relative path of the render script.")
    language: PlotLanguage
    manifest: PlotManifest = Field(description="Normalized manifest data.")
    script_source: str = Field(description="Full render-script source text.")
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# validate_plot (FR-021, FR-022).
# ---------------------------------------------------------------------------


class ValidatePlotResult(BaseModel):
    """Result envelope for ``validate_plot`` (FR-022)."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    manifest: PlotManifest | None = Field(
        default=None,
        description="Normalized manifest data when the manifest parsed; None on schema failure.",
    )
    next_step: str = Field(
        default=(
            "If valid, call mcp__scistudio__run_plot_job(plot_id=...). If not, fix the "
            "reported errors in plot.yaml / the render script and re-validate."
        ),
        description="Suggested next MCP call.",
    )


# ---------------------------------------------------------------------------
# run_plot_job (FR-028, FR-030).
# ---------------------------------------------------------------------------


class PlotArtifact(BaseModel):
    """One display-only artifact written to the preview cache (FR-026)."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(description="Artifact filename, e.g. current.svg.")
    format: PlotFormat
    path: str = Field(description="Absolute filesystem path of the artifact in the preview cache.")
    size_bytes: int


class PlotRunResult(BaseModel):
    """Result envelope for ``run_plot_job`` (write/run-class, FR-030)."""

    model_config = ConfigDict(extra="forbid")

    status: PlotStatus
    returncode: int | None = Field(default=None, description="Process return code when available.")
    artifact_paths: list[str] = Field(
        default_factory=list,
        description="Absolute preview-cache paths of the written display artifacts.",
    )
    metadata_path: str | None = Field(default=None, description="Absolute path to current.json.")
    cache_key: str | None = Field(default=None, description="Preview cache key for UI refresh.")
    stdout: str = Field(default="", description="Truncated stdout (FR-029).")
    stderr: str = Field(default="", description="Truncated, sanitized stderr (FR-029).")
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    next_step: str = Field(
        default=(
            "On success, the artifact shows through the core PlotPreviewer in the preview "
            "panel. To change the figure, edit the render script and re-run. To keep the "
            "artifact, explicitly export/save it — the preview cache is not a result path."
        ),
        description="Suggested next action.",
    )


__all__ = [
    "ABSOLUTE_MAX_FILES",
    "ABSOLUTE_MAX_OUTPUT_BYTES",
    "ABSOLUTE_MAX_TIMEOUT_SECONDS",
    "DEFAULT_MAX_FILES",
    "DEFAULT_MAX_OUTPUT_BYTES",
    "DEFAULT_MAX_ROWS",
    "DEFAULT_TIMEOUT_SECONDS",
    "LOG_TRUNCATE_BYTES",
    "ListPlotExamplesResult",
    "ListPlotTargetsResult",
    "PlotArtifact",
    "PlotExample",
    "PlotFormat",
    "PlotLanguage",
    "PlotManifest",
    "PlotManifestLimits",
    "PlotManifestOutputs",
    "PlotManifestRuntime",
    "PlotManifestScript",
    "PlotManifestTarget",
    "PlotRunResult",
    "PlotStatus",
    "PlotTarget",
    "ReadPlotSourceResult",
    "ScaffoldPlotResult",
    "ValidatePlotResult",
]
