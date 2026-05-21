from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from scistudio_blocks_lcms.external.elmaven_block import (
    ElMAVENBlock,
    _classify_export,
    _collect_elmaven_outputs,
    _prepare_elmaven_exchange,
    _resolve_command,
    _resolve_exchange_dir,
)
from scistudio_blocks_lcms.types import MIDTable, MSRawFile, PeakTable

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection


def test_elmaven_block_class_config() -> None:
    block = ElMAVENBlock()
    assert block.app_command == "elmaven"
    assert block.output_patterns == ["*.csv", "*.tsv", "*.xlsx"]
    assert block.input_ports[0].accepted_types == [MSRawFile]
    assert block.output_ports[0].accepted_types == [PeakTable]
    assert block.output_ports[1].accepted_types == [MIDTable]


def test_elmaven_classify_export_peak_vs_mid(tmp_path: Path) -> None:
    peak_path = tmp_path / "peak.csv"
    peak_path.write_text("compound,medMz\nfoo,100.0\n", encoding="utf-8")
    mid_path = tmp_path / "mid.csv"
    mid_path.write_text("Compound,C13,S1\nfoo,0,1.0\n", encoding="utf-8")

    assert _classify_export(peak_path) == "peak_table"
    assert _classify_export(mid_path) == "mid_table"


def test_resolve_exchange_dir_with_project_dir(tmp_path: Path) -> None:
    """Exchange dir falls back to project_dir/data/exchange/block_id."""
    config = BlockConfig(params={"project_dir": str(tmp_path), "block_id": "blk-1"})
    result = _resolve_exchange_dir(config, prefix="scistudio_elmaven_")
    assert result == tmp_path / "data" / "exchange" / "blk-1"
    assert (result / "inputs").is_dir()
    assert (result / "outputs").is_dir()


def test_resolve_exchange_dir_with_explicit(tmp_path: Path) -> None:
    """Explicit exchange_dir config takes priority."""
    explicit = tmp_path / "my_exchange"
    config = BlockConfig(params={"exchange_dir": str(explicit)})
    result = _resolve_exchange_dir(config, prefix="scistudio_elmaven_")
    assert result == explicit


def test_resolve_command_default() -> None:
    config = BlockConfig(params={})
    result = _resolve_command(config, app_command="elmaven", override_key="elmaven_path")
    assert result == ["elmaven"]


def test_resolve_command_override() -> None:
    config = BlockConfig(params={"elmaven_path": "/usr/bin/el-maven"})
    result = _resolve_command(config, app_command="elmaven", override_key="elmaven_path")
    assert result == ["/usr/bin/el-maven"]


def test_prepare_elmaven_exchange_writes_manifest(tmp_path: Path) -> None:
    """Manifest is written with input file paths."""
    import json

    exchange = tmp_path / "exchange"
    exchange.mkdir()
    (exchange / "inputs").mkdir()
    (exchange / "outputs").mkdir()

    raw1 = tmp_path / "sample1.mzXML"
    raw1.write_text("<mzXML/>", encoding="utf-8")
    raw_paths = [str(raw1)]

    config = BlockConfig(params={"some_key": "some_val"})
    _prepare_elmaven_exchange(raw_paths, exchange, tool_name="lcms.elmaven", config=config)

    manifest = json.loads((exchange / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["tool"] == "lcms.elmaven"
    assert manifest["input_files"] == raw_paths
    assert manifest["output_dir"] == str(exchange / "outputs")


def test_collect_elmaven_outputs_empty() -> None:
    """Empty output_files produces empty collections."""
    result = _collect_elmaven_outputs([])
    assert len(result["peak_table"]) == 0
    assert len(result["mid_table"]) == 0


def test_run_passes_raw_paths_as_launch_args(tmp_path: Path) -> None:
    """run() must forward raw file paths as launch_args to _run_external_app."""
    raw1 = tmp_path / "sample1.mzXML"
    raw2 = tmp_path / "sample2.mzML"
    raw1.write_text("<mzXML/>", encoding="utf-8")
    raw2.write_text("<mzML/>", encoding="utf-8")

    raw_files = Collection(
        items=[
            MSRawFile(file_path=raw1, meta=MSRawFile.Meta(format="mzXML")),
            MSRawFile(file_path=raw2, meta=MSRawFile.Meta(format="mzML")),
        ],
        item_type=MSRawFile,
    )

    captured_kwargs: dict = {}

    def fake_run_external_app(_block, **kwargs):  # type: ignore[no-untyped-def]
        captured_kwargs.update(kwargs)
        return []  # no output files

    with patch(
        "scistudio_blocks_lcms.external.elmaven_block._run_external_app",
        side_effect=fake_run_external_app,
    ):
        ElMAVENBlock().run({"raw_files": raw_files}, BlockConfig(params={}))

    assert "launch_args" in captured_kwargs, "launch_args not passed to _run_external_app"
    # Paths must be resolved to absolute so they survive cwd changes in the bridge.
    assert captured_kwargs["launch_args"] == [str(raw1.resolve()), str(raw2.resolve())]


def test_run_resolves_relative_paths_to_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Relative file_path values must be resolved to absolute before launch."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    raw = data_dir / "sample.mzML"
    raw.write_text("<mzML/>", encoding="utf-8")

    # Store a *relative* path in the MSRawFile (simulates LoadMzMLFiles with relative config).
    monkeypatch.chdir(tmp_path)
    relative_path = Path("data/sample.mzML")

    raw_files = Collection(
        items=[MSRawFile(file_path=relative_path, meta=MSRawFile.Meta(format="mzML"))],
        item_type=MSRawFile,
    )

    captured_kwargs: dict = {}

    def fake_run_external_app(_block, **kwargs):  # type: ignore[no-untyped-def]
        captured_kwargs.update(kwargs)
        return []

    with patch(
        "scistudio_blocks_lcms.external.elmaven_block._run_external_app",
        side_effect=fake_run_external_app,
    ):
        ElMAVENBlock().run({"raw_files": raw_files}, BlockConfig(params={}))

    launch_args = captured_kwargs["launch_args"]
    assert len(launch_args) == 1
    assert Path(launch_args[0]).is_absolute(), f"Expected absolute path, got: {launch_args[0]}"
    assert launch_args[0] == str(raw.resolve())


@pytest.mark.skipif(shutil.which("elmaven") is None, reason="ElMAVEN not installed")
def test_elmaven_end_to_end_launch_and_collect(tmp_path: Path) -> None:
    """Full end-to-end test -- only runs when ElMAVEN is actually installed."""
    raw_path = tmp_path / "sample.mzML"
    raw_path.write_text("<mzML />", encoding="utf-8")

    raw = MSRawFile(file_path=raw_path, meta=MSRawFile.Meta(format="mzML"))
    result = ElMAVENBlock().run(
        {"raw_files": Collection(items=[raw], item_type=MSRawFile)},
        BlockConfig(params={"elmaven_path": "elmaven"}),
    )

    assert "peak_table" in result
    assert "mid_table" in result
