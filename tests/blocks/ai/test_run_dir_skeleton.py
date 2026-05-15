"""Tests for RunDir (ADR-035 §3.2, §3.4) — Phase 2A implementation.

Originally a skeleton (xfail) file from the Phase 1 scaffold; flipped
to real tests by I35a per the test plan in ``run_dir.py``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scieasy.blocks.ai.run_dir import RunDir
from scieasy.blocks.base.ports import OutputPort
from scieasy.core.types.artifact import Artifact
from scieasy.core.types.dataframe import DataFrame
from scieasy.core.types.text import Text


def test_run_dir_class_imports() -> None:
    """Smoke test — class is importable."""
    assert RunDir is not None


def test_init_computes_path_correctly(tmp_path: Path) -> None:
    rd = RunDir(tmp_path, "abc-123")
    assert rd.path == tmp_path / ".scieasy" / "ai-block-runs" / "abc-123"
    # ADR-038 §5.2 rename: the Python attribute is ``block_execution_id``.
    assert rd.block_execution_id == "abc-123"
    assert rd.project_dir == tmp_path


def test_init_rejects_block_execution_id_with_separators(tmp_path: Path) -> None:
    """Renamed from ``test_init_rejects_run_id_with_separators`` per ADR-038 §5.2."""
    with pytest.raises(ValueError, match="path separator"):
        RunDir(tmp_path, "foo/bar")
    with pytest.raises(ValueError, match="path separator"):
        RunDir(tmp_path, "")
    if os.sep != "/":
        # On Windows the OS separator is also rejected.
        with pytest.raises(ValueError, match="path separator"):
            RunDir(tmp_path, f"a{os.sep}b")


def test_create_makes_dir_and_signals_subdir(tmp_path: Path) -> None:
    rd = RunDir(tmp_path, "abc")
    rd.create()
    assert rd.path.is_dir()
    assert (rd.path / "signals").is_dir()


def test_create_raises_on_collision(tmp_path: Path) -> None:
    rd = RunDir(tmp_path, "abc")
    rd.create()
    with pytest.raises(FileExistsError):
        rd.create()


def test_write_manifest_basic_shape(tmp_path: Path) -> None:
    rd = RunDir(tmp_path, "run1")
    rd.create()
    artifact = Artifact(file_path=tmp_path / "input.czi", mime_type="application/octet-stream")
    output_port = OutputPort(name="metadata", accepted_types=[DataFrame])
    manifest_path = rd.write_manifest(
        block_name="extract_metadata",
        block_type="AIBlock",
        user_prompt="Extract metadata.",
        inputs={"files": [artifact]},
        outputs=[output_port],
        deadline_iso="2026-05-13T22:30:45Z",
        output_paths={"metadata": "./results/metadata.csv"},
    )

    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["block"]["name"] == "extract_metadata"
    assert data["block"]["type"] == "AIBlock"
    assert data["block"]["run_id"] == "run1"
    assert data["user_prompt"] == "Extract metadata."
    assert "files" in data["inputs"]
    assert data["inputs"]["files"][0]["type_chain"][0] == "Artifact"
    assert data["outputs"]["metadata"]["expected_path"] == "./results/metadata.csv"
    assert data["outputs"]["metadata"]["expected_type"] == "DataFrame"
    assert data["completion"]["deadline"] == "2026-05-13T22:30:45Z"
    assert "Call mcp__scieasy__finish_ai_block" in data["completion"]["primary"]


def test_write_manifest_records_paths_verbatim(tmp_path: Path) -> None:
    """Input paths must NOT be rewritten / symlinked / copied."""
    rd = RunDir(tmp_path, "run2")
    rd.create()
    weird_path = tmp_path / "subdir with spaces" / "file_2026-04-01.czi"
    weird_path.parent.mkdir()
    weird_path.write_bytes(b"data")
    artifact = Artifact(file_path=weird_path, mime_type="x/y")
    rd.write_manifest(
        block_name="b",
        block_type="AIBlock",
        user_prompt="p",
        inputs={"files": [artifact]},
        outputs=[],
        deadline_iso="2026-05-13T22:30:45Z",
    )
    data = json.loads((rd.path / "manifest.json").read_text(encoding="utf-8"))
    assert data["inputs"]["files"][0]["path"] == str(weird_path)


def test_write_manifest_atomic(tmp_path: Path) -> None:
    """tempfile + os.replace — never a partial file on disk.

    We can't kill mid-write portably; instead assert the file appears in
    one shot (no `.tmp` orphan beside it) and that no other files exist
    in the dir except the manifest + signals.
    """
    rd = RunDir(tmp_path, "run3")
    rd.create()
    rd.write_manifest(
        block_name="b",
        block_type="AIBlock",
        user_prompt="p",
        inputs={},
        outputs=[],
        deadline_iso="d",
    )
    # No leftover .tmp files.
    leftovers = [p for p in rd.path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []
    # Manifest is valid JSON (was not partially written).
    json.loads((rd.path / "manifest.json").read_text(encoding="utf-8"))


def test_write_manifest_default_expected_path(tmp_path: Path) -> None:
    """Output port without expected_path → ./{block_name}_outputs/{port}.{ext}."""
    rd = RunDir(tmp_path, "run4")
    rd.create()
    text_port = OutputPort(name="report", accepted_types=[Text])
    rd.write_manifest(
        block_name="my_block",
        block_type="AIBlock",
        user_prompt="p",
        inputs={},
        outputs=[text_port],
        deadline_iso="d",
    )
    data = json.loads((rd.path / "manifest.json").read_text(encoding="utf-8"))
    assert data["outputs"]["report"]["expected_path"] == "./my_block_outputs/report.txt"


def test_write_manifest_dataframe_default_extension(tmp_path: Path) -> None:
    rd = RunDir(tmp_path, "run5")
    rd.create()
    df_port = OutputPort(name="m", accepted_types=[DataFrame])
    rd.write_manifest(
        block_name="b",
        block_type="AIBlock",
        user_prompt="p",
        inputs={},
        outputs=[df_port],
        deadline_iso="d",
    )
    data = json.loads((rd.path / "manifest.json").read_text(encoding="utf-8"))
    assert data["outputs"]["m"]["expected_path"].endswith(".csv")


def test_write_manifest_inmemory_input_records_no_path(tmp_path: Path) -> None:
    """In-memory DataObject (no storage_ref / file_path) records ``path: null``.

    Phase 2A behaviour: we log a warning and emit a placeholder so the
    agent at least sees the type. Actual materialization is the engine's
    ``_auto_flush`` job before run() is called; this test asserts the
    diagnostic path doesn't crash.
    """
    rd = RunDir(tmp_path, "run6")
    rd.create()
    # Plain Text without file_path / storage_ref.
    text = Text(content="hello", format="plain")
    rd.write_manifest(
        block_name="b",
        block_type="AIBlock",
        user_prompt="p",
        inputs={"prompt": [text]},
        outputs=[],
        deadline_iso="d",
    )
    data = json.loads((rd.path / "manifest.json").read_text(encoding="utf-8"))
    assert data["inputs"]["prompt"][0]["path"] is None
    assert "Text" in data["inputs"]["prompt"][0]["type_chain"]


def test_mcp_signal_path_under_signals_dir(tmp_path: Path) -> None:
    rd = RunDir(tmp_path, "x")
    assert rd.mcp_signal_path() == rd.path / "signals" / "finish_ai_block.json"


def test_mark_done_signal_path_under_signals_dir(tmp_path: Path) -> None:
    rd = RunDir(tmp_path, "x")
    assert rd.mark_done_signal_path() == rd.path / "signals" / "mark_done.json"


def test_copy_transcript_basic(tmp_path: Path) -> None:
    rd = RunDir(tmp_path, "x")
    rd.create()
    src = tmp_path / "transcript.log"
    src.write_text("agent log", encoding="utf-8")
    dest = rd.copy_transcript(src)
    assert dest == rd.path / "transcript.log"
    assert dest.read_text(encoding="utf-8") == "agent log"


def test_copy_transcript_missing_source_logs_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    rd = RunDir(tmp_path, "x")
    rd.create()
    missing = tmp_path / "does-not-exist.log"
    with caplog.at_level("WARNING"):
        dest = rd.copy_transcript(missing)
    assert dest == rd.path / "transcript.log"
    assert not dest.exists()
    assert any("transcript source missing" in r.message for r in caplog.records)


# NOTE: concurrent-write atomicity is NOT a contract of write_manifest.
# Each AI Block run owns its own RunDir (run_id is unique per run); the
# atomic-write guarantee only matters for a single writer that may crash
# mid-write. On Windows ``os.replace`` of a destination held open by a
# concurrent reader/writer raises PermissionError, so a multi-writer test
# would be platform-specific. The test_write_manifest_atomic test above
# covers the single-writer guarantee.
