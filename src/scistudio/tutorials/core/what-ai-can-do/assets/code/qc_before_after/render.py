# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/tutorials/core/']`, which the
# CI-side run honours but the pre-commit hook (explicit file list) does not:
# this file ships as project *data* a reader edits, and its unannotated
# `def render(collection):` is deliberate — the first Python a new user meets
# should look like the Python they write.
"""The QC before/after picture the scripted agent writes in core tutorial 4.

A plot card runs this file and shows whatever ``render`` returns. The bound
output is the QC filter's annotated table, which still holds every sample —
that is what lets one figure show the plate before and after the cut.
"""


def render(collection):
    """Draw every sample's robust z-score, kept and flagged told apart.

    The y-axis is the score the QC block filtered on, so the picture *is* the
    decision: everything between the threshold lines survived, everything
    outside was flagged. The two extreme samples are clipped to the plot edge
    and annotated with their true scores, because a 9840 in a plate of 1200s
    would otherwise flatten everyone else onto one pixel.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    df = collection.items.open_one()
    z = df["qc_robust_z"].to_numpy(dtype=float)
    keep = df["qc_keep"].to_numpy(dtype=bool)
    x = np.arange(len(df))

    clip = 4.0
    clipped = np.clip(z, -clip, clip)

    fig, ax = plt.subplots(figsize=(8.0, 4.4))
    ax.scatter(x[keep], clipped[keep], s=26, color="#2d7891", label="kept")
    ax.scatter(x[~keep], clipped[~keep], s=34, color="#c2410c", marker="x", label="flagged")

    for bound, style in ((2.0, ":"), (3.0, "--")):
        for sign in (1, -1):
            ax.axhline(sign * bound, color="#78716c", linewidth=0.8, linestyle=style)
        ax.text(len(df) - 0.5, bound + 0.08, f"{bound:.0f} sigma", color="#78716c", ha="right", fontsize=8)

    # Samples whose true score is off the chart get their real value written
    # at the clip edge, so the picture never hides how far out they were.
    for idx in np.flatnonzero(np.isfinite(z) & (np.abs(z) > clip)):
        ax.annotate(
            f"z = {z[idx]:+.0f}",
            (x[idx], clipped[idx]),
            textcoords="offset points",
            xytext=(6, -4),
            fontsize=8,
            color="#c2410c",
        )

    n_kept = int(keep.sum())
    ax.set_title(f"QC: {n_kept} of {len(df)} samples kept")
    ax.set_xlabel("sample")
    ax.set_ylabel("robust z (fluorescence_au)")
    missing = int(np.isnan(z).sum())
    if missing:
        ax.text(
            0.01,
            0.02,
            f"{missing} samples had no fluorescence value and are not drawn",
            transform=ax.transAxes,
            fontsize=8,
            color="#78716c",
        )
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    return fig
