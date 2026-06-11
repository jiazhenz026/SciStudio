"""Curated plot examples for matplotlib / seaborn / ggplot2 (ADR-048 SPEC 2 FR-019).

Each example is a complete ``render`` function an agent can adapt. The Python
examples target the ``context.plt`` / ``context.save_figure`` helpers; the R
example targets ``context$to_dataframe`` / ``context$save_plot`` (FR-014, FR-015,
FR-018).
"""

from __future__ import annotations

from scistudio.ai.agent.mcp.tools_plot.models import PlotExample

_MATPLOTLIB_SCATTER = '''def render(collection, context):
    """Scatter plot with matplotlib (FR-014)."""
    df = context.to_dataframe(collection, max_rows=10000)
    fig, ax = context.plt.subplots()
    ax.scatter(df["x"], df["y"], s=6)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    return context.save_figure(fig, "figure.svg")
'''

_MATPLOTLIB_HIST = '''def render(collection, context):
    """Histogram of one numeric column with matplotlib."""
    df = context.to_dataframe(collection, max_rows=10000)
    fig, ax = context.plt.subplots()
    ax.hist(df["value"], bins=30)
    ax.set_xlabel("value")
    ax.set_ylabel("count")
    return context.save_figure(fig, "figure.png")
'''

_SEABORN_BOX = '''def render(collection, context):
    """Boxplot with seaborn (uses the project environment's seaborn if present)."""
    import seaborn as sns

    df = context.to_dataframe(collection, max_rows=10000)
    fig, ax = context.plt.subplots()
    sns.boxplot(data=df, x="group", y="value", ax=ax)
    return context.save_figure(fig, "figure.svg")
'''

_GGPLOT2_POINT = """render <- function(collection, context) {
  # ggplot2 scatter (FR-013, FR-015). Requires R + ggplot2 in the project env.
  df <- context$to_dataframe(collection, max_rows = 10000)
  p <- ggplot2::ggplot(df, ggplot2::aes(x = x, y = y)) +
    ggplot2::geom_point()
  context$save_plot(p, "figure.pdf")
}
"""

_GGPLOT2_BAR = """render <- function(collection, context) {
  # ggplot2 bar chart of a categorical count.
  df <- context$to_dataframe(collection, max_rows = 10000)
  p <- ggplot2::ggplot(df, ggplot2::aes(x = category)) +
    ggplot2::geom_bar()
  context$save_plot(p, "figure.svg")
}
"""


_EXAMPLES: tuple[PlotExample, ...] = (
    PlotExample(
        id="matplotlib_scatter",
        language="python",
        library="matplotlib",
        title="Scatter plot",
        description="Two-column scatter using context.plt + context.save_figure → SVG.",
        source=_MATPLOTLIB_SCATTER,
        output_formats=["svg"],
    ),
    PlotExample(
        id="matplotlib_histogram",
        language="python",
        library="matplotlib",
        title="Histogram",
        description="Single-column histogram saved as PNG.",
        source=_MATPLOTLIB_HIST,
        output_formats=["png"],
    ),
    PlotExample(
        id="seaborn_boxplot",
        language="python",
        library="seaborn",
        title="Boxplot",
        description="Grouped boxplot via seaborn over a matplotlib Figure → SVG.",
        source=_SEABORN_BOX,
        output_formats=["svg"],
    ),
    PlotExample(
        id="ggplot2_scatter",
        language="r",
        library="ggplot2",
        title="ggplot2 scatter",
        description="Scatter via ggplot2 + context$save_plot → PDF.",
        source=_GGPLOT2_POINT,
        output_formats=["pdf"],
    ),
    PlotExample(
        id="ggplot2_bar",
        language="r",
        library="ggplot2",
        title="ggplot2 bar chart",
        description="Categorical bar chart via ggplot2 → SVG.",
        source=_GGPLOT2_BAR,
        output_formats=["svg"],
    ),
)


def list_examples(language: str | None = None, library: str | None = None) -> list[PlotExample]:
    """Return curated examples filtered by ``language`` and/or ``library`` (FR-019)."""
    out = list(_EXAMPLES)
    if language:
        lang = language.lower()
        out = [e for e in out if e.language == lang]
    if library:
        lib = library.lower()
        out = [e for e in out if e.library.lower() == lib]
    return out


__all__ = ["list_examples"]
