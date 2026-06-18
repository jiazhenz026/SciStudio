"""Plot scaffolding — templates + safe file creation (ADR-048 SPEC 2 FR-007..FR-013).

``scaffold_plot`` creates exactly ``plots/<plot_id>/plot.yaml`` plus one
language-specific render script (FR-007). It refuses to overwrite unless
``overwrite=true`` (FR-008) and rejects plot IDs that would escape the project
root or collide with reserved names (FR-004, edge cases).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from scistudio.ai.agent.mcp.tools_plot.models import (
    PlotLanguage,
    PlotManifest,
    PlotManifestScript,
    PlotManifestTarget,
)
from scistudio.ai.agent.mcp.tools_plot.targets import PlotTarget

# A plot id is a single safe directory segment: letters, digits, dash,
# underscore. No dots (blocks ``..`` traversal and hidden dirs), no slashes.
_PLOT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_RESERVED_IDS = frozenset({"con", "prn", "aux", "nul", "current", "."})

_PYTHON_TEMPLATE = '''"""Render script created by SciStudio.

This is a PREVIEW-ONLY plot job. It is NOT a workflow block and never becomes a
DAG node.

What ``collection`` means:
  ``collection`` is the read-only data passed from the workflow output this plot
  is bound to. If the block output is one table, the collection contains one
  table-like item. If the block output is a collection of five arrays, it
  contains five array items. Treat it as input data, not as workflow state.

What ``context`` means:
  ``context`` is the small plot-runtime helper object SciStudio gives this
  script. It loads bounded input data, exposes matplotlib as ``context.plt``,
  and saves the final artifact. It is not the workflow engine context and it
  should not mutate blocks, nodes, files, or lineage records.
"""

from __future__ import annotations


def render(collection, context):
    """Draw a figure from ``collection`` and return the saved artifact path.

    Available context helpers:
      * context.to_dataframe(collection, max_rows=...) -> pandas.DataFrame
      * context.items(collection, max_items=...)        -> bounded iterator
      * context.plt                                      -> matplotlib.pyplot
      * context.save_figure(fig, "figure.svg")           -> save PNG/JPEG/SVG/PDF

    Minimal examples you can paste over the default plot:

      # Example A: collection contains up to 5 NumPy .npy arrays; draw each
      # flattened value distribution.
      # import numpy as np
      # fig, ax = context.plt.subplots()
      # for index, item in enumerate(context.items(collection, max_items=5)):
      #     path = item.get("path")
      #     if not path:
      #         continue
      #     array = np.load(path)
      #     ax.hist(np.asarray(array).ravel(), bins=64, alpha=0.35, label="array " + str(index + 1))
      # ax.legend()
      # return context.save_figure(fig, "figure.svg")

      # Example B: collection contains one dataframe; draw a box plot from the
      # 2nd and 3rd dataframe columns.
      # df = context.to_dataframe(collection, max_rows=10000)
      # fig, ax = context.plt.subplots()
      # df.iloc[:, [1, 2]].plot(kind="box", ax=ax)
      # return context.save_figure(fig, "figure.svg")
    """
    df = context.to_dataframe(collection, max_rows={max_rows})
    fig, ax = context.plt.subplots()
    # EDIT HERE: replace with your plot. Example: ax.scatter(df["x"], df["y"], s=6)
    ax.plot(range(len(df)))
    return context.save_figure(fig, "figure.{ext}")
'''

_R_TEMPLATE = """# Render script created by SciStudio.
#
# This is a PREVIEW-ONLY plot job. It is NOT a workflow block and never becomes a
# DAG node.
#
# What `collection` means:
#   `collection` is the read-only data passed from the workflow output this plot
#   is bound to. If the block output is one table, the collection contains one
#   table-like item. If the block output is a collection of five arrays, it
#   contains five array items. In R it is a list of item references; each item
#   usually has fields such as `path`, `format`, and metadata.
#
# What `context` means:
#   `context` is the small plot-runtime helper object SciStudio gives this
#   script. It loads bounded input data and saves the final artifact. It is not
#   the workflow engine context and it should not mutate blocks, nodes, files,
#   or lineage records.
#
# Available context helpers:
#   * context$to_dataframe(collection, max_rows = ...) -> data.frame
#   * context$save_plot(plot_or_grob, "figure.pdf")    -> save PNG/JPEG/SVG/PDF
#
# Minimal examples you can paste over the default plot:
#
#   # Example A: collection contains one dataframe; draw a box plot from the
#   # 2nd and 3rd dataframe columns.
#   # df <- context$to_dataframe(collection, max_rows = 10000)
#   # value_cols <- names(df)[2:3]
#   # long <- stack(df[value_cols])
#   # p <- ggplot2::ggplot(long, ggplot2::aes(x = ind, y = values)) +
#   #   ggplot2::geom_boxplot()
#   # context$save_plot(p, "figure.pdf")
#
#   # Example B: collection contains several CSV tables; draw each first-column
#   # distribution.
#   # frames <- list()
#   # for (item in collection) {{
#   #   if (!is.null(item$path) && tools::file_ext(item$path) == "csv") {{
#   #     frames[[length(frames) + 1]] <- utils::read.csv(item$path)
#   #   }}
#   # }}
#   # values <- data.frame()
#   # for (index in seq_along(frames)) {{
#   #   values <- rbind(values, data.frame(value = frames[[index]][[1]], source = paste("table", index)))
#   # }}
#   # p <- ggplot2::ggplot(values, ggplot2::aes(x = value, fill = source)) +
#   #   ggplot2::geom_histogram(bins = 40, alpha = 0.35, position = "identity")
#   # context$save_plot(p, "figure.pdf")

render <- function(collection, context) {{
  df <- context$to_dataframe(collection, max_rows = {max_rows})
  p <- ggplot2::ggplot(df, ggplot2::aes(x = seq_along(df[[1]]), y = df[[1]])) +
    ggplot2::geom_line()
  context$save_plot(p, "figure.{ext}")
}}
"""

_SCRIPT_FILENAME: dict[PlotLanguage, str] = {"python": "render.py", "r": "render.R"}


class PlotScaffoldError(ValueError):
    """Raised for invalid plot ids or overwrite collisions."""


def validate_plot_id(plot_id: str) -> str:
    """Validate a plot id is a single safe path segment (FR-004)."""
    if not plot_id or not _PLOT_ID_RE.match(plot_id):
        raise PlotScaffoldError(
            f"invalid plot_id {plot_id!r}: must match {_PLOT_ID_RE.pattern} "
            "(letters/digits/dash/underscore, no dots or slashes)."
        )
    if plot_id.lower() in _RESERVED_IDS:
        raise PlotScaffoldError(f"plot_id {plot_id!r} is reserved.")
    return plot_id


def plot_dir_for(root: Path, plot_id: str) -> Path:
    """Return the confined ``<root>/plots/<plot_id>`` directory (FR-004)."""
    validate_plot_id(plot_id)
    plots_root = (root / "plots").resolve()
    candidate = (plots_root / plot_id).resolve()
    try:
        candidate.relative_to(plots_root)
    except ValueError as exc:  # pragma: no cover - regex already blocks this
        raise PlotScaffoldError(f"plot_id {plot_id!r} escapes the plots/ directory.") from exc
    return candidate


def _default_format(language: PlotLanguage) -> str:
    # SVG is the spec's preferred default (FR-018 / plot.yaml example).
    return "svg"


def build_manifest(plot_id: str, target: PlotTarget, language: PlotLanguage, title: str | None) -> PlotManifest:
    """Build the :class:`PlotManifest` for a new plot (FR-010, FR-011)."""
    return PlotManifest(
        schema_version=1,
        id=plot_id,
        title=title or plot_id.replace("_", " ").replace("-", " ").title(),
        target=PlotManifestTarget(
            workflow_path=target.workflow_path,
            workflow_id=target.workflow_id,
            node_id=target.node_id,
            output_port=target.output_port,
            display_label=target.node_label,
        ),
        script=PlotManifestScript(language=language, path=_SCRIPT_FILENAME[language], entrypoint="render"),
    )


def render_manifest_yaml(manifest: PlotManifest) -> str:
    """Serialise a manifest to deterministic YAML (FR-010)."""
    data = manifest.model_dump(mode="json")
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False)


def render_script_template(language: PlotLanguage, max_rows: int) -> str:
    """Return the language-specific render-script template body (FR-012/FR-013)."""
    ext = _default_format(language)
    if language == "python":
        return _PYTHON_TEMPLATE.format(max_rows=max_rows, ext=ext)
    if language == "r":
        return _R_TEMPLATE.format(max_rows=max_rows, ext="pdf")
    raise PlotScaffoldError(f"unsupported language: {language!r}")  # pragma: no cover


def scaffold_plot_files(
    root: Path,
    plot_id: str,
    target: PlotTarget,
    language: PlotLanguage,
    title: str | None,
    overwrite: bool,
) -> tuple[Path, Path, int]:
    """Create ``plots/<plot_id>/plot.yaml`` + render script (FR-007, FR-008).

    Returns ``(manifest_path, script_path, bytes_written)``. Raises
    :class:`PlotScaffoldError` (mapped to ``FileExistsError`` by the tool) when
    the directory exists and ``overwrite`` is false.
    """
    plot_dir = plot_dir_for(root, plot_id)
    manifest = build_manifest(plot_id, target, language, title)
    manifest_path = plot_dir / "plot.yaml"
    script_path = plot_dir / _SCRIPT_FILENAME[language]

    if plot_dir.exists() and not overwrite:
        raise FileExistsError(f"plot {plot_id!r} already exists at {plot_dir}. Pass overwrite=true to replace it.")

    plot_dir.mkdir(parents=True, exist_ok=True)
    manifest_text = render_manifest_yaml(manifest)
    script_text = render_script_template(language, manifest.limits.max_rows)
    manifest_path.write_text(manifest_text, encoding="utf-8")
    script_path.write_text(script_text, encoding="utf-8")
    bytes_written = len(manifest_text.encode("utf-8")) + len(script_text.encode("utf-8"))
    return manifest_path, script_path, bytes_written


__all__ = [
    "PlotScaffoldError",
    "build_manifest",
    "plot_dir_for",
    "render_manifest_yaml",
    "render_script_template",
    "scaffold_plot_files",
    "validate_plot_id",
]
