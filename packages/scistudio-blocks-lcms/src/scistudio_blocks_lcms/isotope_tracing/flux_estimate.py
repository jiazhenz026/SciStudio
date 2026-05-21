"""FluxEstimate - simple steady-state flux estimate (T-LCMS-011)."""

from __future__ import annotations

from types import ModuleType
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, cast

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio_blocks_lcms._base import _LCMSBlockMixin
from scistudio_blocks_lcms.types import MIDTable, PeakTable, SampleMetadata

if TYPE_CHECKING:
    import pandas as pd

TDataObject = TypeVar("TDataObject", bound=DataObject)


class FluxEstimate(_LCMSBlockMixin, ProcessBlock):
    """Naive steady-state flux estimate (labelling rate x pool size).

    NOT a replacement for full 13C-MFA - see INCA / OpenFLUX / Metran
    for proper EMU-based flux analysis.
    """

    name: ClassVar[str] = "Flux Estimate"
    type_name: ClassVar[str] = "lcms.flux_estimate"
    subcategory: ClassVar[str] = "isotope_tracing"
    description: ClassVar[str] = (
        "Naive steady-state flux estimate via linear fit to fractional "
        "labelling vs. time, multiplied by optional pool size. NOT a "
        "13C-MFA replacement; use INCA / OpenFLUX / Metran for that."
    )

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="mid_table",
            accepted_types=[MIDTable],
            required=True,
            description="MID table for fractional labelling computation",
        ),
        InputPort(
            name="sample_metadata",
            accepted_types=[SampleMetadata],
            required=True,
            description="Per-sample metadata with the time column",
        ),
        InputPort(
            name="pool_size_table",
            accepted_types=[PeakTable],
            required=False,
            description="Optional peak table providing per-compound pool sizes",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="flux",
            accepted_types=[DataFrame],
            description="Long-format DataFrame: compound, group, labeling_rate, intercept, r_squared, p_value, stderr, pool_size, estimated_flux",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "time_points_column": {
                "type": "string",
                "default": "time_hours",
                "title": "Time Column Name",
                "ui_priority": 1,
            },
            "group_column": {
                "type": ["string", "null"],
                "default": None,
                "title": "Group Column Name",
                "ui_priority": 2,
            },
        },
        "required": ["time_points_column"],
    }

    def run(
        self,
        inputs: dict[str, Collection],
        config: BlockConfig,
    ) -> dict[str, Collection]:
        """Compute the long-format flux estimate DataFrame."""
        from scipy.stats import linregress

        mid_table = _extract_single_item(inputs["mid_table"], MIDTable, "mid_table")
        sample_metadata = _extract_single_item(inputs["sample_metadata"], SampleMetadata, "sample_metadata")
        pool_size_table = None
        if "pool_size_table" in inputs:
            pool_size_table = _extract_optional_single_item(inputs["pool_size_table"], PeakTable, "pool_size_table")

        time_column = str(config.get("time_points_column", "time_hours"))
        group_column = config.get("group_column")

        metadata_frame = _as_pandas_frame(sample_metadata)
        if time_column not in metadata_frame.columns:
            raise ValueError(f"FluxEstimate: time column {time_column!r} is missing")

        metadata_meta = cast(SampleMetadata.Meta, sample_metadata.meta)
        sample_id_column = metadata_meta.sample_id_column
        if sample_id_column not in metadata_frame.columns:
            raise ValueError(f"FluxEstimate: sample id column {sample_id_column!r} is missing")

        compound_column = _resolve_compound_column(_as_pandas_frame(mid_table))
        fractional_frame = _fractional_labeling_frame(mid_table, compound_column)
        merged = fractional_frame.merge(
            metadata_frame,
            left_on="sample",
            right_on=sample_id_column,
            how="left",
            validate="many_to_one",
        )

        group_key = "_group"
        if group_column is None:
            merged[group_key] = "all"
        else:
            group_name = str(group_column)
            if group_name not in merged.columns:
                raise ValueError(f"FluxEstimate: group column {group_name!r} is missing")
            merged[group_key] = merged[group_name]

        pool_sizes: dict[tuple[object, object], float] = {}
        if pool_size_table is not None:
            peak_frame = _as_pandas_frame(pool_size_table)
            peak_compound_column = _resolve_compound_column(peak_frame)
            intensity_column = "intensity" if "intensity" in peak_frame.columns else "Intensity"
            peak_sample_column = sample_id_column if sample_id_column in peak_frame.columns else "sample_id"
            if peak_sample_column not in peak_frame.columns:
                raise ValueError(f"FluxEstimate: pool size table is missing sample column {sample_id_column!r}")
            if intensity_column not in peak_frame.columns:
                raise ValueError("FluxEstimate: pool size table is missing an intensity column")
            merged_peak = peak_frame.merge(
                metadata_frame,
                left_on=peak_sample_column,
                right_on=sample_id_column,
                how="left",
                validate="many_to_one",
            )
            if group_column is None:
                merged_peak[group_key] = "all"
            else:
                merged_peak[group_key] = merged_peak[str(group_column)]
            grouped_pool = merged_peak.groupby([peak_compound_column, group_key], sort=False)[intensity_column].mean()
            pool_sizes = {(compound, group): float(value) for (compound, group), value in grouped_pool.items()}

        rows: list[dict[str, object]] = []
        for (compound, group), group_frame in merged.groupby(["compound", group_key], sort=False):
            distinct_timepoints = group_frame[time_column].dropna().unique()
            if len(distinct_timepoints) < 2:
                raise ValueError("FluxEstimate: each compound/group requires at least two distinct timepoints")
            result = linregress(
                group_frame[time_column].astype(float),
                group_frame["fractional_labeling"].astype(float),
            )
            labeling_rate = float(result.slope)
            pool_size = float(pool_sizes.get((compound, group), 1.0))
            rows.append(
                {
                    "compound": compound,
                    "group": group,
                    "labeling_rate": labeling_rate,
                    "intercept": float(result.intercept),
                    "r_squared": float(result.rvalue**2),
                    "p_value": float(result.pvalue),
                    "stderr": float(result.stderr),
                    "pool_size": pool_size,
                    "estimated_flux": labeling_rate * pool_size,
                }
            )

        result_object = _to_core_dataframe(_pandas().DataFrame(rows))
        return {"flux": Collection(items=[result_object], item_type=DataFrame)}


def _pandas() -> ModuleType:
    import pandas as pd

    return cast(ModuleType, pd)


def _extract_single_item(payload: Collection | DataObject, expected_type: type[TDataObject], name: str) -> TDataObject:
    if isinstance(payload, Collection):
        if len(payload) != 1:
            raise ValueError(f"FluxEstimate: input {name!r} must contain exactly one item")
        item = payload[0]
    else:
        item = payload
    if not isinstance(item, expected_type):
        raise TypeError(f"FluxEstimate: input {name!r} must be {expected_type.__name__}")
    return cast(TDataObject, item)


def _extract_optional_single_item(
    payload: Collection | DataObject,
    expected_type: type[TDataObject],
    name: str,
) -> TDataObject | None:
    if isinstance(payload, Collection) and len(payload) == 0:
        return None
    return _extract_single_item(payload, expected_type, name)


def _as_pandas_frame(item: DataObject) -> pd.DataFrame:
    pd = _pandas()
    raw = getattr(item, "_data", None)
    if isinstance(raw, pd.DataFrame):
        return raw.copy()
    if raw is not None:
        return pd.DataFrame(raw).copy()
    materialized = item.to_memory()
    if isinstance(materialized, pd.DataFrame):
        return materialized.copy()
    return pd.DataFrame(materialized).copy()


def _resolve_compound_column(frame: pd.DataFrame) -> str:
    if "Compound" in frame.columns:
        return "Compound"
    if "compound" in frame.columns:
        return "compound"
    raise ValueError("FluxEstimate: no compound column found")


def _fractional_labeling_frame(mid_table: MIDTable, compound_column: str) -> pd.DataFrame:
    frame = _as_pandas_frame(mid_table)
    meta = cast(MIDTable.Meta, mid_table.meta)
    tracer_atoms = list(meta.tracer_atoms)
    sample_columns = list(meta.sample_columns)
    rows: list[dict[str, object]] = []
    for compound, compound_frame in frame.groupby(compound_column, sort=False):
        m0_rows = compound_frame.copy()
        for tracer_atom in tracer_atoms:
            m0_rows = m0_rows.loc[m0_rows[tracer_atom] == 0]
        if m0_rows.empty:
            raise ValueError(f"FluxEstimate: compound {compound!r} is missing an M+0 row")
        m0_row = m0_rows.iloc[0]
        for sample_column in sample_columns:
            rows.append(
                {
                    "compound": compound,
                    "sample": sample_column,
                    "fractional_labeling": 1.0 - float(m0_row[sample_column]),
                }
            )
    return _pandas().DataFrame(rows)


def _to_core_dataframe(frame: pd.DataFrame) -> DataFrame:
    result = DataFrame(columns=list(frame.columns), row_count=len(frame))
    result._data = frame.reset_index(drop=True)  # type: ignore[attr-defined]
    return result
