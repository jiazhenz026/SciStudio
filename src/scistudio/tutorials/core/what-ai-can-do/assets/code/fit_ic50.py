"""Fit a dose-response curve and report its IC50.

Written into the tutorial project by core tutorial 3's scripted agent. It takes
the QC-annotated plate, averages the replicate wells QC kept in each group, and
fits the concentration at which viability falls to half — the IC50, which is
the number this whole experiment exists to produce.

**Two inputs, and that is the point of the level's middle act.** The plate
table names a *group* per well and nothing else; what each group was dosed
with is not in it. The concentrations exist only in the export's filename, so
something has to turn that filename into a table before a curve can be fitted
at all. That something is the AI Block upstream, and this block is what makes
its absence a hard stop rather than a nice-to-have: with no ``metadata`` there
is no x axis.

The metadata table is also where the controls are dealt with. ``VEH`` and
``BLANK`` are labels in the group column that are not doses, and averaging them
into a dose-response would be nonsense. They are excluded by having no
concentration in the metadata rather than by a rule written into this file — a
list of control names hard-coded in the fit would be a second place to keep in
step with the plate.

**The fit is real and it is twenty lines**, because the reader can open this
file and a fake would be obvious. SciStudio ships neither SciPy nor
scikit-learn, so there is no curve_fit to call; instead the sigmoid is
straightened first. A Hill curve

    viability = 100 / (1 + (dose / IC50) ** slope)

rearranges so that the log-odds of viability are linear in log dose:

    log(v / (100 - v)) = -slope * (log10(dose) - log10(IC50)) * ln(10)

so an ordinary least-squares line through (log10 dose, logit viability) has the
IC50 at its x-intercept. This is the classic log-logit linearisation. It
assumes the curve runs between 0% and 100%, which is what a normalised
viability plate is reported as, and it is the honest choice here over an
iterative fit nobody could check by eye.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import pyarrow as pa

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import Collection, DataFrame

GROUP_COLUMN = "group"
METRIC_COLUMN = "viability_pct"
DOSE_COLUMN = "concentration_um"

# Viability is clipped away from 0 and 100 before the logit: both are infinite
# on the log-odds scale, and a single saturated well would otherwise take the
# whole fit with it.
EPSILON = 0.001


class FitIc50Block(ProcessBlock):
    """Join the plate to its dose metadata, then fit the IC50.

    Emits one row per dose — what was measured and how many wells it rests on,
    plus the fitted value there — with the fitted parameters repeated on every
    row, so the curve and the number that came out of it travel together in one
    table.
    """

    name: ClassVar[str] = "Fit IC50"
    type_name: ClassVar[str] = "fit_ic50"
    description: ClassVar[str] = "Join a grouped plate to its dose metadata and fit the IC50."
    algorithm: ClassVar[str] = "log_logit_linearised_hill_fit"

    # Teal, and a falling line: the curve this block fits goes down as the dose
    # goes up, which is the whole shape of the result.
    ui_color: ClassVar[str] = "#a3ddd8"
    ui_icon: ClassVar[str] = "TrendingDown"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="table", accepted_types=[DataFrame], description="QC-annotated plate, one row per well"),
        # `required=False` is about the *canvas*, not about the science: the
        # workflow validator refuses to start a run with a dangling required
        # port, and the reader would get "required input port 'metadata' has
        # no incoming connection" instead of ever reaching this block. The
        # block is where the explanation belongs, so the port lets the run in
        # and `run` turns it away with a reason worth reading.
        InputPort(
            name="metadata",
            accepted_types=[DataFrame],
            required=False,
            description="What each group was dosed with: group, concentration_um. No fit without it.",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="curve", accepted_types=[DataFrame], description="Per-dose means and the fitted IC50"),
        # The same fit at well level. A per-dose mean is what you save and
        # quote; the eight wells behind each mean are what you should look at
        # before you believe it, and a picture cannot draw a spread it was
        # never given. Both come out of one fit so they cannot disagree.
        OutputPort(
            name="wells",
            accepted_types=[DataFrame],
            description="Every kept well with its dose and the fitted curve, for plotting",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    @staticmethod
    def _one_frame(collection: Any, port: str) -> Any:
        """The single table on *port*, as pandas.

        Both inputs are one-table collections in this workflow; anything else
        is an authoring mistake worth naming rather than silently taking the
        first item of.
        """
        items = list(collection) if isinstance(collection, Collection) else [collection]
        if len(items) != 1:
            raise ValueError(f"input {port!r} carries {len(items)} tables; Fit IC50 expects exactly one.")
        return items[0].to_memory().to_pandas()

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Fit the curve over the wells QC kept, at the doses metadata names.

        Args:
            inputs: ``table`` (the plate) and ``metadata`` (group to dose).
            config: Unused; the block has no parameters.

        Returns:
            ``curve`` — one row per dose carrying ``concentration_um``,
            ``group``, ``n_wells``, ``mean_viability_pct``,
            ``fitted_viability_pct``, ``ic50_um`` and ``hill_slope`` — and
            ``wells``, the same thing at well level: every kept well with its
            dose, its own reading, and the fitted value at that dose.

        Raises:
            ValueError: An input is missing or carries more than one table; the
                metadata lacks the two columns the join needs; fewer than three
                doses survived; or every dose reads the same. Each is a case
                where inventing a curve would be worse than saying what is
                wrong.
        """
        for port in ("table", "metadata"):
            if port not in inputs:
                raise ValueError(
                    f"Fit IC50 needs its {port!r} input connected. The plate names groups, not doses — "
                    "without the metadata table there is nothing to put on the x axis."
                )

        plate = self._one_frame(inputs["table"], "table")
        metadata = self._one_frame(inputs["metadata"], "metadata")

        missing = {GROUP_COLUMN, DOSE_COLUMN} - set(metadata.columns)
        if missing:
            raise ValueError(
                f"metadata must carry {GROUP_COLUMN!r} and {DOSE_COLUMN!r}; "
                f"missing {sorted(missing)} in {list(metadata.columns)}."
            )

        kept = plate[plate["qc_keep"].astype(bool)] if "qc_keep" in plate.columns else plate
        kept = kept[kept[METRIC_COLUMN].notna()]

        # An inner join is what drops the controls: VEH and BLANK are groups
        # with no concentration, so they simply do not survive it.
        doses = metadata[[GROUP_COLUMN, DOSE_COLUMN]].dropna(subset=[DOSE_COLUMN])
        joined = kept.merge(doses, on=GROUP_COLUMN, how="inner")

        summary = (
            joined.groupby([DOSE_COLUMN, GROUP_COLUMN])[METRIC_COLUMN]
            .agg(["mean", "count"])
            .reset_index()
            .sort_values(DOSE_COLUMN)
        )
        if len(summary) < 3:
            raise ValueError(f"only {len(summary)} dose(s) survived QC and the join; an IC50 needs at least three.")

        x = np.log10(summary[DOSE_COLUMN].to_numpy(dtype=float))
        means = summary["mean"].to_numpy(dtype=float)
        fraction = np.clip(means / 100.0, EPSILON, 1.0 - EPSILON)
        y = np.log(fraction / (1.0 - fraction))

        if np.ptp(y) == 0:
            raise ValueError("every dose reads the same viability; there is no dose response to fit.")

        slope, intercept = np.polyfit(x, y, 1)
        ic50 = float(10 ** (-intercept / slope))
        # The Hill slope is the log-odds slope taken back off the natural-log
        # scale, and negated: a drug that works has viability going down.
        hill_slope = float(-slope / np.log(10))

        fitted = 100.0 / (1.0 + np.exp(-(slope * x + intercept)))
        curve = pa.table(
            {
                DOSE_COLUMN: summary[DOSE_COLUMN].to_numpy(dtype=float),
                GROUP_COLUMN: summary[GROUP_COLUMN].astype(str).tolist(),
                "n_wells": summary["count"].to_numpy(dtype="int64"),
                "mean_viability_pct": np.round(means, 2),
                "fitted_viability_pct": np.round(fitted, 2),
                "ic50_um": np.full(len(summary), round(ic50, 4)),
                "hill_slope": np.full(len(summary), round(hill_slope, 3)),
            }
        )

        # Well level: the same fit, carried down onto each row that went into
        # it, so one binding is enough to draw both the spread and the curve.
        per_dose = dict(zip(summary[DOSE_COLUMN].to_numpy(dtype=float), np.round(fitted, 2), strict=True))
        wells = joined[["well", GROUP_COLUMN, DOSE_COLUMN, METRIC_COLUMN]].copy()
        wells["fitted_viability_pct"] = wells[DOSE_COLUMN].map(per_dose)
        wells["ic50_um"] = round(ic50, 4)
        wells["hill_slope"] = round(hill_slope, 3)

        return {
            "curve": Collection([DataFrame(data=curve)]),
            "wells": Collection([DataFrame(data=pa.Table.from_pandas(wells, preserve_index=False))]),
        }
