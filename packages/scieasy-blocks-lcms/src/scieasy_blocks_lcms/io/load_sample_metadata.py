"""LoadSampleMetadata — sample-level metadata loader (T-LCMS-006 / part 1).

Skeleton @ c08a885. Per ``docs/specs/phase11-lcms-block-spec.md`` §9
T-LCMS-006.

Mirrors :class:`LoadPeakTable` but wraps the result as
:class:`SampleMetadata` and exposes a configurable
``sample_id_column`` (default ``"sample_id"``).
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
from scieasy_blocks_lcms.types import SampleMetadata


class LoadSampleMetadata(_LCMSBlockMixin, IOBlock):
    """Load a per-sample metadata file into a :class:`SampleMetadata`.

    See spec §9 T-LCMS-006 for the 6 acceptance criteria.
    """

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "lcms.load_sample_metadata"
    name: ClassVar[str] = "Load Sample Metadata"
    subcategory: ClassVar[str] = "io"
    description: ClassVar[str] = (
        "Load per-sample metadata (group, timepoint, replicate, etc.) "
        "from CSV / TSV / XLSX into a typed SampleMetadata."
    )

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="sample_metadata",
            accepted_types=[SampleMetadata],
            description="Loaded per-sample metadata",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": ["string", "array"],
                "items": {"type": "string"},
                "title": "Sample metadata file(s)",
                "ui_priority": 0,
                "ui_widget": "file_browser",
            },
            "sample_id_column": {
                "type": "string",
                "default": "sample_id",
                "title": "Sample ID column",
                "ui_priority": 1,
            },
            "sheet_name": {
                "type": ["string", "integer", "null"],
                "default": None,
                "title": "XLSX sheet (name or index)",
                "ui_priority": 2,
            },
        },
        "required": ["path"],
    }

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """Read metadata file(s) and return :class:`Collection[SampleMetadata]`.

        ADR-031 D4: uses :meth:`persist_table` to write the DataFrame
        payload to arrow storage instead of storing a pandas DataFrame
        in the ``user`` dict.

        Accepts ``config["path"]`` as a single string or a list of strings
        (matching the :class:`LoadImage` multi-file pattern).

        Raises:
            FileNotFoundError: If any path does not exist.
            ValueError: If the sample ID column is missing or path config is invalid.
        """
        raw_path = config.get("path")
        if isinstance(raw_path, list):
            paths = [Path(p) for p in raw_path if isinstance(p, str) and p]
        elif isinstance(raw_path, str) and raw_path:
            paths = [Path(raw_path)]
        else:
            raise ValueError("LoadSampleMetadata: config['path'] must be a non-empty string or list of strings")

        sample_id_column = str(config.get("sample_id_column", "sample_id"))
        items: list[SampleMetadata] = []
        for path in paths:
            if not path.exists():
                raise FileNotFoundError(f"LoadSampleMetadata: source file not found: {path}")
            frame = _read_table(path, sheet_name=config.get("sheet_name"))
            if sample_id_column not in frame.columns:
                raise ValueError(f"LoadSampleMetadata requires column '{sample_id_column}'")

            # ADR-031 D4: persist to arrow storage instead of storing
            # pandas DataFrame in user dict.
            storage_ref = None
            if output_dir:
                import pyarrow as pa

                arrow_table = pa.Table.from_pandas(frame)
                storage_ref = self.persist_table(arrow_table, output_dir)

            sm = SampleMetadata(
                columns=[str(col) for col in frame.columns],
                row_count=len(frame),
                schema={str(col): str(dtype) for col, dtype in frame.dtypes.items()},
                meta=SampleMetadata.Meta(sample_id_column=sample_id_column),
                storage_ref=storage_ref,
            )
            # ADR-031: no longer store pandas_df in user dict.
            items.append(sm)
        return Collection(items=items, item_type=SampleMetadata)

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Not supported — use :class:`SaveTable` for output."""
        raise NotImplementedError("T-LCMS-006 LoadSampleMetadata is direction='input'; use SaveTable to write.")


def _read_table(path: Path, *, sheet_name: str | int | None) -> pd.DataFrame:
    import pandas as pd

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, sheet_name=0 if sheet_name is None else sheet_name)
    raise ValueError(f"LoadSampleMetadata: unsupported file format: {path.suffix}")
