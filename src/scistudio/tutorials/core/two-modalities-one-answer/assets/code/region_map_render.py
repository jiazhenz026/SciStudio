# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/tutorials/core/']`, which the
# CI-side run honours but the pre-commit hook (explicit file list) does not
# (#2115): this file ships as project *data* a reader edits, and its
# unannotated `def render(collection):` is deliberate — a plot script should
# look like the Python a reader would write.
"""Draw the clustered regions back onto the slides they came from.

Core tutorial 3 writes this file into the plot the reader created. It draws
nothing the joint block did not already decide: the cluster label is read
straight out of the table. A plot card is preview-only — its picture goes to a
cache the next run overwrites, and version control never sees it — so the
answer has to arrive here already computed.

One panel per section, region centroids in image coordinates, colour by
cluster. Read it the way you would read the slide: if the clustering found
tissue programmes rather than sequencing depth, each section carries a
comparable spread of every colour, because the same kinds of tissue recur
section to section. A section that turns one colour is the picture of a
clustering that grouped by batch.
"""


def render(collection):
    """One panel per section: region centroids, coloured by cluster."""
    import matplotlib.pyplot as plt

    frame = collection.items.open_one()
    sections = sorted(frame["section"].unique())
    clusters = sorted(int(value) for value in frame["cluster"].dropna().unique())
    palette = ["#2d7891", "#c2410c", "#6d8f3f", "#7c3aed", "#b45309", "#0f766e", "#9d174d", "#3f3f46"]

    fig, axes = plt.subplots(1, len(sections), figsize=(3.6 * len(sections), 4.0), squeeze=False)
    for axis, section in zip(axes[0], sections, strict=True):
        panel = frame[frame["section"] == section]
        for cluster in clusters:
            members = panel[panel["cluster"] == cluster]
            axis.scatter(
                members["centroid_x"],
                members["centroid_y"],
                s=members["n_positions"] * 9,
                color=palette[cluster % len(palette)],
                edgecolor="white",
                linewidth=0.8,
                label=f"cluster {cluster}" if section == sections[0] else None,
            )
        unassigned = panel[panel["cluster"].isna()]
        if len(unassigned):
            axis.scatter(
                unassigned["centroid_x"],
                unassigned["centroid_y"],
                s=30,
                color="#d6d3d1",
                marker="x",
                label="too few positions" if section == sections[0] else None,
            )
        axis.set_title(f"{section} — {len(panel)} regions")
        axis.set_xlabel("x (pixels)")
        axis.set_xlim(0, 96)
        axis.set_ylim(96, 0)  # image coordinates: y grows downwards
        axis.set_aspect("equal")
    axes[0][0].set_ylabel("y (pixels)")

    counts = " / ".join(str(int((frame["cluster"] == cluster).sum())) for cluster in clusters)
    fig.suptitle(f"Region clusters across {len(sections)} sections — sizes {counts}")
    handles, labels = axes[0][0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="lower center", ncol=len(labels), frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    return fig
