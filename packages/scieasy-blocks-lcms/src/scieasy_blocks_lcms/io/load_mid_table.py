"""LoadMIDTable — AccuCor MID table loader (T-LCMS-005).

Skeleton @ c08a885. Per ``docs/specs/phase11-lcms-block-spec.md`` §9
T-LCMS-005.

Loads the long-format MID table produced by AccuCor (or any tool that
emits the same shape) and auto-detects sample columns by excluding the
known identity columns and the known tracer-atom columns.

Spec sections referenced:

* §8 Q-3 — long format is canonical.
* §8 Q-4 — sample-column detection heuristic.
* §8 Q-5 — tracer atoms (single vs multi-tracer).
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
from scieasy_blocks_lcms.types import MIDTable

#: Identity columns dropped from sample-column auto-detection.
_KNOWN_IDENTITY_COLUMNS = frozenset(
    {
        "Compound",
        "compound",
        "formula",
        "Formula",
        "mz",
        "MZ",
        "m/z",
        "rt",
        "RT",
        "retentionTime",
        "Adduct",
        "adduct",
        "name",
        "Name",
    }
)

#: Known tracer-atom columns dropped from sample-column auto-detection.
_KNOWN_ATOM_COLUMNS = frozenset(
    {
        "C13",
        "H2",
        "N15",
        "O18",
        "D",
        "S34",
        "Cl37",
    }
)


class LoadMIDTable(_LCMSBlockMixin, IOBlock):
    """Load an AccuCor-style long-format MID table into a :class:`MIDTable`.

    See spec §9 T-LCMS-005 for the 14 acceptance criteria, including
    the user's verbatim cytosine fixture.
    """

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "lcms.load_mid_table"
    name: ClassVar[str] = "Load MID Table"
    subcategory: ClassVar[str] = "io"
    description: ClassVar[str] = (
        "Load a long-format Mass Isotopomer Distribution (MID) table from "
        "AccuCor output (CSV/TSV/XLSX) into a typed MIDTable."
    )

    # ADR-028 §D8: declared extensions consumed by the base-class
    # :meth:`IOBlock._detect_format` helper and (per #1077) by
    # :meth:`BlockRegistry.find_loader`. ``.xls`` aliases to ``xlsx``
    # because pandas reads both via ``read_excel``. Issue #1076.
    supported_extensions: ClassVar[dict[str, str]] = {
        ".csv": "csv",
        ".tsv": "tsv",
        ".xlsx": "xlsx",
        ".xls": "xlsx",
    }

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="mid_table",
            accepted_types=[MIDTable],
            description="Loaded MID table with detected sample columns",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": ["string", "array"],
                "items": {"type": "string"},
                "title": "MID table file(s)",
                "ui_priority": 0,
                "ui_widget": "file_browser",
            },
            "tracer_atoms": {
                "type": "array",
                "items": {"type": "string"},
                "default": ["C13"],
                "title": "Tracer atoms",
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
        """Read MID table file(s) and return a :class:`Collection[MIDTable]`.

        ADR-031 D4: uses :meth:`persist_table` to write the DataFrame
        payload to arrow storage instead of storing a pandas DataFrame
        in the ``user`` dict.

        Accepts ``config["path"]`` as a single string or a list of strings
        (matching the :class:`LoadImage` multi-file pattern).

        Raises:
            FileNotFoundError: If any path does not exist.
            ValueError: If a required column is missing or path config is invalid.
        """
        raw_path = config.get("path")
        if isinstance(raw_path, list):
            paths = [Path(p) for p in raw_path if isinstance(p, str) and p]
        elif isinstance(raw_path, str) and raw_path:
            paths = [Path(raw_path)]
        else:
            raise ValueError("LoadMIDTable: config['path'] must be a non-empty string or list of strings")

        tracer_atoms = [str(atom) for atom in config.get("tracer_atoms", ["C13"])]
        tables: list[MIDTable] = []
        for path in paths:
            if not path.exists():
                raise FileNotFoundError(f"LoadMIDTable: source file not found: {path}")
            # ADR-028 §D8 / #1076: resolve format via the declared ClassVar.
            file_format = self._detect_format(path)
            if file_format is None:
                raise ValueError(f"LoadMIDTable: unsupported file format: {path.suffix}")
            frame = _read_table(path, file_format=file_format, sheet_name=config.get("sheet_name"))
            compound_column = _find_compound_column(frame.columns)
            if compound_column is None:
                raise ValueError("LoadMIDTable requires a 'Compound' or 'compound' column")
            sample_columns = _detect_sample_columns(
                frame.columns,
                tracer_atoms=tracer_atoms,
            )
            if not sample_columns:
                raise ValueError("LoadMIDTable could not detect any sample columns")

            # ADR-031 D4: persist to arrow storage instead of storing
            # pandas DataFrame in user dict.
            storage_ref = None
            if output_dir:
                import pyarrow as pa

                arrow_table = pa.Table.from_pandas(frame)
                storage_ref = self.persist_table(arrow_table, output_dir)

            table = MIDTable(
                columns=[str(col) for col in frame.columns],
                row_count=len(frame),
                schema={str(col): str(dtype) for col, dtype in frame.dtypes.items()},
                meta=MIDTable.Meta(
                    tracer_atoms=tracer_atoms,
                    sample_columns=sample_columns,
                    corrected=True,
                    correction_tool="AccuCor",
                ),
                storage_ref=storage_ref,
            )
            # ADR-031: no longer store pandas_df in user dict.
            tables.append(table)
        return Collection(items=tables, item_type=MIDTable)

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Not supported — use :class:`SaveTable` for output."""
        raise NotImplementedError("T-LCMS-005 LoadMIDTable is direction='input'; use SaveTable to write.")


def _read_table(path: Path, *, file_format: str, sheet_name: str | int | None) -> pd.DataFrame:
    """Read an MID table file using the format identifier resolved from
    :attr:`LoadMIDTable.supported_extensions` (#1076)."""
    import pandas as pd

    if file_format == "csv":
        return pd.read_csv(path)
    if file_format == "tsv":
        return pd.read_csv(path, sep="\t")
    if file_format == "xlsx":
        return pd.read_excel(path, sheet_name=0 if sheet_name is None else sheet_name)
    raise ValueError(f"LoadMIDTable: unsupported file format: {file_format}")


def _find_compound_column(columns: pd.Index) -> str | None:
    for candidate in ("Compound", "compound"):
        if candidate in columns:
            return candidate
    return None


def _detect_sample_columns(
    columns: pd.Index,
    *,
    tracer_atoms: list[str],
) -> list[str]:
    exclude = set(_KNOWN_IDENTITY_COLUMNS) | set(_KNOWN_ATOM_COLUMNS) | set(tracer_atoms)
    return [str(column) for column in columns if str(column) not in exclude]
