"""Tests for ``scistudio storage`` (#1983).

``gc`` is destructive, so the preview/apply split is the important contract:
without ``--apply`` nothing may be removed.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from scistudio.cli.main import app
from scistudio.core.lineage.record import (
    BlockExecutionRecord,
    BlockIORow,
    DataObjectRow,
    RunRecord,
)
from scistudio.core.lineage.store import LineageStore

runner = CliRunner()


def _project(tmp_path: Path) -> Path:
    (tmp_path / ".scistudio").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _artifact(root: Path, block: str, name: str, payload: bytes) -> Path:
    store_dir = root / "data" / "zarr" / "wf" / block / f"{name}.zarr"
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / "chunk").write_bytes(payload)
    return store_dir


def _stamp(path: Path, when: str) -> None:
    """Place *path* on the timeline of the run that wrote it."""
    stamp = datetime.fromisoformat(when).timestamp()
    for entry in sorted(path.rglob("*"), reverse=True):
        os.utime(entry, (stamp, stamp))
    os.utime(path, (stamp, stamp))


def _seed(root: Path, *, old: Path, newer: Path) -> None:
    store = LineageStore(str(root / ".scistudio" / "lineage.db"))
    for run_id, started_at, object_id, path in (
        ("run-old", "2026-06-10T00:00:00", "obj-old", old),
        ("run-new", "2026-06-11T00:00:00", "obj-new", newer),
    ):
        store.insert_run(
            RunRecord(
                run_id=run_id,
                workflow_id="wf",
                workflow_yaml_snapshot="",
                started_at=started_at,
                status="completed",
                environment_snapshot={},
            )
        )
        store.insert_block_execution(
            BlockExecutionRecord(
                block_execution_id=f"be-{run_id}",
                run_id=run_id,
                block_id="load",
                block_type="T",
                block_version="1",
                block_config_resolved={},
                started_at=started_at,
                termination="completed",
            )
        )
        store.upsert_data_object(
            DataObjectRow(
                object_id=object_id,
                type_name="Image",
                wire_payload={"metadata": {"backend": "zarr", "path": str(path)}},
                created_at=started_at,
                backend="zarr",
                storage_path=str(path),
                produced_by_execution=f"be-{run_id}",
            )
        )
        store.insert_block_io(
            BlockIORow(
                block_execution_id=f"be-{run_id}",
                direction="output",
                port_name="out",
                object_id=object_id,
                position=0,
            )
        )
        _stamp(path, started_at)
    store.close()


def test_gc_previews_without_deleting(tmp_path: Path) -> None:
    root = _project(tmp_path)
    old = _artifact(root, "load", "old", b"o" * 4096)
    newer = _artifact(root, "load", "new", b"n" * 1024)
    _seed(root, old=old, newer=newer)

    result = runner.invoke(app, ["storage", "gc", "--project", str(root)])

    assert result.exit_code == 0, result.output
    assert "Preview only" in result.output
    assert "run-new" in result.output
    assert old.exists()
    assert newer.exists()


def test_gc_apply_removes_superseded_artifacts(tmp_path: Path) -> None:
    root = _project(tmp_path)
    old = _artifact(root, "load", "old", b"o" * 4096)
    newer = _artifact(root, "load", "new", b"n" * 1024)
    _seed(root, old=old, newer=newer)

    result = runner.invoke(app, ["storage", "gc", "--project", str(root), "--apply"])

    assert result.exit_code == 0, result.output
    assert "Removed 1 artifacts" in result.output
    assert not old.exists()
    assert newer.exists()


def test_gc_rejects_a_non_project_directory(tmp_path: Path) -> None:
    result = runner.invoke(app, ["storage", "gc", "--project", str(tmp_path)])

    assert result.exit_code == 1
    assert "Not a SciStudio project" in result.output


def test_gc_exits_nonzero_when_blocked(tmp_path: Path) -> None:
    """An empty lineage DB must not be read as "everything is reclaimable"."""
    root = _project(tmp_path)
    _artifact(root, "load", "a", b"a" * 64)
    LineageStore(str(root / ".scistudio" / "lineage.db")).close()

    result = runner.invoke(app, ["storage", "gc", "--project", str(root)])

    assert result.exit_code == 1
    assert "records no runs" in result.output


def test_usage_reports_recursive_directory_sizes(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _artifact(root, "load", "a", b"a" * 8192)

    result = runner.invoke(app, ["storage", "usage", "--project", str(root)])

    assert result.exit_code == 0, result.output
    assert "wf" in result.output
    assert "TOTAL" in result.output
    # A directory-inode-size report would have rendered as bytes, not KB.
    assert "KB" in result.output
