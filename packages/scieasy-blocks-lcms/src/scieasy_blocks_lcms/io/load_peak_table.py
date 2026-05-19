"""LoadPeakTable — CSV/TSV/XLSX peak table loader (T-LCMS-004).

Skeleton @ c08a885. Per ``docs/specs/phase11-lcms-block-spec.md`` §9
T-LCMS-004.

Reads a peak table from CSV / TSV / XLSX, auto-detects the source tool
(ElMAVEN / MZmine / XCMS) from column-name markers, and wraps the
result as a :class:`PeakTable`.

Source autodetection signatures (per spec):

* **ElMAVEN**: any of ``{"compound", "formula", "medMz", "medRt",
  "expectedRtDiff"}``.
* **MZmine**: any of ``{"row ID", "row m/z", "row retention time"}``.
* **XCMS**: any of ``{"mzmed", "rtmed", "mzmin", "mzmax"}``.
* Fallback: ``ElMAVEN`` (the user's primary tool).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    import pandas as pd

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import OutputPort
from scieasy.blocks.io.io_block import IOBlock
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy_blocks_lcms._base import _LCMSBlockMixin
from scieasy_blocks_lcms.types import PeakTable

_ELMAVEN_COLUMNS = frozenset({"compound", "formula", "medMz", "medRt", "expectedRtDiff"})
_MZMINE_COLUMNS = frozenset({"row ID", "row m/z", "row retention time"})
_XCMS_COLUMNS = frozenset({"mzmed", "rtmed", "mzmin", "mzmax"})


class LoadPeakTable(_LCMSBlockMixin, IOBlock):
    """CSV/TSV/XLSX peak table loader with source autodetection.

    See spec §9 T-LCMS-004 for the 14 acceptance criteria.
    """

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "lcms.load_peak_table"
    name: ClassVar[str] = "Load Peak Table"
    subcategory: ClassVar[str] = "io"
    description: ClassVar[str] = (
        "Load a peak table (CSV/TSV/XLSX) into a typed PeakTable. "
        "Auto-detects ElMAVEN / MZmine / XCMS column-name conventions."
    )

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="peak_table",
            accepted_types=[PeakTable],
            description="Loaded peak table with source-tool tagged Meta",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": ["string", "array"],
                "items": {"type": "string"},
                "title": "Peak table file(s)",
                "ui_priority": 0,
                "ui_widget": "file_browser",
            },
            "source": {
                "type": "string",
                "enum": ["auto", "ElMAVEN", "MZmine", "XCMS"],
                "default": "auto",
                "title": "Source tool",
                "ui_priority": 1,
            },
            "sheet_name": {
                "type": ["string", "integer", "null"],
                "default": None,
                "title": "XLSX sheet (name or index)",
                "ui_priority": 2,
            },
            "polarity": {
                "type": ["string", "null"],
                "enum": [None, "+", "-"],
                "default": None,
                "title": "Polarity (optional)",
                "ui_priority": 3,
            },
        },
        "required": ["path"],
    }

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """Read peak table file(s) and return a :class:`Collection[PeakTable]`.

        ADR-031 D4: uses :meth:`persist_table` to write the DataFrame
        payload to arrow storage instead of storing a pandas DataFrame
        in the ``user`` dict (which violates JSON-serializability per
        ADR-017).

        Accepts ``config["path"]`` as a single string or a list of strings
        (matching the :class:`LoadImage` multi-file pattern).

        Raises:
            FileNotFoundError: If any path does not exist.
            ValueError: If the table is empty or path config is invalid.
        """
        raw_path = config.get("path")
        if isinstance(raw_path, list):
            paths = [Path(p) for p in raw_path if isinstance(p, str) and p]
        elif isinstance(raw_path, str) and raw_path:
            paths = [Path(raw_path)]
        else:
            raise ValueError("LoadPeakTable: config['path'] must be a non-empty string or list of strings")

        source = str(config.get("source", "auto"))
        tables: list[PeakTable] = []
        for path in paths:
            if not path.exists():
                raise FileNotFoundError(f"LoadPeakTable: source file not found: {path}")
            frame = _read_table(path, sheet_name=config.get("sheet_name"))
            if frame.empty:
                raise ValueError(f"LoadPeakTable: table is empty: {path}")
            resolved_source = _detect_source(frame.columns) if source == "auto" else source

            # ADR-031 D4: persist to arrow storage instead of storing
            # pandas DataFrame in user dict.
            storage_ref = None
            if output_dir:
                import pyarrow as pa

                arrow_table = pa.Table.from_pandas(frame)
                storage_ref = self.persist_table(arrow_table, output_dir)

            table = PeakTable(
                columns=[str(col) for col in frame.columns],
                row_count=len(frame),
                schema={str(col): str(dtype) for col, dtype in frame.dtypes.items()},
                meta=PeakTable.Meta(
                    source=resolved_source,
                    polarity=config.get("polarity"),
                ),
                storage_ref=storage_ref,
            )
            # ADR-031: no longer store pandas_df in user dict.
            # The data is now in arrow storage via storage_ref.
            tables.append(table)
        return Collection(items=tables, item_type=PeakTable)

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Not supported — use :class:`SaveTable` for output."""
        raise NotImplementedError("T-LCMS-004 LoadPeakTable is direction='input'; use SaveTable to write.")


def _read_table(path: Path, *, sheet_name: str | int | None) -> pd.DataFrame:
    import pandas as pd

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, sheet_name=0 if sheet_name is None else sheet_name)
    raise ValueError(f"LoadPeakTable: unsupported file format: {path.suffix}")


def _detect_source(columns: pd.Index) -> str:
    names = {str(column) for column in columns}
    if names & _ELMAVEN_COLUMNS:
        return "ElMAVEN"
    if names & _MZMINE_COLUMNS:
        return "MZmine"
    if names & _XCMS_COLUMNS:
        return "XCMS"
    return "ElMAVEN"
