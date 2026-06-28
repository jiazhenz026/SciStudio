"""Curated plot examples for matplotlib, seaborn, and ggplot2.

Each example is a complete ``render`` function you can copy and adapt. They open
the bound collection into ordinary scientific objects (a DataFrame, an array) and
return a familiar matplotlib or ggplot2 plot object. ``list_examples`` returns
them, optionally filtered by language or library.
"""

from __future__ import annotations

from scistudio.plot.models import PlotExample

_MATPLOTLIB_SCATTER = '''def render(collection):
    """Scatter plot with matplotlib."""
    import matplotlib.pyplot as plt

    df = collection.items.open_one()
    fig, ax = plt.subplots()
    ax.scatter(df["x"], df["y"], s=6)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    return fig
'''

_MATPLOTLIB_HIST = '''def render(collection):
    """Histogram of one numeric column with matplotlib."""
    import matplotlib.pyplot as plt

    df = collection.items.open_one()
    fig, ax = plt.subplots()
    ax.hist(df["value"], bins=30)
    ax.set_xlabel("value")
    ax.set_ylabel("count")
    return fig
'''

_SEABORN_BOX = '''def render(collection):
    """Boxplot with seaborn."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    df = collection.items.open_one()
    fig, ax = plt.subplots()
    sns.boxplot(data=df, x="group", y="value", ax=ax)
    return fig
'''

_GGPLOT2_POINT = """render <- function(collection) {
  # ggplot2 scatter. Requires R + ggplot2 in the project environment.
  df <- collection$items$open_one()
  ggplot2::ggplot(df, ggplot2::aes(x = x, y = y)) +
    ggplot2::geom_point()
}
"""

_GGPLOT2_BAR = """render <- function(collection) {
  # ggplot2 bar chart of a categorical count.
  df <- collection$items$open_one()
  ggplot2::ggplot(df, ggplot2::aes(x = category)) +
    ggplot2::geom_bar()
}
"""


_EXAMPLES: tuple[PlotExample, ...] = (
    PlotExample(
        id="matplotlib_scatter",
        language="python",
        library="matplotlib",
        title="Scatter plot",
        description="Two-column scatter using collection.items.open_one() and matplotlib.",
        source=_MATPLOTLIB_SCATTER,
        output_formats=["svg"],
    ),
    PlotExample(
        id="matplotlib_histogram",
        language="python",
        library="matplotlib",
        title="Histogram",
        description="Single-column histogram using collection.items.open_one() and matplotlib.",
        source=_MATPLOTLIB_HIST,
        output_formats=["png"],
    ),
    PlotExample(
        id="seaborn_boxplot",
        language="python",
        library="seaborn",
        title="Boxplot",
        description="Grouped boxplot via seaborn over a matplotlib Figure.",
        source=_SEABORN_BOX,
        output_formats=["svg"],
    ),
    PlotExample(
        id="ggplot2_scatter",
        language="r",
        library="ggplot2",
        title="ggplot2 scatter",
        description="Scatter via collection$items$open_one() and ggplot2.",
        source=_GGPLOT2_POINT,
        output_formats=["pdf"],
    ),
    PlotExample(
        id="ggplot2_bar",
        language="r",
        library="ggplot2",
        title="ggplot2 bar chart",
        description="Categorical bar chart via collection$items$open_one() and ggplot2.",
        source=_GGPLOT2_BAR,
        output_formats=["svg"],
    ),
)


def list_examples(language: str | None = None, library: str | None = None) -> list[PlotExample]:
    """Return the curated render-script examples, optionally filtered.

    Use this to fetch starting points you can paste into a plot's render script.
    With no arguments it returns every example; pass ``language`` and/or
    ``library`` to narrow the list. Matching is case-insensitive.

    Args:
        language: Keep only examples in this language (``"python"`` or ``"r"``).
        library: Keep only examples using this plotting library
            (``"matplotlib"``, ``"seaborn"``, or ``"ggplot2"``).

    Returns:
        The matching :class:`~scistudio.plot.models.PlotExample` entries, in
        curated order.

    Example:
        >>> from scistudio.plot import list_examples
        >>> [e.id for e in list_examples(library="ggplot2")]
        ['ggplot2_scatter', 'ggplot2_bar']
    """
    out = list(_EXAMPLES)
    if language:
        lang = language.lower()
        out = [e for e in out if e.language == lang]
    if library:
        lib = library.lower()
        out = [e for e in out if e.library.lower() == lib]
    return out


__all__ = ["list_examples"]
