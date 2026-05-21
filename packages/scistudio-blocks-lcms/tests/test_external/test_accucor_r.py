from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from scistudio_blocks_lcms.external.accucor_r import AccuCorR
from scistudio_blocks_lcms.types import MIDTable, PeakTable, SampleMetadata

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.code.code_block import CodeBlock
from scistudio.core.types.collection import Collection


def _peak_table() -> PeakTable:
    df = pd.DataFrame({"compound": ["glucose"], "intensity": [100.0]})
    table = PeakTable(
        columns=list(df.columns),
        row_count=len(df),
        schema={col: str(dtype) for col, dtype in df.dtypes.items()},
        meta=PeakTable.Meta(source="ElMAVEN"),
    )
    table.user["pandas_df"] = df
    return table


def _sample_metadata() -> SampleMetadata:
    df = pd.DataFrame({"sample_id": ["S1"], "group": ["UL"]})
    table = SampleMetadata(
        columns=list(df.columns),
        row_count=len(df),
        schema={col: str(dtype) for col, dtype in df.dtypes.items()},
        meta=SampleMetadata.Meta(sample_id_column="sample_id"),
    )
    table.user["pandas_df"] = df
    return table


def test_accucor_r_subclasses_codeblock_language_r() -> None:
    block = AccuCorR()
    assert issubclass(AccuCorR, CodeBlock)
    assert block.language == "r"
    assert block.mode == "script"
    assert block.output_ports[0].accepted_types == [MIDTable]


def test_accucor_r_default_script_path_resolves() -> None:
    path = Path(AccuCorR()._resolve_script_path(BlockConfig(params={})))
    assert path.exists()
    assert path.name == "accucor.R"


def test_accucor_r_override_script_path_accepted(tmp_path: Path) -> None:
    override = tmp_path / "override.R"
    override.write_text("run_accucor <- function(inputs, params) list(mid_table = '')", encoding="utf-8")
    path = AccuCorR()._resolve_script_path(BlockConfig(params={"accucor_script_path": str(override)}))
    assert path == str(override)


@pytest.mark.requires_r
def test_accucor_r_run_wraps_mid_table(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out_path = tmp_path / "mid.csv"
    pd.DataFrame({"Compound": ["glucose"], "C13": [0], "S1": [1.0]}).to_csv(out_path, index=False)

    def fake_run(self: CodeBlock, inputs: dict, config: BlockConfig) -> dict:
        assert config.get("entry_function") == "run_accucor"
        assert Path(config.get("script_path")).exists()
        return {"mid_table": str(out_path)}

    monkeypatch.setattr(CodeBlock, "run", fake_run)

    result = AccuCorR().run(
        {
            "peak_table": Collection(items=[_peak_table()], item_type=PeakTable),
            "sample_metadata": Collection(items=[_sample_metadata()], item_type=SampleMetadata),
        },
        BlockConfig(params={"tracer_formula": "C13"}),
    )

    assert len(result["mid_table"]) == 1
    assert result["mid_table"][0].meta.tracer_atoms == ["C13"]
