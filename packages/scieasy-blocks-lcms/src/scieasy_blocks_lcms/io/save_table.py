"""SaveTable — generic DataFrame saver (T-LCMS-006 / part 2).

Skeleton @ c08a885. Per ``docs/specs/phase11-lcms-block-spec.md`` §9
T-LCMS-006.

Generic sink block that writes any :class:`DataFrame` (including the
plugin-specific :class:`PeakTable`, :class:`MIDTable`,
:class:`SampleMetadata` subclasses via Liskov) to CSV / TSV / XLSX.

Per master plan §2.4 there is **NO** dedicated ``SaveMIDTable`` block —
this generic saver covers every output need.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    import pandas as pd

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort
from scieasy.blocks.io.io_block import IOBlock
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy.core.types.dataframe import DataFrame
from scieasy_blocks_lcms._base import _LCMSBlockMixin


class SaveTable(_LCMSBlockMixin, IOBlock):
    """Generic CSV / TSV / XLSX sink for any :class:`DataFrame` subclass.

    See spec §9 T-LCMS-006 for the 8 acceptance criteria.
    """

    direction: ClassVar[str] = "output"
    type_name: ClassVar[str] = "lcms.save_table"
    name: ClassVar[str] = "Save Table"
    subcategory: ClassVar[str] = "io"
    description: ClassVar[str] = (
        "Save any DataFrame (PeakTable / MIDTable / SampleMetadata / generic) to CSV, TSV, or XLSX."
    )

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="table",
            accepted_types=[DataFrame],
            required=True,
            description="DataFrame to save (any subclass accepted)",
        ),
    ]

    # Sink — produces no downstream artifacts.
    output_ports: ClassVar[list[Any]] = []

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            # ADR-030: ``path`` is inherited from IOBlock base class via MRO merge.
            # Direction-aware post-processing auto-switches to directory_browser,
            # fixing the incorrect file_browser that was declared here previously.
            "format": {
                "type": "string",
                "enum": ["csv", "tsv", "xlsx"],
                "default": "csv",
                "title": "Format",
                "ui_priority": 1,
            },
            "index": {
                "type": "boolean",
                "default": False,
                "title": "Write row index",
                "ui_priority": 2,
            },
        },
        "required": [],
    }

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """Not supported — :class:`SaveTable` is output-only."""
        raise NotImplementedError("T-LCMS-006 SaveTable is direction='output'; load() is unreachable.")

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Persist *obj* to the configured path.

        Implementation must:

        * create parent directories if they do not exist
        * dispatch to ``df.to_csv`` / ``df.to_csv(sep="\\t")`` /
          ``df.to_excel`` based on ``format``
        * respect ``index`` (default ``False``)
        * raise :class:`ValueError` on unknown ``format``
        * materialise the underlying pandas DataFrame from
          ``obj.user["pandas_df"]`` cache or ``obj.view().to_pandas()``
        """
        table = _unwrap_table(obj)
        frame = _to_pandas(table)

        output_path = Path(config.get("path"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        file_format = str(config.get("format", "csv"))
        include_index = bool(config.get("index", False))
        if file_format == "csv":
            frame.to_csv(output_path, index=include_index)
            return
        if file_format == "tsv":
            frame.to_csv(output_path, sep="\t", index=include_index)
            return
        if file_format == "xlsx":
            frame.to_excel(output_path, index=include_index)
            return
        raise ValueError(f"SaveTable: unsupported format '{file_format}'")


def _unwrap_table(obj: DataObject | Collection) -> DataFrame:
    if isinstance(obj, Collection):
        if len(obj) != 1:
            raise ValueError("SaveTable expects a single DataFrame item")
        item = obj[0]
    else:
        item = obj

    if not isinstance(item, DataFrame):
        raise TypeError(f"SaveTable requires a DataFrame, got {type(item).__name__}")
    return item


def _to_pandas(table: DataFrame) -> pd.DataFrame:
    import pandas as pd

    cached = table.user.get("pandas_df")
    if isinstance(cached, pd.DataFrame):
        return cached.copy()

    arrow_table = getattr(table, "_arrow_table", None)
    if arrow_table is not None and hasattr(arrow_table, "to_pandas"):
        return arrow_table.to_pandas()

    if table.storage_ref is not None:
        materialized = table.view().to_memory()
        if isinstance(materialized, pd.DataFrame):
            return materialized.copy()
        if hasattr(materialized, "to_pandas"):
            return materialized.to_pandas()
        return pd.DataFrame(materialized)

    raise ValueError("SaveTable requires a cached pandas DataFrame or a storage-backed table")
