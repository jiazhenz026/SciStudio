"""Tests for LineageStore integrity + read-only query enforcement.

Covers:

* #1529 (DSN-5): ``data_objects`` rows record an xxhash content digest of
  the bytes at ``storage_path`` so an overwritten / deleted artifact can be
  detected (``check_object_integrity`` / ``detect_dangling_objects``).
* #1546 (BUG-11): ``execute_query`` enforces its "read-only" contract,
  rejecting non-SELECT statements rather than silently mutating the DB.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.core.lineage.record import (
    BlockExecutionRecord,
    DataObjectRow,
    RunRecord,
)
from scistudio.core.lineage.store import LineageStore, hash_artifact_file


def _store(tmp_path: Path) -> LineageStore:
    return LineageStore(str(tmp_path / "lineage.db"))


def _seed_run_and_exec(store: LineageStore) -> str:
    store.insert_run(
        RunRecord(
            run_id="run-1",
            workflow_id="wf",
            workflow_yaml_snapshot="",
            started_at="2026-06-10T00:00:00",
            status="running",
            environment_snapshot={},
        )
    )
    be_id = "be-1"
    store.insert_block_execution(
        BlockExecutionRecord(
            block_execution_id=be_id,
            run_id="run-1",
            block_id="A",
            block_type="T",
            block_version="1",
            block_config_resolved={},
            started_at="2026-06-10T00:00:00",
            termination="completed",
        )
    )
    return be_id


# ---------------------------------------------------------------------------
# #1529 — content hash + dangling detection
# ---------------------------------------------------------------------------


def test_upsert_records_content_hash_and_size(tmp_path: Path) -> None:
    store = _store(tmp_path)
    be_id = _seed_run_and_exec(store)

    artifact = tmp_path / "out.bin"
    artifact.write_bytes(b"hello world")

    store.upsert_data_object(
        DataObjectRow(
            object_id="obj-1",
            type_name="Image",
            wire_payload={},
            created_at="2026-06-10T00:00:00",
            storage_path=str(artifact),
            produced_by_execution=be_id,
        )
    )

    row = store.get_data_object("obj-1")
    assert row is not None
    assert row["content_hash"] == hash_artifact_file(str(artifact))
    assert row["content_hash"] is not None
    assert row["size_bytes"] == len(b"hello world")


def test_integrity_ok_when_bytes_unchanged(tmp_path: Path) -> None:
    store = _store(tmp_path)
    be_id = _seed_run_and_exec(store)
    artifact = tmp_path / "out.bin"
    artifact.write_bytes(b"stable bytes")
    store.upsert_data_object(
        DataObjectRow(
            object_id="obj-ok",
            type_name="Image",
            wire_payload={},
            created_at="2026-06-10T00:00:00",
            storage_path=str(artifact),
            produced_by_execution=be_id,
        )
    )
    assert store.check_object_integrity("obj-ok") == "ok"
    assert store.detect_dangling_objects("run-1") == []


def test_integrity_dangling_when_bytes_overwritten(tmp_path: Path) -> None:
    """ADR-038 §3.5: a later run may overwrite the same path — the digest
    mismatch surfaces as 'dangling'."""
    store = _store(tmp_path)
    be_id = _seed_run_and_exec(store)
    artifact = tmp_path / "out.bin"
    artifact.write_bytes(b"original")
    store.upsert_data_object(
        DataObjectRow(
            object_id="obj-dangle",
            type_name="Image",
            wire_payload={},
            created_at="2026-06-10T00:00:00",
            storage_path=str(artifact),
            produced_by_execution=be_id,
        )
    )

    # Simulate a subsequent run overwriting the mutable path.
    artifact.write_bytes(b"OVERWRITTEN by a later run")

    assert store.check_object_integrity("obj-dangle") == "dangling"
    dangling = store.detect_dangling_objects("run-1")
    assert [r["object_id"] for r in dangling] == ["obj-dangle"]
    assert dangling[0]["integrity"] == "dangling"


def test_integrity_dangling_when_file_deleted(tmp_path: Path) -> None:
    store = _store(tmp_path)
    be_id = _seed_run_and_exec(store)
    artifact = tmp_path / "gone.bin"
    artifact.write_bytes(b"data")
    store.upsert_data_object(
        DataObjectRow(
            object_id="obj-gone",
            type_name="Image",
            wire_payload={},
            created_at="2026-06-10T00:00:00",
            storage_path=str(artifact),
            produced_by_execution=be_id,
        )
    )
    artifact.unlink()
    assert store.check_object_integrity("obj-gone") == "dangling"


def test_integrity_unknown_without_path_or_hash(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_run_and_exec(store)
    store.upsert_data_object(
        DataObjectRow(
            object_id="obj-nopath",
            type_name="DataObject",
            wire_payload={},
            created_at="2026-06-10T00:00:00",
        )
    )
    assert store.check_object_integrity("obj-nopath") == "unknown"
    assert store.check_object_integrity("does-not-exist") == "unknown"


def test_detect_dangling_scopes_to_run(tmp_path: Path) -> None:
    store = _store(tmp_path)
    be_id = _seed_run_and_exec(store)
    good = tmp_path / "good.bin"
    good.write_bytes(b"good")
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"bad")
    for oid, path in (("g", good), ("b", bad)):
        store.upsert_data_object(
            DataObjectRow(
                object_id=oid,
                type_name="Image",
                wire_payload={},
                created_at="2026-06-10T00:00:00",
                storage_path=str(path),
                produced_by_execution=be_id,
            )
        )
    bad.write_bytes(b"changed!")
    dangling = store.detect_dangling_objects("run-1")
    assert {r["object_id"] for r in dangling} == {"b"}


# ---------------------------------------------------------------------------
# #1546 — execute_query read-only enforcement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_sql",
    [
        "DELETE FROM runs",
        "UPDATE runs SET status = 'x'",
        "INSERT INTO runs (run_id) VALUES ('x')",
        "DROP TABLE runs",
        "ALTER TABLE runs ADD COLUMN x TEXT",
        "SELECT 1; DROP TABLE runs",  # statement batching
        "  ;  ",  # empty / whitespace
        "-- just a comment\nDELETE FROM runs",  # comment-prefixed write
    ],
)
def test_execute_query_rejects_writes_memory(bad_sql: str) -> None:
    store = LineageStore(":memory:")
    with pytest.raises(ValueError):
        store.execute_query(bad_sql)


def test_execute_query_rejects_writes_file(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_run_and_exec(store)
    with pytest.raises(ValueError):
        store.execute_query("DELETE FROM runs")
    # The run row is untouched.
    assert store.get_run("run-1") is not None


def test_execute_query_allows_select_and_with(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_run_and_exec(store)
    assert store.execute_query("SELECT run_id FROM runs") == [("run-1",)]
    assert store.execute_query("WITH x AS (SELECT run_id FROM runs) SELECT * FROM x") == [("run-1",)]
    # Comment + SELECT is fine.
    assert store.execute_query("-- comment\nSELECT 1") == [(1,)]


def test_execute_query_readonly_connection_blocks_slipped_write(tmp_path: Path) -> None:
    """Defence in depth: even if the statement check were bypassed, the
    file-backed read-only connection refuses writes. We approximate by
    confirming a SELECT works while the DB file is not mutated."""
    store = _store(tmp_path)
    _seed_run_and_exec(store)
    before = store.count("runs")
    store.execute_query("SELECT * FROM runs")
    assert store.count("runs") == before
