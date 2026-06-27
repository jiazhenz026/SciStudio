"""Alpha Task-2 Case 5: R CodeBlock end-to-end (load DataFrame -> R script -> save).

Runs a real R CodeBlock through file exchange: a DataFrame input is
materialised to ``inputs/table/*.csv``; the R script adds a derived
column (``scaled = value * 10``) and writes ``outputs/result/*.csv``;
the runtime reconstructs the output DataFrame.

Requires ``Rscript`` on PATH (skipped otherwise / in CI). The R/Quarto
backend injects ``SCISTUDIO_INPUTS_DIR`` / ``SCISTUDIO_OUTPUTS_DIR`` so
the script needs no FIND-F workaround.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pyarrow as pa
import pytest

from scistudio.blocks.code.code_block import CodeBlock
from scistudio.blocks.io.loaders.load_data import LoadData
from scistudio.blocks.io.savers.save_data import SaveData
from scistudio.blocks.registry import BlockRegistry, _spec_from_class
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame

pytestmark = pytest.mark.skipif(shutil.which("Rscript") is None, reason="requires Rscript on PATH")

R_SCRIPT = """\
inputs <- Sys.getenv("SCISTUDIO_INPUTS_DIR")
outputs <- Sys.getenv("SCISTUDIO_OUTPUTS_DIR")
in_files <- list.files(file.path(inputs, "table"), pattern = "\\\\.csv$", full.names = TRUE)
out_dir <- file.path(outputs, "result")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
for (src in in_files) {
  df <- read.csv(src)
  df$scaled <- df$value * 10
  write.csv(df, file.path(out_dir, basename(src)), row.names = FALSE)
}
"""


def test_r_codeblock_adds_scaled_column(tmp_path: Path) -> None:
    project = tmp_path
    (project / "scripts").mkdir()
    (project / "scripts" / "process_table.R").write_text(R_SCRIPT, encoding="utf-8")

    table = pa.table({"id": [1, 2, 3], "value": [1.0, 2.0, 3.0]})
    src = DataFrame(columns=["id", "value"], row_count=3, data=table)

    # Minimal hermetic registry (no plugin scan) to avoid the global type
    # registry shared with the rest of the -n auto suite.
    reg = BlockRegistry()
    reg._register_spec(_spec_from_class(LoadData, source="alpha-suite"))
    reg._register_spec(_spec_from_class(SaveData, source="alpha-suite"))

    block = CodeBlock(
        config={
            "params": {
                "project_dir": str(project),
                "script_path": "scripts/process_table.R",
                "interpreter_mode": "existing",
                "interpreter_path": shutil.which("Rscript"),
                "exchange_root": "exchange",
                "block_id": "alpha-r",
                "run_id": "run-1",
                "inputs": [{"name": "table", "direction": "input", "data_type": "DataFrame", "extension": ".csv"}],
                "outputs": [{"name": "result", "direction": "output", "data_type": "DataFrame", "extension": ".csv"}],
                "registry": reg,
            }
        }
    )

    outputs = block.run({"table": Collection([src])}, block.config)

    result = outputs["result"][0]
    assert isinstance(result, DataFrame)
    out_table = result.get_in_memory_data()
    cols = out_table.column_names
    assert "scaled" in cols, f"expected a 'scaled' column, got {cols}"
    scaled = out_table.column("scaled").to_pylist()
    assert scaled == [10.0, 20.0, 30.0]
