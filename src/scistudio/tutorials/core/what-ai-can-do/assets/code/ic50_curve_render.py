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
"""The fitted dose-response curve drawn in core tutorial 3.

Bound to the fit's ``wells`` output — every well that reached the fit, with the
dose it was given and the fitted value at that dose. Well level rather than
per-dose means on purpose: a mean is what gets quoted, and the eight readings
behind it are what tell you whether to believe the quote.
"""


def render(collection):
    """Box-plot each dose group against the fitted curve, and mark the IC50.

    One box per concentration, so the reader sees the replicate spread rather
    than a single point standing in for eight wells — a dose whose wells
    disagree looks different from one whose wells agree, and on a plot of means
    those two look identical.

    The curve is drawn from the fit's own ``fitted_viability_pct`` column
    rather than re-derived here, so the line and the IC50 marked on it come
    from the same fit the block reported. A picture that recomputed its subject
    could disagree with it.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    df = collection.items.open_one()
    ic50 = float(df["ic50_um"].iloc[0])
    hill = float(df["hill_slope"].iloc[0])

    doses = np.array(sorted(set(df["concentration_um"].astype(float))))
    by_dose = [df.loc[df["concentration_um"].astype(float) == d, "viability_pct"].to_numpy(float) for d in doses]
    fitted = [float(df.loc[df["concentration_um"].astype(float) == d, "fitted_viability_pct"].iloc[0]) for d in doses]

    # Proportioned for the harness's 20pt body and 24pt titles, not for
    # matplotlib's defaults -- see plate_raw/render.py.
    fig, ax = plt.subplots(figsize=(12.0, 7.4))
    ax.set_xscale("log")

    # Boxes are drawn in data coordinates on a log axis, so each one is given a
    # width proportional to its own position: a fixed width would be invisible
    # at the low doses and enormous at the high ones.
    widths = [d * 0.45 for d in doses]
    boxes = ax.boxplot(
        by_dose,
        positions=doses,
        widths=widths,
        manage_ticks=False,
        patch_artist=True,
        medianprops={"color": "#1a365d", "linewidth": 2.0},
        flierprops={"marker": "o", "markersize": 4, "markerfacecolor": "#718096", "markeredgecolor": "none"},
    )
    for patch in boxes["boxes"]:
        patch.set_facecolor("#bee3f8")
        patch.set_edgecolor("#2b6cb0")

    ax.plot(doses, fitted, color="#c53030", linewidth=2.5, zorder=3, label=f"fit (Hill slope {hill:.2f})")
    ax.axvline(ic50, color="#718096", linestyle="--", linewidth=1.5)
    ax.axhline(50, color="#718096", linestyle=":", linewidth=1.2)
    ax.annotate(
        f"IC50 = {ic50:.1f} uM",
        xy=(ic50, 50),
        xytext=(10, 16),
        textcoords="offset points",
        color="#2d3748",
    )

    ax.set_xlabel("drug concentration (uM)")
    ax.set_ylabel("viability (%)")
    ax.set_title("Dose response, and the IC50 it fits")
    ax.set_ylim(-5, 115)
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, loc="lower left")
    # See plate_raw/render.py: the harness lays figures out; renders do not.
    return fig
