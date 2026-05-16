"""T-ECA-203: unit tests for the 7 inspection tools (post-ADR-040)."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import pytest

from scieasy.ai.agent.mcp import _context, tools_inspection


def _run(coro):
    return asyncio.run(coro)


@dataclass
class _StubRuntime:
    block_registry: object = field(default_factory=object)
    type_registry: object = field(default_factory=object)
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    _project_dir: Path | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@pytest.fixture
def ctx(tmp_path: Path) -> Iterator[_StubRuntime]:
    runtime = _StubRuntime(_project_dir=tmp_path)
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


_WF_YAML = """\
workflow:
  id: test_wf
  version: 1.0.0
  nodes:
    - id: b1
      block_type: LoadData
      config:
        params:
          backend: csv
  edges: []
"""


# --- get_block_output ------------------------------------------------------


def test_get_block_output_unknown_run_raises(ctx: _StubRuntime) -> None:
    with pytest.raises(KeyError):
        _run(tools_inspection.get_block_output("nope", "b1", "out"))


def test_get_block_output_happy(ctx: _StubRuntime) -> None:
    class _Sched:
        _block_outputs: ClassVar[dict[str, Any]] = {
            "b1": {
                "out": {
                    "backend": "filesystem",
                    "path": "/x",
                    "metadata": {"type_chain": ["DataObject", "Array"]},
                }
            }
        }

    class _Run:
        scheduler = _Sched()

    ctx.workflow_runs["r1"] = _Run()
    result = _run(tools_inspection.get_block_output("r1", "b1", "out"))
    assert result.type.type_name == "Array"


# --- inspect_data ----------------------------------------------------------


def test_inspect_data_missing_file(ctx: _StubRuntime, tmp_path: Path) -> None:
    ref = {"backend": "filesystem", "path": str(tmp_path / "does_not_exist.bin")}
    out = _run(tools_inspection.inspect_data(ref))
    assert out.size == 0


def test_inspect_data_real_file(ctx: _StubRuntime, tmp_path: Path) -> None:
    p = tmp_path / "data.txt"
    p.write_text("hello", encoding="utf-8")
    out = _run(tools_inspection.inspect_data({"backend": "filesystem", "path": str(p)}))
    assert out.size == 5


# --- preview_data ----------------------------------------------------------


def test_preview_data_text(ctx: _StubRuntime, tmp_path: Path) -> None:
    p = tmp_path / "note.txt"
    p.write_text("hello world", encoding="utf-8")
    out = _run(tools_inspection.preview_data({"backend": "filesystem", "path": str(p)}, "text"))
    assert out.fmt == "text"
    assert out.payload["content"] == "hello world"


def test_preview_data_dataframe_csv(ctx: _StubRuntime, tmp_path: Path) -> None:
    p = tmp_path / "table.csv"
    p.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    out = _run(tools_inspection.preview_data({"backend": "filesystem", "path": str(p)}, "table"))
    assert out.fmt == "table"
    assert "a" in out.payload["columns"]


def test_preview_data_array_thumbnail(ctx: _StubRuntime, tmp_path: Path) -> None:
    pytest.importorskip("zarr")
    import numpy as np
    import zarr

    zarr_path = tmp_path / "big.zarr"
    z = zarr.open(str(zarr_path), mode="w", shape=(1024, 1024), chunks=(128, 128), dtype="f4")
    z[:] = np.arange(1024 * 1024, dtype="f4").reshape(1024, 1024)
    out = _run(tools_inspection.preview_data({"backend": "zarr", "path": str(zarr_path)}, "png_base64"))
    assert out.fmt == "png_base64"
    base64.b64decode(out.payload["data"])
    thumb = out.payload["thumbnail_shape"]
    assert thumb[0] <= 256 and thumb[1] <= 256


def test_preview_data_tiff_oversize_does_not_load_full_page(
    ctx: _StubRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("tifffile")
    import numpy as np
    import tifffile

    tif_path = tmp_path / "img.tif"
    tifffile.imwrite(str(tif_path), np.ones((64, 64), dtype="uint8"), compression="zlib")
    monkeypatch.setattr(tools_inspection, "_MAX_PREVIEW_BYTES", 1000)

    out = _run(tools_inspection.preview_data({"backend": "filesystem", "path": str(tif_path)}, "png_base64"))
    assert out.fmt == "skipped"
    assert out.payload["reason"] == "tiff_page_exceeds_cap_and_not_memmappable"
    assert out.truncated is True


def test_preview_data_missing_path_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _run(tools_inspection.preview_data({"backend": "filesystem", "path": str(tmp_path / "nope.csv")}, "table"))


# --- get_lineage -----------------------------------------------------------


def test_get_lineage_no_store_returns_empty(ctx: _StubRuntime) -> None:
    out = _run(tools_inspection.get_lineage({"backend": "filesystem", "path": "/x"}))
    assert out.nodes == []
    assert out.edges == []


def test_get_lineage_with_object_id(ctx: _StubRuntime) -> None:
    out = _run(tools_inspection.get_lineage({"metadata": {"framework": {"object_id": "obj-1"}}}))
    assert hasattr(out, "nodes")


# --- get_block_config ------------------------------------------------------


def test_get_block_config_happy(ctx: _StubRuntime, tmp_path: Path) -> None:
    p = tmp_path / "wf.yaml"
    p.write_text(_WF_YAML, encoding="utf-8")
    out = _run(tools_inspection.get_block_config(str(p), "b1"))
    assert out.block_id == "b1"
    assert out.type == "LoadData"


def test_get_block_config_unknown_block_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    p = tmp_path / "wf.yaml"
    p.write_text(_WF_YAML, encoding="utf-8")
    with pytest.raises(KeyError):
        _run(tools_inspection.get_block_config(str(p), "missing"))


# --- update_block_config ---------------------------------------------------


def test_update_block_config_preserves_comments(ctx: _StubRuntime, tmp_path: Path) -> None:
    p = tmp_path / "wf.yaml"
    p.write_text(
        """\
# top-level comment
workflow:
  id: test_wf
  nodes:
    - id: b1
      block_type: LoadData
      config:
        # inline comment
        params:
          backend: csv
  edges: []
""",
        encoding="utf-8",
    )
    out = _run(tools_inspection.update_block_config(str(p), "b1", {"params": {"backend": "parquet"}}))
    assert out.block_id == "b1"
    text = p.read_text(encoding="utf-8")
    assert "# top-level comment" in text
    assert "parquet" in text


def test_update_block_config_missing_file_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _run(tools_inspection.update_block_config(str(tmp_path / "nope.yaml"), "b1", {}))


# --- get_block_logs --------------------------------------------------------


def test_get_block_logs_no_logs_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        _run(tools_inspection.get_block_logs("run-x", "block-y"))


def test_get_block_logs_happy(ctx: _StubRuntime, tmp_path: Path) -> None:
    logs = tmp_path / "logs" / "run-1"
    logs.mkdir(parents=True)
    (logs / "b1.stdout").write_text("hello\n", encoding="utf-8")
    (logs / "b1.stderr").write_text("warn\n", encoding="utf-8")
    out = _run(tools_inspection.get_block_logs("run-1", "b1"))
    assert "hello" in out.stdout
    assert "warn" in out.stderr
