"""T-ECA-203: unit tests for the 7 inspection tools.

# TODO(#1012): module-level skip during ADR-040 §3.1 FastMCP skeleton
#   phase. The inspection tool bodies are NotImplementedError stubs in
#   S40a; I40a Phase 2a restores behavior. Out of scope per ADR-040
#   §3.1 / phase: 2a I40a. Followup: #1012.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import pytest

pytestmark = pytest.mark.skip(
    reason="S40a skeleton — tool bodies are NotImplementedError stubs. TODO(#1012): I40a Phase 2a restores."
)

from scistudio.ai.agent.mcp import _context, tools_inspection  # noqa: E402


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
def ctx(tmp_path: Path) -> _StubRuntime:
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
        tools_inspection.get_block_output("nope", "b1", "out")


def test_get_block_output_happy(ctx: _StubRuntime) -> None:
    class _Sched:
        _block_outputs: ClassVar[dict[str, Any]] = {
            "b1": {"out": {"backend": "filesystem", "path": "/x", "metadata": {"type_chain": ["DataObject", "Array"]}}}
        }

    class _Run:
        scheduler = _Sched()

    ctx.workflow_runs["r1"] = _Run()
    result = tools_inspection.get_block_output("r1", "b1", "out")
    assert result["type"]["type_name"] == "Array"


# --- inspect_data ----------------------------------------------------------


def test_inspect_data_missing_file(ctx: _StubRuntime, tmp_path: Path) -> None:
    ref = {"backend": "filesystem", "path": str(tmp_path / "does_not_exist.bin")}
    out = tools_inspection.inspect_data(ref)
    assert out["size"] == 0


def test_inspect_data_real_file(ctx: _StubRuntime, tmp_path: Path) -> None:
    p = tmp_path / "data.txt"
    p.write_text("hello", encoding="utf-8")
    out = tools_inspection.inspect_data({"backend": "filesystem", "path": str(p)})
    assert out["size"] == 5


# --- preview_data ----------------------------------------------------------


def test_preview_data_text(ctx: _StubRuntime, tmp_path: Path) -> None:
    p = tmp_path / "note.txt"
    p.write_text("hello world", encoding="utf-8")
    out = tools_inspection.preview_data({"backend": "filesystem", "path": str(p)}, "text")
    assert out["fmt"] == "text"
    assert out["payload"]["content"] == "hello world"


def test_preview_data_dataframe_csv(ctx: _StubRuntime, tmp_path: Path) -> None:
    p = tmp_path / "table.csv"
    p.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    out = tools_inspection.preview_data({"backend": "filesystem", "path": str(p)}, "table")
    assert out["fmt"] == "table"
    assert "a" in out["payload"]["columns"]


def test_preview_data_array_thumbnail(ctx: _StubRuntime, tmp_path: Path) -> None:
    pytest.importorskip("zarr")
    import numpy as np
    import zarr

    # Build a 1024x1024 array; preview should NOT load it all (uses step
    # slicing) and must return a base64 PNG with shape <= 256x256.
    zarr_path = tmp_path / "big.zarr"
    z = zarr.open(str(zarr_path), mode="w", shape=(1024, 1024), chunks=(128, 128), dtype="f4")
    z[:] = np.arange(1024 * 1024, dtype="f4").reshape(1024, 1024)
    out = tools_inspection.preview_data({"backend": "zarr", "path": str(zarr_path)}, "png_base64")
    assert out["fmt"] == "png_base64"
    # Round-trip the base64 to confirm it's well-formed.
    base64.b64decode(out["payload"]["data"])
    thumb = out["payload"]["thumbnail_shape"]
    assert thumb[0] <= 256 and thumb[1] <= 256


def test_preview_data_tiff_oversize_does_not_load_full_page(
    ctx: _StubRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex P1 regression — large TIFF must not call `page.asarray()`.

    Lower ``_MAX_PREVIEW_BYTES`` so even a small TIFF trips the
    oversize branch. The fix in `_preview_array` either succeeds via
    `tifffile.memmap` (uncompressed) or returns a structured "skipped"
    payload — both prove the cap check fires BEFORE the eager
    `page.asarray()` that previously consumed unbounded RAM on
    multi-GB single-IFD TIFFs.
    PR #744 discussion_r3231046699.
    """
    pytest.importorskip("tifffile")
    import numpy as np
    import tifffile

    # Compressed TIFF — tifffile.memmap refuses to map compressed data,
    # so when the page is "too large" the new code returns a structured
    # "skipped" stub rather than blindly calling `page.asarray()`.
    tif_path = tmp_path / "img.tif"
    tifffile.imwrite(str(tif_path), np.ones((64, 64), dtype="uint8"), compression="zlib")
    # Make the 4096-byte page look "oversized" relative to the cap so
    # the new branch executes. Keep the cap above PNG-output sizes for
    # any other tests that might fall through.
    monkeypatch.setattr(tools_inspection, "_MAX_PREVIEW_BYTES", 1000)

    out = tools_inspection.preview_data({"backend": "filesystem", "path": str(tif_path)}, "png_base64")
    # Forbidden outcome: the old path called `page.asarray()` blindly
    # and then raised RuntimeError after PNG encoding. We expect the
    # guard to return a structured "skipped" payload instead.
    assert out["fmt"] == "skipped"
    assert out["payload"]["reason"] == "tiff_page_exceeds_cap_and_not_memmappable"
    assert out["truncated"] is True


def test_preview_data_missing_path_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        tools_inspection.preview_data({"backend": "filesystem", "path": str(tmp_path / "nope.csv")}, "table")


# --- get_lineage -----------------------------------------------------------


def test_get_lineage_no_store_returns_empty(ctx: _StubRuntime) -> None:
    # No MetadataStore installed in tests; should degrade gracefully.
    out = tools_inspection.get_lineage({"backend": "filesystem", "path": "/x"})
    assert out["nodes"] == []
    assert out["edges"] == []


def test_get_lineage_with_object_id(ctx: _StubRuntime) -> None:
    out = tools_inspection.get_lineage({"metadata": {"framework": {"object_id": "obj-1"}}})
    # Still no store; should not raise.
    assert "nodes" in out


# --- get_block_config ------------------------------------------------------


def test_get_block_config_happy(ctx: _StubRuntime, tmp_path: Path) -> None:
    p = tmp_path / "wf.yaml"
    p.write_text(_WF_YAML, encoding="utf-8")
    out = tools_inspection.get_block_config(str(p), "b1")
    assert out["block_id"] == "b1"
    assert out["type"] == "LoadData"


def test_get_block_config_unknown_block_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    p = tmp_path / "wf.yaml"
    p.write_text(_WF_YAML, encoding="utf-8")
    with pytest.raises(KeyError):
        tools_inspection.get_block_config(str(p), "missing")


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
    out = tools_inspection.update_block_config(str(p), "b1", {"params": {"backend": "parquet"}})
    assert out["block_id"] == "b1"
    text = p.read_text(encoding="utf-8")
    assert "# top-level comment" in text  # comments preserved by ruamel
    assert "parquet" in text


def test_update_block_config_missing_file_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        tools_inspection.update_block_config(str(tmp_path / "nope.yaml"), "b1", {})


# --- get_block_logs --------------------------------------------------------


def test_get_block_logs_no_logs_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        tools_inspection.get_block_logs("run-x", "block-y")


def test_get_block_logs_happy(ctx: _StubRuntime, tmp_path: Path) -> None:
    logs = tmp_path / "logs" / "run-1"
    logs.mkdir(parents=True)
    (logs / "b1.stdout").write_text("hello\n", encoding="utf-8")
    (logs / "b1.stderr").write_text("warn\n", encoding="utf-8")
    out = tools_inspection.get_block_logs("run-1", "b1")
    assert "hello" in out["stdout"]
    assert "warn" in out["stderr"]
