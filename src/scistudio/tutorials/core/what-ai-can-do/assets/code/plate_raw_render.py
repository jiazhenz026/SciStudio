# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/tutorials/core/']`, which the
# CI-side run honours but the pre-commit hook (explicit file list) does not:
# this file ships as project *data* a reader edits, and its unannotated
# `def render(collection):` is deliberate — the first Python a new user meets
# should look like the Python they write.
#
# Flat here, `plots/<id>/render.py` in the reader's project. Two plots in one
# tutorial would otherwise ship two `render.py` files, which collide as
# duplicate top-level modules the moment a tool is handed both by name — the
# project's mypy config excludes this tree, but a diff-scoped run that names
# files applies no exclude. Core tutorial 1 names its render asset flat for the
# same reason; only the write destination has to match the product's
# convention, and it does.
"""The plate as it came off the reader, drawn in core tutorial 3.

A plot card runs this file and shows whatever ``render`` returns. This one is
bound to the bare load block, so it draws the data before anything has been
done to it — which is the whole reason the reader asked for it.

The x axis is the **group label**, because that is all the table knows. What
each group was dosed with is in the file's name and nowhere else, and turning
that into an axis is the job of another block downstream.
"""


def render(collection):
    """Draw the 96-well plate, one square per well, coloured by viability.

    The plate's own geometry rather than a scatter: the reader ran this on a
    physical plate, and a bad well is something that happened in a *place*. The
    two wells that never reported are visible only here, as holes, and the
    blank that reads like a live well is obvious the moment the last column is
    next to the first.

    Groups run along the columns, so each column is one condition and the eight
    wells down it are its replicates. Read left to right and the plate should
    fade from dead to healthy, ending in the two control columns.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    df = collection.items.open_one()

    rows = "ABCDEFGH"
    grid = np.full((len(rows), 12), np.nan)
    # Each column carries one group; collected here rather than assumed, so the
    # axis labels come from the plate instead of from a guess about its layout.
    group_of_column = {}
    for well, group, value in zip(df["well"], df["group"], df["viability_pct"], strict=True):
        column = int(well[1:]) - 1
        grid[rows.index(well[0])][column] = value
        group_of_column[column] = group

    # Sized and un-locked for the plot harness's style rather than
    # matplotlib's defaults: it renders at 20pt body and 24pt titles so the
    # previewer stays legible, and `imshow` otherwise pins the axes to a
    # square-cell aspect that constrained layout cannot shrink -- the
    # decorations then spill off the canvas. `aspect='auto'` lets the cells
    # stretch to the frame; the figure is proportioned 12:8 so they stay near
    # enough square.
    fig, ax = plt.subplots(figsize=(13.2, 8.4))
    # `bad` paints the wells that never reported: NaN is not a low reading, and
    # colouring it like one would hide them.
    palette = plt.get_cmap("viridis").with_extremes(bad="#f0f0f0")
    image = ax.imshow(grid, cmap=palette, vmin=0, vmax=100, aspect="auto")

    ax.set_xticks(range(12))
    ax.set_xticklabels([group_of_column.get(column, "?") for column in range(12)])
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(list(rows))
    ax.set_xlabel("group")
    ax.set_title("Viability by well")

    # Grid lines on the cell boundaries, so the squares read as wells.
    ax.set_xticks(np.arange(-0.5, 12, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(rows), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.5)
    ax.tick_params(which="minor", length=0)

    fig.colorbar(image, ax=ax, label="viability (%)", shrink=0.85)
    # No tight_layout here. The plot harness turns on constrained layout for
    # every figure (`figure.constrained_layout.use`), and switching engines
    # afterwards is refused outright once a colorbar exists — matplotlib says
    # so and leaves the figure alone. Constrained layout already does this
    # job, and does it better with a colorbar in the frame.
    return fig
