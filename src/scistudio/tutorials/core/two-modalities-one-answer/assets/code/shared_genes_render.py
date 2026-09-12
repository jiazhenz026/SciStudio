# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/tutorials/core/']`, which the
# CI-side run honors but the pre-commit hook (explicit file list) does not
# (#2115): this file ships as project *data* a reader edits, and its
# unannotated `def render(collection):` is deliberate — a plot script should
# look like the Python a reader would write.
"""The genes every tumor agrees on, one bar per tumor.

One tumor can differ from the next for reasons that have nothing to do with
cancer. A gene that is significantly higher (or lower) in the region in *every*
tumor, and in the same direction, is what a conclusion can stand on. This plot
keeps only those, and shows each tumor's fold change side by side so the
agreement is visible rather than asserted.
"""

MAX_Q = 0.05

#: How many shared genes to show on each side, the largest average change first.
PER_SIDE = 8

COLORS = ("#4c72b0", "#dd8452", "#55a868", "#c44e52")


def render(collection):
    """Draw the shared genes as grouped horizontal bars."""
    import matplotlib.pyplot as plt
    import numpy as np

    tables = [table.set_index("gene") for table in collection.items.open()]
    tumors = [table["tumor"].iloc[0] for table in tables]
    region = tables[0]["region"].iloc[0]
    against = tables[0]["against"].iloc[0]
    other = "the rest" if against == "Rest of the tissue" else against.lower()

    tested_everywhere = set.intersection(*(set(table.index) for table in tables))
    folds = {gene: [table.at[gene, "log2_fold_change"] for table in tables] for gene in tested_everywhere}
    certain = {gene for gene in tested_everywhere if all(table.at[gene, "q_value"] < MAX_Q for table in tables)}
    higher = sorted((g for g in certain if all(f > 0 for f in folds[g])), key=lambda g: -np.mean(folds[g]))
    lower = sorted((g for g in certain if all(f < 0 for f in folds[g])), key=lambda g: np.mean(folds[g]))
    genes = higher[:PER_SIDE] + lower[:PER_SIDE][::-1]

    fig, ax = plt.subplots(figsize=(7.2, 0.42 * max(len(genes), 4) + 1.4))
    rows = np.arange(len(genes))
    width = 0.8 / len(tables)
    for index, tumor in enumerate(tumors):
        offsets = rows - 0.4 + width * (index + 0.5)
        ax.barh(offsets, [folds[g][index] for g in genes], height=width, color=COLORS[index % len(COLORS)], label=tumor)

    ax.set_yticks(rows)
    ax.set_yticklabels(genes)
    ax.invert_yaxis()
    ax.axvline(0, color="#1c211b", linewidth=0.8)
    ax.set_xlabel(f"log2 fold change, {region.lower()} vs {other}")
    ax.set_title(f"Genes every tumor agrees on (q < {MAX_Q} in each)")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    return fig
