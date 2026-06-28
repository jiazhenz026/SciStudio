"""Data models for the plot tools and the ``plot.yaml`` manifest.

These are the shared, validated shapes the plot engine uses everywhere: the
result objects the plot tools return, and the ``plot.yaml`` manifest that records
which workflow output a plot draws and how it renders. They are deliberately
strict (``extra="forbid"`` where a closed schema is meaningful) so that a
hand-edited manifest with an unexpected field is rejected with a clear error from
:mod:`validation` rather than running with the typo silently ignored.

Importing this module is cheap and has no side effects: nothing here imports
``scistudio.blocks`` / ``scistudio.previewers`` at load time.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PlotLanguage = Literal["python", "r"]
"""Language a render script is written in: ``"python"`` or ``"r"``."""
PlotFormat = Literal["svg", "pdf", "png", "jpeg"]
"""Supported export image format for a rendered figure."""
PlotStatus = Literal["succeeded", "failed", "cancelled", "timed_out"]
"""Outcome of a plot run: succeeded, failed, cancelled, or timed out."""

# Default and absolute caps for a plot run. A manifest's ``limits`` block may
# tighten the defaults; the runtime always re-clamps to the absolute ceilings so
# a hand-edited manifest cannot raise a cap beyond the safe envelope.
DEFAULT_TIMEOUT_SECONDS: float = 30.0
"""Default wall-clock seconds a render script may run before it is killed."""
ABSOLUTE_MAX_TIMEOUT_SECONDS: float = 300.0
"""Hard ceiling (seconds) on a render run; a manifest cannot exceed this."""
DEFAULT_MAX_OUTPUT_BYTES: int = 10 * 1024 * 1024  # 10 MiB
"""Default cap on the combined size of the artifacts a plot may write (10 MiB)."""
ABSOLUTE_MAX_OUTPUT_BYTES: int = 64 * 1024 * 1024  # 64 MiB
"""Hard ceiling on combined artifact size (64 MiB), regardless of the manifest."""
DEFAULT_MAX_INPUT_BYTES: int = 64 * 1024 * 1024  # 64 MiB
"""Default cap on the size of a single input loaded into memory (64 MiB)."""
ABSOLUTE_MAX_INPUT_BYTES: int = 512 * 1024 * 1024  # 512 MiB
"""Hard ceiling on a single input's in-memory size (512 MiB)."""
DEFAULT_MAX_FILES: int = 8
"""Default cap on how many artifact files one render run may produce."""
ABSOLUTE_MAX_FILES: int = 32
"""Hard ceiling on the number of artifact files per run, regardless of the manifest."""
LOG_TRUNCATE_BYTES: int = 16 * 1024  # 16 KiB per stream
"""Per-stream cap (16 KiB) on captured stdout/stderr; longer logs are truncated."""


def _default_allowed_formats() -> list[PlotFormat]:
    """Default ``allowed_formats`` — all four supported export formats."""
    return ["svg", "pdf", "png", "jpeg"]


# ---------------------------------------------------------------------------
# Plot targets.
# ---------------------------------------------------------------------------


class PlotTarget(BaseModel):
    """One output port of one workflow node that a plot can draw from.

    A *plot target* names exactly where a plot gets its data: a single output
    port of a single node in one of the project's workflows. ``list_plot_targets``
    returns one of these per available output; you pick one and pass its
    ``target_id`` to ``scaffold_plot`` to create a plot bound to it.

    A plot always binds by ``node_id`` + ``output_port``, never by the human
    label, so two blocks that share a display name still resolve to distinct
    targets. The ``target_id`` is a stable hash of the workflow path, node id, and
    output port, so it stays the same across runs as long as the node does.

    Example:
        >>> target = PlotTarget(
        ...     target_id="tgt_1a2b3c4d5e6f7a8b",
        ...     workflow_path="workflows/main.yaml",
        ...     node_id="node-7",
        ...     block_type="LoadCSV",
        ...     output_port="table",
        ... )
        >>> target.is_collection
        False
    """

    model_config = ConfigDict(extra="forbid")

    target_id: str = Field(description="Opaque stable selector returned by list_plot_targets.")
    """Stable selector for this target; pass it to ``scaffold_plot`` to bind a plot."""
    workflow_path: str = Field(description="Project-relative workflow file path.")
    """Workflow file this target lives in, relative to the project root."""
    workflow_id: str | None = Field(default=None, description="Stable workflow ID when available.")
    """Stable workflow identifier, or ``None`` when the workflow records none."""
    node_id: str = Field(description="Stable node ID.")
    """Identifier of the workflow node that produces the output — the binding key."""
    node_label: str = Field(default="", description="Human display label only — never used for binding.")
    """Human-readable node label, for display only; never used to bind a plot."""
    block_type: str = Field(description="Block type or package-qualified block ID.")
    """Type of block at this node, e.g. a built-in name or a package-qualified id."""
    output_port: str = Field(description="Output port name.")
    """Name of the node's output port this target draws from."""
    output_type: str = Field(default="", description="Recorded output type when known.")
    """Recorded data type of the output when known, else an empty string."""
    is_collection: bool = Field(default=False, description="Whether the latest output is a collection.")
    """``True`` when the latest recorded output holds more than one item."""
    latest_run_id: str | None = Field(default=None, description="Latest run ID when available.")
    """Run id of the most recent run that produced this output, if any."""
    latest_output_available: bool = Field(
        default=False,
        description="Whether a plot can run immediately against a recorded output.",
    )
    """``True`` when a recorded output exists, so a plot can run without re-running the workflow."""
    diagnostics: list[str] = Field(
        default_factory=list,
        description="Missing-output or broken-target details.",
    )
    """Human-readable notes explaining why a target is unavailable or broken, if any."""


class ListPlotTargetsResult(BaseModel):
    """What ``list_plot_targets`` returns: the plottable outputs in a project.

    A small wrapper around the list of discovered :class:`PlotTarget` objects,
    plus a count and a plain-language hint for the next step. Read ``targets`` to
    see the available outputs and pick a ``target_id`` to plot.
    """

    model_config = ConfigDict(extra="forbid")

    targets: list[PlotTarget] = Field(default_factory=list)
    """The discovered plot targets across the project's workflows."""
    count: int = Field(description="Number of targets returned.")
    """How many targets are in ``targets``."""
    next_step: str = Field(
        default=(
            "Pick a target_id, then call mcp__scistudio__scaffold_plot(plot_id=..., "
            "target_id=..., language='python'|'r'). Never bind a plot by node label alone."
        ),
        description="Suggested next MCP call.",
    )
    """Plain-language hint describing the suggested next call."""


# ---------------------------------------------------------------------------
# plot.yaml manifest model.
# ---------------------------------------------------------------------------


class PlotManifestTarget(BaseModel):
    """The ``target:`` section of ``plot.yaml`` — which output a plot draws.

    Records the stable identity of the bound workflow output: the workflow file,
    the node, and the output port. Binding is always by ``node_id`` +
    ``output_port``; the label is stored for display only. If the node is deleted
    and recreated it gets a new ``node_id`` and the binding goes stale — use
    ``relink_plot`` to point the plot at the new target.

    Example:
        >>> target = PlotManifestTarget(
        ...     workflow_path="workflows/main.yaml",
        ...     node_id="node-7",
        ...     output_port="table",
        ... )
        >>> target.display_label
        ''
    """

    model_config = ConfigDict(extra="forbid")

    workflow_path: str = Field(description="Project-relative workflow file path.")
    """Workflow file the bound output lives in, relative to the project root."""
    workflow_id: str | None = Field(default=None, description="Stable workflow ID when available.")
    """Stable workflow identifier, or ``None`` when the workflow records none."""
    node_id: str = Field(description="Stable node ID — the binding key, never the label.")
    """Identifier of the bound node; this, with ``output_port``, is the binding key."""
    output_port: str = Field(description="Output port name.")
    """Name of the bound node's output port."""
    display_label: str = Field(default="", description="Human display label only.")
    """Human-readable node label, kept for display only; never used to bind."""


class PlotManifestScript(BaseModel):
    """The ``script:`` section of ``plot.yaml`` — the render script to run.

    Names the render script file, its language, and the entrypoint function. The
    entrypoint must be ``render`` and the script must define ``render(collection)``
    with one positional argument.
    """

    model_config = ConfigDict(extra="forbid")

    language: PlotLanguage = Field(description="python or r.")
    """Language the render script is written in."""
    path: str = Field(description="Project-relative-to-the-plot-dir render script filename.")
    """Render script filename, relative to the plot's own ``plots/<id>/`` directory."""
    entrypoint: str = Field(default="render", description="Render function name; must be 'render'.")
    """Name of the function the runner calls; must be ``"render"``."""


class PlotManifestOutputs(BaseModel):
    """The ``outputs:`` section of ``plot.yaml`` — image formats to produce.

    Declares the preferred export format and the set of formats the plot is
    allowed to write. The preferred format must be one of the allowed formats.
    """

    model_config = ConfigDict(extra="forbid")

    preferred_format: PlotFormat = Field(default="svg")
    """Format the runner saves by default; must appear in ``allowed_formats``."""
    allowed_formats: list[PlotFormat] = Field(default_factory=_default_allowed_formats)
    """Formats the plot is permitted to write (defaults to all four)."""


class PlotManifestRuntime(BaseModel):
    """The ``runtime:`` section of ``plot.yaml`` — per-run execution limits.

    Holds the render timeout. The runtime re-clamps this to the absolute ceiling
    (:data:`ABSOLUTE_MAX_TIMEOUT_SECONDS`) so a manifest cannot exceed it.
    """

    model_config = ConfigDict(extra="forbid")

    timeout_seconds: float = Field(default=DEFAULT_TIMEOUT_SECONDS, gt=0)
    """Wall-clock seconds the render script may run before it is killed."""


class PlotManifestLimits(BaseModel):
    """The ``limits:`` section of ``plot.yaml`` — input/output size caps.

    Caps on input size, total output size, and artifact count for one run. The
    runtime re-clamps each value to its absolute ceiling, so a manifest can only
    tighten the defaults, never raise them past the safe envelope.
    """

    model_config = ConfigDict(extra="forbid")

    max_input_bytes: int = Field(default=DEFAULT_MAX_INPUT_BYTES, gt=0)
    """Largest single input (in bytes) the render script may load into memory."""
    max_output_bytes: int = Field(default=DEFAULT_MAX_OUTPUT_BYTES, gt=0)
    """Combined size cap (in bytes) on all artifacts one run may write."""
    max_files: int = Field(default=DEFAULT_MAX_FILES, gt=0)
    """Maximum number of artifact files one run may produce."""


class PlotManifest(BaseModel):
    """The full ``plot.yaml`` manifest for one plot.

    A plot is described entirely by its ``plot.yaml``: which workflow output it
    draws (:class:`PlotManifestTarget`), which render script runs
    (:class:`PlotManifestScript`), and the output formats and limits. This model
    is the validated, in-memory form of that file. ``scaffold_plot`` writes one;
    ``validate_plot`` and ``run_plot_job`` read it back. A plot is preview-only:
    it never becomes a workflow node and never claims lineage.

    Example:
        >>> manifest = PlotManifest(
        ...     schema_version=1,
        ...     id="qc_scatter",
        ...     target=PlotManifestTarget(
        ...         workflow_path="workflows/main.yaml",
        ...         node_id="node-7",
        ...         output_port="table",
        ...     ),
        ...     script=PlotManifestScript(language="python", path="render.py"),
        ... )
        >>> manifest.outputs.preferred_format
        'svg'
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(description="Manifest schema version; must be 1.")
    """Manifest format version; only ``1`` is supported."""
    id: str = Field(description="Plot ID — also the plots/<id>/ directory name.")
    """Plot identifier; also the name of the plot's ``plots/<id>/`` directory."""
    title: str = Field(default="", description="Human title for the plot.")
    """Human-readable title shown for the plot."""
    target: PlotManifestTarget
    """Which workflow output this plot draws from."""
    script: PlotManifestScript
    """Which render script runs and in what language."""
    outputs: PlotManifestOutputs = Field(default_factory=PlotManifestOutputs)
    """Export formats the plot may produce."""
    runtime: PlotManifestRuntime = Field(default_factory=PlotManifestRuntime)
    """Per-run execution limits (the render timeout)."""
    limits: PlotManifestLimits = Field(default_factory=PlotManifestLimits)
    """Per-run input/output size caps."""


# ---------------------------------------------------------------------------
# scaffold_plot.
# ---------------------------------------------------------------------------


class ScaffoldPlotResult(BaseModel):
    """What ``scaffold_plot`` returns after creating a new plot.

    Reports where the new ``plot.yaml`` and render script were written, how many
    bytes were written, any soft warnings, and a hint for the next step (edit the
    script, then validate and run).
    """

    model_config = ConfigDict(extra="forbid")

    plot_id: str = Field(description="Plot ID that was scaffolded.")
    """Identifier of the plot that was created."""
    manifest_path: str = Field(description="Project-relative path of plots/<id>/plot.yaml.")
    """Project-relative path of the written ``plot.yaml``."""
    script_path: str = Field(description="Project-relative path of the render script.")
    """Project-relative path of the written render script."""
    bytes_written: int = Field(description="Total bytes written (manifest + script).")
    """Combined size of the manifest and render script just written."""
    warnings: list[str] = Field(default_factory=list, description="Soft advisory notes.")
    """Advisory notes that do not block using the new plot."""
    next_step: str = Field(
        default=(
            "Edit the render script to draw your figure, then call "
            "mcp__scistudio__validate_plot(plot_id=...) and "
            "mcp__scistudio__run_plot_job(plot_id=...). A plot is preview-only — it "
            "never becomes a workflow node and never claims lineage."
        ),
        description="Suggested next MCP call.",
    )
    """Plain-language hint describing the suggested next call."""


# ---------------------------------------------------------------------------
# list_plot_examples.
# ---------------------------------------------------------------------------


class PlotExample(BaseModel):
    """One curated, ready-to-adapt render-script example.

    Each example pairs a short description with a full ``render`` script for a
    common plotting library. ``list_examples`` returns these so an author can copy
    one into a plot's render script and adapt it.

    Example:
        >>> from scistudio.plot import list_examples
        >>> example = list_examples(language="python", library="matplotlib")[0]
        >>> "def render(collection):" in example.source
        True
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    """Stable identifier for the example."""
    language: PlotLanguage
    """Language the example's render script is written in."""
    library: str = Field(description="matplotlib, seaborn, or ggplot2.")
    """Plotting library the example uses (matplotlib, seaborn, or ggplot2)."""
    title: str
    """Short human-readable title."""
    description: str
    """One-line summary of what the example draws and how."""
    source: str = Field(description="Full render-script source for the example.")
    """Complete render-script source an author can copy and adapt."""
    output_formats: list[PlotFormat] = Field(default_factory=list)
    """Export formats the example is intended to produce."""


class ListPlotExamplesResult(BaseModel):
    """What ``list_plot_examples`` returns: curated examples plus a count."""

    model_config = ConfigDict(extra="forbid")

    examples: list[PlotExample] = Field(default_factory=list)
    """The curated examples, filtered by any requested language/library."""
    count: int
    """How many examples are in ``examples``."""


# ---------------------------------------------------------------------------
# read_plot_source.
# ---------------------------------------------------------------------------


class ReadPlotSourceResult(BaseModel):
    """What ``read_plot_source`` returns: a plot's manifest and script text.

    Bundles the parsed manifest and the full render-script source so a caller can
    inspect or edit an existing plot without reading the files directly.
    """

    model_config = ConfigDict(extra="forbid")

    plot_id: str
    """Identifier of the plot that was read."""
    manifest_path: str = Field(description="Project-relative path of plot.yaml.")
    """Project-relative path of the plot's ``plot.yaml``."""
    script_path: str = Field(description="Project-relative path of the render script.")
    """Project-relative path of the plot's render script."""
    language: PlotLanguage
    """Language of the render script."""
    manifest: PlotManifest = Field(description="Normalized manifest data.")
    """The parsed, validated manifest."""
    script_source: str = Field(description="Full render-script source text.")
    """Complete source text of the render script."""
    warnings: list[str] = Field(default_factory=list)
    """Advisory notes raised while reading the plot, if any."""


# ---------------------------------------------------------------------------
# validate_plot.
# ---------------------------------------------------------------------------


class ValidatePlotResult(BaseModel):
    """What ``validate_plot`` returns: whether a plot is ready to run.

    ``valid`` is ``True`` only when there are no errors. ``errors`` block a run
    (bad manifest, missing script, broken target); ``warnings`` are advisory
    (e.g. R is not installed) and never block. ``manifest`` is the parsed manifest
    when it parsed at all, else ``None``.
    """

    model_config = ConfigDict(extra="forbid")

    valid: bool
    """``True`` only when there are no blocking errors."""
    errors: list[str] = Field(default_factory=list)
    """Problems that must be fixed before the plot can run."""
    warnings: list[str] = Field(default_factory=list)
    """Advisory notes that do not block a run."""
    manifest: PlotManifest | None = Field(
        default=None,
        description="Normalized manifest data when the manifest parsed; None on schema failure.",
    )
    """The parsed manifest, or ``None`` when the manifest failed to parse."""
    next_step: str = Field(
        default=(
            "If valid, call mcp__scistudio__run_plot_job(plot_id=...). If not, fix the "
            "reported errors in plot.yaml / the render script and re-validate."
        ),
        description="Suggested next MCP call.",
    )
    """Plain-language hint describing the suggested next call."""


# ---------------------------------------------------------------------------
# run_plot_job.
# ---------------------------------------------------------------------------


class PlotArtifact(BaseModel):
    """One display-only image file produced by a plot run.

    Describes a single rendered figure written to the preview cache: its
    filename, format, absolute path, and size. These artifacts are for preview
    only — to keep one, export or save it explicitly.
    """

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(description="Artifact filename, e.g. current.svg.")
    """Name of the artifact file, e.g. ``current.svg``."""
    format: PlotFormat
    """Image format of the artifact."""
    path: str = Field(description="Absolute filesystem path of the artifact in the preview cache.")
    """Absolute path of the artifact inside the preview cache."""
    size_bytes: int
    """Size of the artifact file in bytes."""


class PlotPreviewTarget(BaseModel):
    """A preview-panel target pointing at a registered plot artifact.

    After a plot run registers its artifact, this describes how the preview panel
    should show it. It mirrors the app's generic preview-target shape closely
    enough to hand straight to the preview API or report back to the UI.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["plot_artifact"] = "plot_artifact"
    """Discriminator marking this as a plot-artifact preview target."""
    ref: str = Field(description="Catalog data_ref for the registered plot artifact.")
    """Catalog reference of the registered artifact to preview."""
    recorded_type: str = Field(default="PlotArtifact")
    """Recorded type name of the artifact (``"PlotArtifact"``)."""
    type_chain: list[str] = Field(default_factory=lambda: ["DataObject", "PlotArtifact"])
    """Type chain from general to specific, used by the preview panel to route."""
    source: dict[str, str | None] | None = Field(default=None)
    """Optional provenance (workflow/node/port) the artifact was produced from."""


class PlotRunResult(BaseModel):
    """What ``run_plot_job`` returns after executing a plot.

    Carries the run outcome end to end: a status, the process return code, the
    paths of any artifacts written to the preview cache, optional catalog/preview
    references when the artifact was registered, truncated logs, and any warnings
    or errors. On success the figure shows through the preview panel; the preview
    cache is not a durable result path, so export the artifact to keep it.
    """

    model_config = ConfigDict(extra="forbid")

    status: PlotStatus
    """Outcome of the run (succeeded, failed, cancelled, or timed out)."""
    returncode: int | None = Field(default=None, description="Process return code when available.")
    """Exit code of the render process, or ``None`` when it never ran."""
    artifact_paths: list[str] = Field(
        default_factory=list,
        description="Absolute preview-cache paths of the written display artifacts.",
    )
    """Absolute preview-cache paths of the figures the run wrote."""
    data_ref: str | None = Field(
        default=None,
        description="Catalog id for the first artifact when a live preview catalog is available.",
    )
    """Catalog id of the first artifact when a live preview catalog registered it."""
    recorded_type: str = Field(default="PlotArtifact", description="Recorded type of the catalog artifact.")
    """Recorded type name of the registered artifact."""
    type_chain: list[str] = Field(default_factory=list, description="Ordered general -> specific type chain.")
    """Artifact type chain from general to specific, when registered."""
    preview_target: PlotPreviewTarget | None = Field(
        default=None,
        description="PreviewHost-ready plot_artifact target when the artifact was registered.",
    )
    """A ready-to-show preview target when the artifact was registered, else ``None``."""
    metadata_path: str | None = Field(default=None, description="Absolute path to current.json.")
    """Absolute path to the run record (``current.json``) in the preview cache."""
    cache_key: str | None = Field(default=None, description="Preview cache key for UI refresh.")
    """Stable key the UI can poll to refresh this plot's preview."""
    stdout: str = Field(default="", description="Truncated stdout (FR-029).")
    """Captured standard output from the render run, truncated if long."""
    stderr: str = Field(default="", description="Truncated, sanitized stderr (FR-029).")
    """Captured standard error, truncated and with project paths stripped."""
    warnings: list[str] = Field(default_factory=list)
    """Advisory notes about the run that do not mark it failed."""
    errors: list[str] = Field(default_factory=list)
    """Reasons the run failed, when ``status`` is not ``"succeeded"``."""
    next_step: str = Field(
        default=(
            "On success, the artifact shows through the core PlotPreviewer in the preview "
            "panel. To change the figure, edit the render script and re-run. To keep the "
            "artifact, explicitly export/save it — the preview cache is not a result path."
        ),
        description="Suggested next action.",
    )
    """Plain-language hint describing the suggested next action."""


__all__ = [
    "ABSOLUTE_MAX_FILES",
    "ABSOLUTE_MAX_INPUT_BYTES",
    "ABSOLUTE_MAX_OUTPUT_BYTES",
    "ABSOLUTE_MAX_TIMEOUT_SECONDS",
    "DEFAULT_MAX_FILES",
    "DEFAULT_MAX_INPUT_BYTES",
    "DEFAULT_MAX_OUTPUT_BYTES",
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
    "PlotPreviewTarget",
    "PlotRunResult",
    "PlotStatus",
    "PlotTarget",
    "ReadPlotSourceResult",
    "ScaffoldPlotResult",
    "ValidatePlotResult",
]
