# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/_user_guide/']`: these files
# ship as project *data* a reader edits, and their unannotated
# `def render(collection):` is deliberate — a plot script should look like the
# Python a reader would write.
"""The render script of the [plot.yaml](plot.yaml) example.

Every slide's area table arrives in one collection, and the histogram pools
them: the question the picture answers is "how big are the cells in this
experiment", not "how big are the cells in slide one". Each table is one
micrograph, so opening them all and concatenating the ``area_px`` column is
the whole of it.

The contract (see the plot page of the user guide): define exactly
``render(collection)``, import nothing from SciStudio — the collection is the
whole interface — and return a matplotlib figure, a path to an image you
wrote, or a list of either.
"""


def render(collection):
    """Pool every slide's areas into one distribution."""
    import matplotlib.pyplot as plt

    frames = collection.items.open()
    areas = [float(value) for frame in frames for value in frame["area_px"]]

    figure, axis = plt.subplots(figsize=(6.4, 4.0))
    axis.hist(areas, bins=12, color="#2d7891", edgecolor="white", linewidth=0.8)
    axis.set_xlabel("Cell area (pixels)")
    axis.set_ylabel("Cells")
    axis.set_title(f"Cell size distribution — {len(areas)} cells across {len(frames)} slides")
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    figure.tight_layout()
    return figure
