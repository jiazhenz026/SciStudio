# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/tutorials/core/']`, which the
# CI-side run honours but the pre-commit hook (explicit file list) does not
# (#2115): this file ships as project *data* the reader opens and reads.
"""The joint block: two modalities in, one labelled table out.

Core tutorial 3 writes this block into the project when the reader presses the
button. It is the block the whole level exists for, and it is the only place
where the two branches of the canvas become one piece of science.

What it does, in order:

1. **Co-register.** Each position in the expression table carries the ``y`` and
   ``x`` it was measured at. The label map says which tissue region owns each
   pixel. Looking one up in the other is the join — and notice what is *not*
   here: no shared identifier, no key column, nothing either instrument agreed
   on in advance. Position and region meet through space alone, which is why
   this analysis cannot be done on either modality by itself.
2. **Aggregate.** Positions landing on the same region are averaged into one
   profile for that region. Positions landing on background are dropped; they
   were never on tissue.
3. **Cluster.** Every region of every section is pooled and clustered with
   k-means — written out below, twenty lines of NumPy, because a reader who
   opens this file deserves to see the algorithm rather than an import.
4. **Emit.** One row per region: where it is, how many positions it holds, its
   mean profile, and its cluster.

**Why the clustering lives here and not in the plot.** A plot card is
preview-only: its output goes to a cache, it is not recorded in the project's
history, and the next run overwrites it. Cluster assignments are a result — a
thing you would put in a paper — so they have to be computed by something the
project records. Draw the answer in a plot; do not decide it there.

**Pairing is positional, and that is a hazard.** Item *i* of ``labels`` is
analysed against item *i* of ``expression``, and nothing in this block can
check that the two are the same section — a label map is pixels; it does not
carry a section name to compare against. A wrong pairing therefore does not
fail, does not warn, and does not even look thin: every region still fills up,
because the measured positions are the same grid whichever section's map they
are looked up in. It simply answers a different question, in a table that
looks exactly as trustworthy as the right one.

That is the argument for the Pair Editor sitting upstream, on the raw items:
it is the last point in the workflow where the two streams still carry the
names their instruments gave them, so it is the only place a human can see
the mismatch at all.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import pandas as pd
import pyarrow as pa
from image import Image

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import DataFrame
from scistudio.core.types.collection import Collection

# Columns of the expression table that describe a position rather than a gene.
COORDINATE_COLUMNS = ("position_id", "section", "y", "x")

# A region needs at least this many positions on it before its mean profile is
# worth clustering. Smaller regions are reported with an empty cluster rather
# than dropped — the reader should see that they were found.
MIN_POSITIONS_PER_REGION = 4

# How many iterations Lloyd's algorithm is allowed before it is called done.
# It converges on this data in far fewer; the cap is there so a pathological
# input cannot spin.
MAX_ITERATIONS = 100


def _initial_centres(points: np.ndarray, k: int) -> np.ndarray:
    """Choose *k* starting centres, deterministically.

    Textbook k-means++ samples at random and needs a seed to be reproducible.
    This is its greedy cousin: start from the point nearest the overall mean,
    then repeatedly take the point *furthest* from everything chosen so far.
    Same intent — spread the starting centres out — with no randomness to
    record, which is what a result a reader has to trust wants.
    """
    centre = points[np.argmin(((points - points.mean(axis=0)) ** 2).sum(axis=1))]
    centres = [centre]
    while len(centres) < k:
        distances = np.min(
            np.stack([((points - chosen) ** 2).sum(axis=1) for chosen in centres]),
            axis=0,
        )
        centres.append(points[int(np.argmax(distances))])
    return np.stack(centres)


def kmeans(points: np.ndarray, k: int) -> np.ndarray:
    """Cluster *points* into *k* groups with Lloyd's algorithm.

    Args:
        points: One row per region, one column per feature.
        k: How many clusters to look for.

    Returns:
        One integer cluster index per row.
    """
    if len(points) <= k:
        return np.arange(len(points))
    centres = _initial_centres(points, k)
    assignment = np.full(len(points), -1)
    for _ in range(MAX_ITERATIONS):
        distances = np.stack([((points - centre) ** 2).sum(axis=1) for centre in centres], axis=1)
        updated = distances.argmin(axis=1)
        if np.array_equal(updated, assignment):
            break
        assignment = updated
        for index in range(k):
            members = points[assignment == index]
            if len(members):
                centres[index] = members.mean(axis=0)
    return assignment


def _order_clusters(points: np.ndarray, assignment: np.ndarray) -> np.ndarray:
    """Renumber clusters by their centre's total signal, largest first.

    Lloyd's algorithm has no opinion about which group is called 0. Without a
    rule, the same data can produce the same partition under different names on
    a different machine, and the figure's colours move for no reason.
    """
    order = sorted(
        set(assignment.tolist()),
        key=lambda index: -float(points[assignment == index].mean(axis=0).sum()),
    )
    lookup = {old: new for new, old in enumerate(order)}
    return np.array([lookup[int(value)] for value in assignment])


class JointRegionProfilesBlock(ProcessBlock):
    """Aggregate expression by imaged region, then cluster the regions."""

    name: ClassVar[str] = "Joint Region Profiles"
    type_name: ClassVar[str] = "joint_region_profiles"
    description: ClassVar[str] = "Aggregate per-position expression inside imaged regions and cluster the regions."
    algorithm: ClassVar[str] = "spatial_aggregation_kmeans"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="labels", accepted_types=[Image], description="One label map per section"),
        InputPort(name="expression", accepted_types=[DataFrame], description="One normalised count table per section"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="regions", accepted_types=[DataFrame], description="One row per region, with its cluster"),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "clusters": {
                "type": "integer",
                "minimum": 2,
                "maximum": 8,
                "default": 3,
                "title": "Clusters",
                "description": "How many groups k-means should look for across every section's regions.",
            },
        },
        "required": [],
    }

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        """Pair the two modalities positionally and produce one region table.

        ``ProcessBlock`` normally maps one function over one input Collection.
        This block overrides ``run`` instead, because its answer is not
        per-section: regions are aggregated section by section, but the
        clustering is done once over every section's regions together, so that
        cluster 1 means the same thing on every slide.

        Args:
            inputs: ``labels`` and ``expression``, each a Collection with one
                item per section, paired by position.
            config: Supplies ``clusters`` (default 3).

        Returns:
            ``{"regions": Collection([...])}`` holding one table.

        Raises:
            ValueError: if the two inputs hold different numbers of sections.
        """
        labels = _as_items(inputs.get("labels"))
        expression = _as_items(inputs.get("expression"))
        if len(labels) != len(expression):
            raise ValueError(
                f"Joint Region Profiles received {len(labels)} label map(s) and "
                f"{len(expression)} expression table(s); pairing is positional, so the counts must match."
            )

        rows: list[dict[str, Any]] = []
        for label_image, table in zip(labels, expression, strict=True):
            rows.extend(_region_rows(label_image, table))
        if not rows:
            raise ValueError("No position fell inside a labelled region; check the pairing and the segmentation.")

        frame = pd.DataFrame(rows)
        genes = [column for column in frame.columns if column.startswith(("hk_", "mk_"))]
        clustered = frame["n_positions"] >= MIN_POSITIONS_PER_REGION
        profiles = frame.loc[clustered, genes].to_numpy(dtype=float)

        # Standardise each gene across regions before clustering. Without it a
        # highly expressed housekeeping gene dominates every distance and the
        # clusters describe abundance instead of identity.
        centred = profiles - profiles.mean(axis=0)
        spread = centred.std(axis=0)
        standardised = centred / np.where(spread > 0, spread, 1.0)

        assignment = _order_clusters(standardised, kmeans(standardised, int(config.get("clusters", 3))))
        frame["cluster"] = pd.Series(dtype="Int64")
        frame.loc[clustered, "cluster"] = assignment

        ordered = ["section", "region", "cluster", "n_positions", "centroid_y", "centroid_x", *genes]
        frame = frame[ordered].sort_values(["section", "region"]).reset_index(drop=True)
        return {"regions": Collection([DataFrame(data=pa.Table.from_pandas(frame, preserve_index=False))])}


def _as_items(value: Any) -> list[Any]:
    """Read an input port as a list of items, whether or not it is a Collection."""
    if value is None:
        return []
    return list(value) if isinstance(value, Collection) else [value]


def _region_rows(label_image: Image, table: DataFrame) -> list[dict[str, Any]]:
    """One row per labelled region of a single section."""
    label_map = np.asarray(label_image.to_memory(), dtype=int)
    frame = table.to_memory().to_pandas()
    genes = [column for column in frame.columns if column not in COORDINATE_COLUMNS]

    height, width = label_map.shape
    ys = np.clip(frame["y"].to_numpy(dtype=int), 0, height - 1)
    xs = np.clip(frame["x"].to_numpy(dtype=int), 0, width - 1)
    frame = frame.assign(region=label_map[ys, xs])
    on_tissue = frame[frame["region"] > 0]

    section = str(frame["section"].iloc[0]) if "section" in frame.columns and len(frame) else "?"
    rows: list[dict[str, Any]] = []
    for region, group in on_tissue.groupby("region", sort=True):
        row: dict[str, Any] = {
            "section": section,
            "region": int(region),
            "n_positions": len(group),
            "centroid_y": round(float(group["y"].mean()), 2),
            "centroid_x": round(float(group["x"].mean()), 2),
        }
        row.update({gene: round(float(group[gene].mean()), 5) for gene in genes})
        rows.append(row)
    return rows
