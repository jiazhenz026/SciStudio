"""Regression coverage for ApiRuntime lineage run finalization."""

from __future__ import annotations

from scistudio.api.runtime import ApiRuntime
from scistudio.blocks.base.state import BlockState


class _Recorder:
    def __init__(self) -> None:
        self.statuses: list[str] = []
        self.disposed = False

    def finalize_run(self, *, status: str) -> None:
        self.statuses.append(status)

    def dispose(self) -> None:
        self.disposed = True


class _Task:
    def __init__(self, *, cancelled: bool = False, exc: BaseException | None = None) -> None:
        self._cancelled = cancelled
        self._exc = exc

    def cancelled(self) -> bool:
        return self._cancelled

    def exception(self) -> BaseException | None:
        return self._exc


class _Scheduler:
    def __init__(self, states: dict[str, BlockState]) -> None:
        self._states = states

    def block_states(self) -> dict[str, BlockState]:
        return dict(self._states)


def _runtime() -> ApiRuntime:
    return object.__new__(ApiRuntime)


def test_lineage_finalization_marks_run_failed_when_block_error_task_succeeds() -> None:
    """A block ERROR is a failed run even when DAGScheduler exits normally."""
    runtime = _runtime()
    recorder = _Recorder()
    scheduler = _Scheduler({"A": BlockState.ERROR, "B": BlockState.SKIPPED})
    task = _Task()

    runtime._finalize_lineage_run(recorder, task, scheduler)  # type: ignore[arg-type]

    assert recorder.statuses == ["failed"]
    assert recorder.disposed is True


def test_lineage_finalization_keeps_completed_when_all_blocks_done() -> None:
    runtime = _runtime()
    recorder = _Recorder()
    scheduler = _Scheduler({"A": BlockState.DONE, "B": BlockState.DONE})
    task = _Task()

    runtime._finalize_lineage_run(recorder, task, scheduler)  # type: ignore[arg-type]

    assert recorder.statuses == ["completed"]
    assert recorder.disposed is True


def test_lineage_finalization_prefers_cancelled_block_state() -> None:
    runtime = _runtime()
    recorder = _Recorder()
    scheduler = _Scheduler({"A": BlockState.CANCELLED, "B": BlockState.SKIPPED})
    task = _Task()

    runtime._finalize_lineage_run(recorder, task, scheduler)  # type: ignore[arg-type]

    assert recorder.statuses == ["cancelled"]
    assert recorder.disposed is True


def test_lineage_finalization_keeps_task_exception_as_failed() -> None:
    runtime = _runtime()
    recorder = _Recorder()
    scheduler = _Scheduler({"A": BlockState.DONE})
    task = _Task(exc=RuntimeError("scheduler crashed"))

    runtime._finalize_lineage_run(recorder, task, scheduler)  # type: ignore[arg-type]

    assert recorder.statuses == ["failed"]
    assert recorder.disposed is True


class _DegradedRecorder(_Recorder):
    """#1527: recorder that reports a degraded provenance state."""

    run_id = "run-deg"
    provenance_degraded = True


def test_lineage_finalization_warns_on_degraded_provenance(caplog) -> None:  # type: ignore[no-untyped-def]
    """#1527 (BUG-6): a run that finishes 'completed' but whose provenance
    writes failed must surface the loss (warning log + still finalises)."""
    import logging

    runtime = _runtime()
    recorder = _DegradedRecorder()
    scheduler = _Scheduler({"A": BlockState.DONE, "B": BlockState.DONE})
    task = _Task()

    with caplog.at_level(logging.WARNING):
        runtime._finalize_lineage_run(recorder, task, scheduler)  # type: ignore[arg-type]

    assert recorder.statuses == ["completed"]
    assert recorder.disposed is True
    assert any("provenance" in rec.message.lower() for rec in caplog.records)
