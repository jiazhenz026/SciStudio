"""Tests for state enums — BlockState, ExecutionMode."""

from __future__ import annotations

from scistudio.blocks.base.state import (
    # ADR-020: BatchErrorStrategy, BatchMode, InputDelivery removed
    BlockState,
    ExecutionMode,
)


class TestBlockStateValues:
    """BlockState — lifecycle state of a block instance."""

    def test_all_values(self) -> None:
        assert BlockState.IDLE.value == "idle"
        assert BlockState.READY.value == "ready"
        assert BlockState.RUNNING.value == "running"
        assert BlockState.PAUSED.value == "paused"
        assert BlockState.DONE.value == "done"
        assert BlockState.ERROR.value == "error"

    # ADR-018: CANCELLED and SKIPPED added
    def test_cancelled_skipped(self) -> None:
        assert BlockState.CANCELLED.value == "cancelled"
        assert BlockState.SKIPPED.value == "skipped"

    def test_member_count(self) -> None:
        assert len(BlockState) == 8  # ADR-018: was 6, now 8


class TestExecutionModeValues:
    """ExecutionMode — how the block is executed."""

    def test_all_values(self) -> None:
        assert ExecutionMode.AUTO.value == "auto"
        assert ExecutionMode.INTERACTIVE.value == "interactive"
        assert ExecutionMode.EXTERNAL.value == "external"

    def test_member_count(self) -> None:
        assert len(ExecutionMode) == 3


# ADR-020: TestBatchModeValues removed — BatchMode enum deleted.
# ADR-020: TestInputDeliveryValues removed — InputDelivery enum deleted.
# ADR-020: TestBatchErrorStrategyValues removed — BatchErrorStrategy enum deleted.
