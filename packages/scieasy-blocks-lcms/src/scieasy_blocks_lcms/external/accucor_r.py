"""AccuCorR — CodeBlock R runner for the AccuCor natural-abundance corrector.

Skeleton @ c08a885. Per ``docs/specs/phase11-lcms-block-spec.md`` §9
T-LCMS-007 (part 2).

Wraps the bundled ``scripts/accucor.R`` driver via :class:`CodeBlock`'s
R runner (``language="r"``, ``mode="script"``). The R script body is
itself a placeholder under ``external/scripts/accucor.R``; the impl
agent replaces it with the user's vetted AccuCor wrapper script.

Per spec §8 Q-1 the AccuCor R package is a runtime dependency installed
by the user (no auto-install) and the script communicates with the
SciEasy R runner via the standard ``inputs`` / ``params`` /
``result`` contract documented in T-TRK-013.
"""

from __future__ import annotations

import tempfile
from importlib import resources
from pathlib import Path
from typing import Any, ClassVar, cast

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.code.code_block import CodeBlock
from scieasy.core.types.collection import Collection
from scieasy_blocks_lcms._base import _LCMSBlockMixin
from scieasy_blocks_lcms.io.load_mid_table import _detect_sample_columns
from scieasy_blocks_lcms.io.save_table import _to_pandas
from scieasy_blocks_lcms.types import MIDTable, PeakTable, SampleMetadata


class AccuCorR(_LCMSBlockMixin, CodeBlock):
    """Run AccuCor's natural-abundance correction on a peak table.

    See spec §9 T-LCMS-007 for the 9 acceptance criteria. The bundled
    R script lives at
    ``scieasy_blocks_lcms.external.scripts.accucor`` and is resolved
    at run-time via :func:`_resolve_script_path`.
    """

    name: ClassVar[str] = "AccuCor (R)"
    type_name: ClassVar[str] = "lcms.accucor_r"
    subcategory: ClassVar[str] = "external"
    description: ClassVar[str] = (
        "Run the AccuCor R package on a PeakTable to apply natural abundance correction and emit a typed MIDTable."
    )

    language: ClassVar[str] = "r"
    mode: ClassVar[str] = "script"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="peak_table",
            accepted_types=[PeakTable],
            required=True,
            description="Peak table from ElMAVEN (or compatible source)",
        ),
        InputPort(
            name="sample_metadata",
            accepted_types=[SampleMetadata],
            required=True,
            description="Per-sample metadata (group, label, etc.)",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="mid_table",
            accepted_types=[MIDTable],
            description="Natural-abundance-corrected MID table",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "tracer_formula": {
                "type": "string",
                "default": "C13",
                "title": "Tracer formula",
                "ui_priority": 1,
            },
            "resolution": {
                "type": "integer",
                "default": 120000,
                "title": "Mass spec resolution",
                "ui_priority": 2,
            },
            "accucor_script_path": {
                "type": ["string", "null"],
                "default": None,
                "title": "Override path to AccuCor R script (advanced)",
                "ui_priority": 3,
                "ui_widget": "file_browser",
            },
        },
    }

    def _resolve_script_path(self, config: BlockConfig) -> str:
        """Return the absolute path to the AccuCor R script.

        Honours the ``accucor_script_path`` config override; otherwise
        falls back to the bundled ``external/scripts/accucor.R``
        loaded via :mod:`importlib.resources`.
        """
        override = config.get("accucor_script_path")
        if override:
            return str(override)

        bundled = resources.files("scieasy_blocks_lcms.external").joinpath("scripts", "accucor.R")
        with resources.as_file(bundled) as path:
            return str(path)

    def run(
        self,
        inputs: dict[str, Collection],
        config: BlockConfig,
    ) -> dict[str, Collection]:
        """Patch ``script_path`` / ``entry_function`` and delegate.

        Implementation must:

        * call :meth:`_resolve_script_path` and write the result into
          a copy of ``config`` under the ``script_path`` key
        * set ``entry_function="run_accucor"``
        * default ``language="r"`` and ``mode="script"``
        * delegate to :meth:`CodeBlock.run`
        * wrap the resulting CSV path in a :class:`MIDTable` with the
          appropriate ``Meta`` (``corrected=True``,
          ``correction_tool="AccuCor"``, ``tracer_atoms`` from config)
        """
        import pandas as pd

        peak_collection = inputs.get("peak_table")
        metadata_collection = inputs.get("sample_metadata")
        if peak_collection is None or metadata_collection is None:
            raise ValueError("AccuCorR requires 'peak_table' and 'sample_metadata' inputs")

        peak_table = peak_collection[0]
        sample_metadata = metadata_collection[0]
        assert isinstance(peak_table, PeakTable)
        assert isinstance(sample_metadata, SampleMetadata)

        patched_params = dict(config.params)
        patched_params["script_path"] = self._resolve_script_path(config)
        patched_params["entry_function"] = "run_accucor"
        patched_params.setdefault("language", "r")
        patched_params.setdefault("mode", "script")

        with tempfile.TemporaryDirectory(prefix="scieasy_accucor_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            peak_path = tmp_path / "peak_table.csv"
            meta_path = tmp_path / "sample_metadata.csv"
            _to_pandas(peak_table).to_csv(peak_path, index=False)
            _to_pandas(sample_metadata).to_csv(meta_path, index=False)

            try:
                raw_outputs = super().run(
                    cast(Any, {"peak_table": str(peak_path), "sample_metadata": str(meta_path)}),
                    BlockConfig(params=patched_params),
                )
            except FileNotFoundError as exc:
                raise ImportError("AccuCorR requires an Rscript runtime on PATH") from exc

            mid_path_raw = raw_outputs.get("mid_table")
            if not isinstance(mid_path_raw, str):
                raise ValueError("AccuCorR expected the R script to return a 'mid_table' path")

            mid_path = Path(mid_path_raw)
            frame = pd.read_csv(mid_path)
            tracer_formula = str(config.get("tracer_formula", "C13"))
            sample_columns = _detect_sample_columns(
                frame.columns,
                tracer_atoms=[tracer_formula],
                pattern=None,
            )
            if not sample_columns:
                raise ValueError("AccuCorR produced a MID table with no detectable sample columns")

            mid_table = MIDTable(
                columns=[str(column) for column in frame.columns],
                row_count=len(frame),
                schema={str(col): str(dtype) for col, dtype in frame.dtypes.items()},
                meta=MIDTable.Meta(
                    tracer_atoms=[tracer_formula],
                    sample_columns=sample_columns,
                    corrected=True,
                    correction_tool="AccuCor",
                ),
            )
            mid_table.user["pandas_df"] = frame.copy()
            return {"mid_table": Collection(items=[mid_table], item_type=MIDTable)}
