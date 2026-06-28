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

from scistudio.plot.models import (
    PlotLanguage,
    PlotManifest,
    PlotManifestScript,
    PlotManifestTarget,
)
from scistudio.plot.targets import PlotTarget

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
"""

from __future__ import annotations


def render(collection):
    """Draw a figure from ``collection`` and return a matplotlib Figure.

    Available collection helpers:
      * collection.types                  -> tuple[str, ...]
      * collection.items                  -> sequence of item wrappers
      * len(collection.items)             -> number of items
      * collection.items.open()           -> list of native values
      * collection.items.open(max_items=n)-> list of at most n native values
      * collection.items.open_one()       -> first native value
      * collection.items[index].type      -> normalized core base type
      * collection.items[index].metadata  -> read-only non-storage metadata
      * collection.items[index].open()    -> one native value
        (a Series-backed item such as a spectrum opens to its full
        {index, value} table, e.g. a DataFrame with lambda + intensity columns)

    Figure size / aspect ratio:
      The default figure is 6.4 x 4.8 inches (4:3). To use a different size or
      ratio, create the figure with an explicit figsize, e.g.
      ``fig, ax = plt.subplots(figsize=(12, 5))``; the saved output uses it.

    Minimal examples you can paste over the default plot:

      # Example A: collection contains up to 5 arrays; draw each flattened
      # value distribution.
      # import numpy as np
      # import matplotlib.pyplot as plt
      # fig, ax = plt.subplots()
      # for index, array in enumerate(collection.items.open(max_items=5)):
      #     ax.hist(np.asarray(array).ravel(), bins=64, alpha=0.35, label="array " + str(index + 1))
      # ax.legend()
      # return fig

      # Example B: collection contains one dataframe; draw a box plot from the
      # 2nd and 3rd dataframe columns.
      # import matplotlib.pyplot as plt
      # df = collection.items.open_one()
      # fig, ax = plt.subplots()
      # df.iloc[:, [1, 2]].plot(kind="box", ax=ax)
      # return fig
    """
    import numpy as np
    import matplotlib.pyplot as plt

    data = collection.items.open_one()
    fig, ax = plt.subplots()

    if hasattr(data, "select_dtypes"):
        numeric = data.select_dtypes(include="number")
        if len(numeric.columns) >= 2:
            ax.scatter(numeric.iloc[:, 0], numeric.iloc[:, 1], s=6)
            ax.set_xlabel(str(numeric.columns[0]))
            ax.set_ylabel(str(numeric.columns[1]))
        elif len(numeric.columns) == 1:
            ax.plot(numeric.iloc[:, 0].to_numpy())
            ax.set_ylabel(str(numeric.columns[0]))
        else:
            ax.text(0.5, 0.5, "No numeric columns", ha="center", va="center")
    else:
        array = np.asarray(data)
        if array.ndim >= 2:
            ax.imshow(array.squeeze())
        else:
            ax.plot(array.ravel())
    return fig
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
#   contains five array items. Treat it as input data, not as workflow state.
#
# Available collection helpers:
#   * collection$types                      -> character vector
#   * collection$items                      -> sequence-like item wrapper
#   * length(collection$items)              -> number of items
#   * collection$items$open()               -> list of native values
#   * collection$items$open(max_items = n)  -> list of at most n native values
#   * collection$items$open_one()           -> first native value
#   * collection$items[[index]]$type        -> normalized core base type
#   * collection$items[[index]]$metadata    -> non-storage metadata
#   * collection$items[[index]]$open()      -> one native value
#     (a Series-backed item such as a spectrum opens to its full
#     {index, value} table, e.g. a data.frame with lambda + intensity columns)
#
# Figure size / aspect ratio:
#   The plot defaults to 6.4 x 4.8 inches (4:3), matching the Python renderer.
#   To use a different size or ratio, call figure_size(width, height) in inches
#   at the TOP LEVEL of this script (outside render), e.g.:
#       figure_size(12, 5)
#   Top-level placement is required: base-graphics devices open before render()
#   runs. A top-level call is honored by both base graphics and ggplot2 output.
#
# Minimal examples you can paste over the default plot:
#
#   # Example A: collection contains one dataframe; draw a box plot from the
#   # 2nd and 3rd dataframe columns.
#   # df <- collection$items$open_one()
#   # value_cols <- names(df)[2:3]
#   # long <- stack(df[value_cols])
#   # p <- ggplot2::ggplot(long, ggplot2::aes(x = ind, y = values)) +
#   #   ggplot2::geom_boxplot()
#   # p
#
#   # Example B: collection contains several tables; draw each first-column
#   # distribution with ggplot2.
#   # frames <- collection$items$open(max_items = 5)
#   # values <- data.frame()
#   # for (index in seq_along(frames)) {
#   #   values <- rbind(values, data.frame(value = frames[[index]][[1]], source = paste("table", index)))
#   # }
#   # p <- ggplot2::ggplot(values, ggplot2::aes(x = value, fill = source)) +
#   #   ggplot2::geom_histogram(bins = 40, alpha = 0.35, position = "identity")
#   # p

render <- function(collection) {
  data <- collection$items$open_one()
  if (is.data.frame(data)) {
    numeric_cols <- names(data)[vapply(data, is.numeric, logical(1))]
    if (length(numeric_cols) >= 2) {
      plot(data[[numeric_cols[[1]]]], data[[numeric_cols[[2]]]], xlab = numeric_cols[[1]], ylab = numeric_cols[[2]])
    } else if (length(numeric_cols) == 1) {
      plot(data[[numeric_cols[[1]]]], type = "l", ylab = numeric_cols[[1]])
    } else {
      plot.new()
      text(0.5, 0.5, "No numeric columns")
    }
  } else {
    plot(as.vector(data), type = "l")
  }
}
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


def render_script_template(language: PlotLanguage) -> str:
    """Return the language-specific render-script template body (FR-012/FR-013)."""
    if language == "python":
        return _PYTHON_TEMPLATE
    if language == "r":
        return _R_TEMPLATE
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
    script_text = render_script_template(language)
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
