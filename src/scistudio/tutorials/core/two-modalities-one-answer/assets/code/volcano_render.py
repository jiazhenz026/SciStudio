# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/tutorials/core/']`, which the
# CI-side run honors but the pre-commit hook (explicit file list) does not
# (#2115): this file ships as project *data* a reader edits, and its
# unannotated `def render(collection):` is deliberate — a plot script should
# look like the Python a reader would write.
"""A volcano plot per tumor: how different each gene is, and how sure.

Each dot is one gene. Left and right is the fold change — right is higher in
the region than in the rest of the tissue. Up is how sure the difference is —
the higher, the smaller its q value. The genes worth reading are the ones far
out in the two upper corners.
"""

#: Where a gene counts as clearly different: at least twice as high or half as
#: high, at a false discovery rate of 5%.
MIN_FOLD_CHANGE = 1.0
MAX_Q = 0.05

#: How many of the most certain genes on each side get their names written.
LABELED_PER_SIDE = 5


def render(collection):
    """Draw one volcano per tumor, side by side."""
    import matplotlib.pyplot as plt
    import numpy as np

    tables = collection.items.open()
    fig, axes = plt.subplots(1, len(tables), figsize=(5.4 * len(tables), 4.8), squeeze=False)

    for ax, table in zip(axes[0], tables, strict=True):
        fold = table["log2_fold_change"].to_numpy()
        # A q value of exactly zero would sit at infinity; pin it to the smallest
        # number a float holds instead.
        height = -np.log10(np.clip(table["q_value"].to_numpy(), 1e-300, 1.0))
        higher = (height > -np.log10(MAX_Q)) & (fold >= MIN_FOLD_CHANGE)
        lower = (height > -np.log10(MAX_Q)) & (fold <= -MIN_FOLD_CHANGE)
        neither = ~(higher | lower)

        region = table["region"].iloc[0]
        against = table["against"].iloc[0]
        other = "the rest" if against == "Rest of the tissue" else against.lower()
        ax.scatter(fold[neither], height[neither], s=10, color="#c4c4c4")
        ax.scatter(fold[higher], height[higher], s=16, color="#E41A1C", label=f"higher in {region.lower()}")
        ax.scatter(fold[lower], height[lower], s=16, color="#377EB8", label="lower")

        for side, direction in ((higher, 1), (lower, -1)):
            picked = np.flatnonzero(side)
            for rank, index in enumerate(picked[np.argsort(-height[picked])][:LABELED_PER_SIDE]):
                # The most certain genes crowd the same corner, so each name is
                # pushed a little further out than the one before it.
                ax.annotate(
                    table["gene"].iloc[index],
                    (fold[index], height[index]),
                    xytext=(direction * (6 + 4 * (rank % 2)), -4 - 9 * rank),
                    textcoords="offset points",
                    ha="left" if direction > 0 else "right",
                    fontsize=8,
                    arrowprops={"arrowstyle": "-", "color": "#78716c", "linewidth": 0.5},
                )

        ax.axhline(-np.log10(MAX_Q), color="#78716c", linewidth=0.8, linestyle="--")
        for edge in (-MIN_FOLD_CHANGE, MIN_FOLD_CHANGE):
            ax.axvline(edge, color="#78716c", linewidth=0.8, linestyle="--")
        ax.set_title(f"{table['tumor'].iloc[0]}: {region} vs {other}")
        ax.set_xlabel("log2 fold change")
        ax.set_ylabel("-log10 q")
        ax.legend(frameon=False, fontsize=8, loc="best")

    fig.tight_layout()
    return fig
