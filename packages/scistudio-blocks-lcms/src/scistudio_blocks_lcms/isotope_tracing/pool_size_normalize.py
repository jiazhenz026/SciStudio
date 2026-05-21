"""PoolSizeNormalize - IS / TIC / median normalization for PeakTables (T-LCMS-012)."""

from __future__ import annotations

from types import ModuleType
from typing import TYPE_CHECKING, Any, ClassVar, cast

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio_blocks_lcms._base import _LCMSBlockMixin
from scistudio_blocks_lcms.types import PeakTable

if TYPE_CHECKING:
    import pandas as pd


class PoolSizeNormalize(_LCMSBlockMixin, ProcessBlock):
    """Normalize a :class:`PeakTable` by IS / TIC / median."""

    name: ClassVar[str] = "Pool Size Normalize"
    type_name: ClassVar[str] = "lcms.pool_size_normalize"
    subcategory: ClassVar[str] = "isotope_tracing"
    description: ClassVar[str] = (
        "Normalize a PeakTable by internal standard, total ion current, "
        "or per-sample median. Output is a PeakTable with preserved Meta."
    )

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="peak_table",
            accepted_types=[PeakTable],
            required=True,
            description="Peak table to normalize",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="normalized",
            accepted_types=[PeakTable],
            description="Normalized peak table (same Meta as input)",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["IS", "TIC", "median"],
                "default": "TIC",
                "title": "Normalization method",
                "ui_priority": 1,
            },
            "reference_compound": {
                "type": ["string", "null"],
                "default": None,
                "title": "IS Reference Compound",
                "ui_priority": 2,
            },
            "intensity_column": {
                "type": "string",
                "default": "intensity",
                "title": "Intensity column",
                "ui_priority": 3,
            },
            "compound_column": {
                "type": "string",
                "default": "compound",
                "title": "Compound column",
                "ui_priority": 4,
            },
        },
    }

    def process_item(
        self,
        item: PeakTable,
        config: BlockConfig,
        state: Any = None,
    ) -> PeakTable:
        """Normalize *item* and return a new :class:`PeakTable`."""
        frame = _as_pandas_frame(item)
        method = str(config.get("method", "TIC"))
        intensity_column = str(config.get("intensity_column", "intensity"))
        compound_column = str(config.get("compound_column", "compound"))
        sample_column = "sample_id" if "sample_id" in frame.columns else "sample"

        if intensity_column not in frame.columns:
            raise ValueError(f"PoolSizeNormalize: intensity column {intensity_column!r} is missing")
        if compound_column not in frame.columns:
            raise ValueError(f"PoolSizeNormalize: compound column {compound_column!r} is missing")
        if sample_column not in frame.columns:
            raise ValueError("PoolSizeNormalize: sample column is missing")

        normalized = frame.copy()
        if method == "IS":
            reference_compound = config.get("reference_compound")
            if not reference_compound:
                raise ValueError("PoolSizeNormalize: reference_compound is required for IS normalization")
            reference_rows = normalized.loc[normalized[compound_column] == reference_compound]
            if reference_rows.empty:
                raise ValueError(f"PoolSizeNormalize: reference compound {reference_compound!r} is missing")
            divisors = reference_rows.groupby(sample_column, sort=False)[intensity_column].first().to_dict()
        elif method == "TIC":
            divisors = normalized.groupby(sample_column, sort=False)[intensity_column].sum().to_dict()
        elif method == "median":
            divisors = normalized.groupby(sample_column, sort=False)[intensity_column].median().to_dict()
        else:
            raise ValueError(f"PoolSizeNormalize: unsupported method {method!r}")

        normalized[intensity_column] = normalized.apply(
            lambda row: float(row[intensity_column]) / float(divisors[row[sample_column]]),
            axis=1,
        )
        return _clone_peak_table(item, normalized)


def _pandas() -> ModuleType:
    import pandas as pd

    return cast(ModuleType, pd)


def _as_pandas_frame(item: PeakTable) -> pd.DataFrame:
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


def _clone_peak_table(source: PeakTable, frame: pd.DataFrame) -> PeakTable:
    result = PeakTable(
        columns=list(frame.columns),
        row_count=len(frame),
        schema=source.schema,
        framework=source.framework.derive(),
        meta=source.meta,
        user=dict(source.user),
        storage_ref=None,
    )
    result._data = frame.reset_index(drop=True)  # type: ignore[attr-defined]
    return result
