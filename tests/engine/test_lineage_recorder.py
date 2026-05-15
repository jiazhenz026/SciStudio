"""Tests for the ADR-038 :class:`LineageRecorder` (migrated from #166 single-table).

The recorder now writes the four-table schema. These tests exercise the
event-driven write path with an in-memory ``LineageStore`` so we cover the
SQL round-trip rather than just mock assertions.
"""

from __future__ import annotations

import asyncio

from scieasy.core.lineage.record import RunRecord
from scieasy.core.lineage.recorder import LineageRecorder
from scieasy.core.lineage.store import LineageStore
from scieasy.engine.events import (
    BLOCK_CANCELLED,
    BLOCK_DONE,
    BLOCK_ERROR,
    BLOCK_SKIPPED,
    EngineEvent,
    EventBus,
)


def _make_recorder(
    with_store: bool = True,
    run_id: str = "run-test",
) -> tuple[LineageRecorder, EventBus, LineageStore | None]:
    event_bus = EventBus()
    store: LineageStore | None
    if with_store:
        store = LineageStore(":memory:")
        store.insert_run(
            RunRecord(
                run_id=run_id,
                workflow_id="wf",
                workflow_yaml_snapshot="",
                started_at="2026-05-15T00:00:00",
                status="running",
                environment_snapshot={},
            )
        )
    else:
        store = None
    recorder = LineageRecorder(event_bus, lineage_store=store, run_id=run_id)
    return recorder, event_bus, store


class TestLineageRecorder:
    def test_block_done_writes_record(self) -> None:
        """BLOCK_DONE inserts a row into ``block_executions`` with termination='completed'."""
        _recorder, bus, store = _make_recorder()
        assert store is not None

        asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_DONE, block_id="A", data={"outputs": {}})))

        rows = store.list_block_executions("run-test")
        assert len(rows) == 1
        assert rows[0]["block_id"] == "A"
        assert rows[0]["termination"] == "completed"

    def test_block_error_writes_record(self) -> None:
        """BLOCK_ERROR -> termination='error' and termination_detail populated."""
        _recorder, bus, store = _make_recorder()
        assert store is not None

        asyncio.run(
            bus.emit(
                EngineEvent(
                    event_type=BLOCK_ERROR,
                    block_id="B",
                    data={"error": "something broke"},
                )
            )
        )

        rows = store.list_block_executions("run-test")
        assert len(rows) == 1
        assert rows[0]["termination"] == "error"
        assert rows[0]["termination_detail"] == "something broke"

    def test_block_cancelled_writes_record(self) -> None:
        _recorder, bus, store = _make_recorder()
        assert store is not None

        asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_CANCELLED, block_id="C")))

        rows = store.list_block_executions("run-test")
        assert len(rows) == 1
        assert rows[0]["termination"] == "cancelled"

    def test_block_skipped_writes_record(self) -> None:
        _recorder, bus, store = _make_recorder()
        assert store is not None

        asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_SKIPPED, block_id="D")))

        rows = store.list_block_executions("run-test")
        assert len(rows) == 1
        assert rows[0]["termination"] == "skipped"

    def test_no_store_is_noop(self) -> None:
        _recorder, bus, _store = _make_recorder(with_store=False)
        # Should not raise.
        asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_DONE, block_id="A", data={"outputs": {}})))

    def test_duration_computed(self) -> None:
        """record_start + BLOCK_DONE -> duration_ms >= 0 is written."""
        recorder, bus, store = _make_recorder()
        assert store is not None
        recorder.record_start("X")

        asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_DONE, block_id="X", data={"outputs": {}})))

        rows = store.list_block_executions("run-test")
        assert len(rows) == 1
        assert rows[0]["duration_ms"] is not None
        assert rows[0]["duration_ms"] >= 0

    def test_none_block_id_is_noop(self) -> None:
        _recorder, bus, store = _make_recorder()
        assert store is not None

        asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_DONE)))

        assert store.count("block_executions") == 0

    def test_block_version_captured(self) -> None:
        """``block_version`` from event data is persisted on the row."""
        _recorder, bus, store = _make_recorder()
        assert store is not None

        asyncio.run(
            bus.emit(
                EngineEvent(
                    event_type=BLOCK_DONE,
                    block_id="V",
                    data={"block_version": "1.2.3", "block_type": "LoadData"},
                )
            )
        )

        rows = store.list_block_executions("run-test")
        assert rows[0]["block_version"] == "1.2.3"
        assert rows[0]["block_type"] == "LoadData"

    def test_finalize_run_updates_status(self) -> None:
        """``finalize_run`` writes finished_at + status to the runs row."""
        recorder, _bus, store = _make_recorder()
        assert store is not None
        recorder.finalize_run(status="completed")
        run = store.get_run("run-test")
        assert run is not None
        assert run["status"] == "completed"
        assert run["finished_at"] is not None


class TestLineageRecorderDispose:
    """D38-3.2 (closes Codex P1 on PR #926 / D38-3.1b P1-2).

    After a workflow run finalises, the recorder must unsubscribe from
    the EventBus or successive ``start_workflow`` calls accumulate
    callbacks and cross-pollinate later runs' lineage rows.
    """

    def test_dispose_unsubscribes_from_event_bus(self) -> None:
        recorder, bus, store = _make_recorder()
        assert store is not None

        recorder.dispose()

        # After dispose, BLOCK_DONE no longer writes to the store.
        asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_DONE, block_id="A", data={"outputs": {}})))

        assert store.count("block_executions") == 0

    def test_dispose_is_idempotent(self) -> None:
        recorder, _bus, _store = _make_recorder()
        recorder.dispose()
        # Second call must not raise.
        recorder.dispose()

    def test_two_sequential_recorders_do_not_cross_pollinate(self) -> None:
        """Two recorders for two different runs, with the first disposed,
        must not cause the first to receive the second's events."""
        bus = EventBus()
        store_a = LineageStore(":memory:")
        store_a.insert_run(
            RunRecord(
                run_id="run-A",
                workflow_id="wf",
                workflow_yaml_snapshot="",
                started_at="2026-05-15T00:00:00",
                status="running",
                environment_snapshot={},
            )
        )
        recorder_a = LineageRecorder(bus, lineage_store=store_a, run_id="run-A")
        recorder_a.dispose()  # Simulate first run completing.

        store_b = LineageStore(":memory:")
        store_b.insert_run(
            RunRecord(
                run_id="run-B",
                workflow_id="wf",
                workflow_yaml_snapshot="",
                started_at="2026-05-15T01:00:00",
                status="running",
                environment_snapshot={},
            )
        )
        _recorder_b = LineageRecorder(bus, lineage_store=store_b, run_id="run-B")

        asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_DONE, block_id="X", data={"outputs": {}})))

        # Run B sees the event; run A (disposed) does NOT.
        assert store_a.count("block_executions") == 0
        assert store_b.count("block_executions") == 1


class TestLineageRecordRemoved:
    """D38-3.2 closes D38-3.1a P1-4 — the legacy ``LineageRecord`` shell
    must no longer be importable from the lineage package."""

    def test_lineage_record_no_longer_exported(self) -> None:
        import scieasy.core.lineage as lineage

        assert not hasattr(lineage, "LineageRecord"), "Legacy LineageRecord shell must be removed per ADR §3.4"


class TestTerminalEventFullPayload:
    """D38-3.2 closes D38-3.1a P1-1 / D38-3.1b P1-3 — all four terminal
    events must carry ``block_type`` / ``block_version`` so the recorder
    writes non-empty columns."""

    def test_block_error_with_full_payload(self) -> None:
        _recorder, bus, store = _make_recorder()
        assert store is not None

        asyncio.run(
            bus.emit(
                EngineEvent(
                    event_type=BLOCK_ERROR,
                    block_id="B",
                    data={
                        "workflow_id": "wf",
                        "block_type": "LoadData",
                        "block_version": "1.2.3",
                        "config": {"path": "/tmp/x"},
                        "error": "boom",
                    },
                )
            )
        )

        rows = store.list_block_executions("run-test")
        assert len(rows) == 1
        assert rows[0]["block_type"] == "LoadData"
        assert rows[0]["block_version"] == "1.2.3"
        assert rows[0]["termination_detail"] == "boom"

    def test_block_cancelled_with_full_payload(self) -> None:
        _recorder, bus, store = _make_recorder()
        assert store is not None

        asyncio.run(
            bus.emit(
                EngineEvent(
                    event_type=BLOCK_CANCELLED,
                    block_id="C",
                    data={
                        "workflow_id": "wf",
                        "block_type": "SaveData",
                        "block_version": "0.5.0",
                        "config": {},
                    },
                )
            )
        )

        rows = store.list_block_executions("run-test")
        assert len(rows) == 1
        assert rows[0]["block_type"] == "SaveData"
        assert rows[0]["block_version"] == "0.5.0"

    def test_block_skipped_with_full_payload(self) -> None:
        _recorder, bus, store = _make_recorder()
        assert store is not None

        asyncio.run(
            bus.emit(
                EngineEvent(
                    event_type=BLOCK_SKIPPED,
                    block_id="D",
                    data={
                        "workflow_id": "wf",
                        "block_type": "Threshold",
                        "block_version": "2.0.0",
                        "config": {},
                    },
                )
            )
        )

        rows = store.list_block_executions("run-test")
        assert len(rows) == 1
        assert rows[0]["block_type"] == "Threshold"
        assert rows[0]["block_version"] == "2.0.0"
