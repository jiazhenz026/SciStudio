# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/tutorials/core/']`, which the
# CI-side run honors but the pre-commit hook (explicit file list) does not
# (#2115): this file ships as project *data* a reader edits, and its
# unannotated `def render(collection):` is deliberate — a plot script should
# look like the Python a reader would write.
"""The cell-size histogram core tutorial 2 writes at the end of the level.

Every slide's area table arrives in one collection, and the histogram pools
them: the question the picture answers is "how big are the cells in this
experiment", not "how big are the cells in slide one". Each table is one
micrograph, so opening them all and concatenating the ``area_px`` column is
the whole of it.

Areas are in pixels because that is what the segmentation measured. A real
experiment would carry the micrograph's pixel size and plot µm², which is a
change to the label on one axis and a multiplication — left out here so the
level ends on the type system rather than on unit conversion.
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
