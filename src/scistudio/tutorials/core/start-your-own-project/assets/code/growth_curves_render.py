# mypy: ignore-errors
# ^ pyproject.toml excludes /tutorials/core/ from type checking on purpose:
#   this is a teaching file a bench scientist reads, so ``render`` carries no
#   annotations. The pre-commit hook passes files to mypy explicitly, which
#   skips that exclude, so the same decision is restated here per-file.
"""The plot script the Learning Center writes into the tutorial project.

A plot card runs this file and shows whatever ``render`` returns. In this
level it is bound to the Load block's table output — the raw measurements —
because the lesson of the step is that a plot can read any block's output, not
only the last one's.
"""


def render(collection):
    """Plot each culture's OD600 growth curve over the measured days.

    A plot script receives the collection bound to one block output port and
    returns a matplotlib figure. The figure lands in the preview cache, not in
    the project — which is exactly what the step after this one is about.
    """
    import matplotlib.pyplot as plt

    df = collection.items.open_one()
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for sample, group in df.groupby("sample", sort=True):
        ordered = group.sort_values("day")
        ax.plot(
            ordered["day"],
            ordered["od600"],
            marker="o",
            linewidth=1.6,
            label=str(sample),
        )
    ax.set_xlabel("Day")
    ax.set_ylabel("OD600")
    ax.set_title("Growth curves")
    ax.set_xticks(sorted(df["day"].unique()))
    ax.legend(title="Culture")
    fig.tight_layout()
    return fig
