"""Smoke tests for the post-ADR-038 lineage package import surface.

Pre-ADR-038 this file exercised the hash-keyed ``LineageRecord`` plus the
in-memory ``ProvenanceGraph`` helper. ADR-038 §3.4 deletes content hashing
and §5.1 deletes ``graph.py``; the assertions below survive only as a
guard against the package import surface regressing.
"""

from __future__ import annotations

import sqlite3

import pytest

from scistudio.core.lineage import (
    BlockExecutionRecord,
    BlockIORow,
    DataObjectRow,
    EnvironmentSnapshot,
    LineageRecorder,
    LineageStore,
    RunContext,
    RunRecord,
    get_run_context,
    reset_run_context,
    set_run_context,
)


class TestPublicImportSurface:
    def test_all_new_names_resolve(self) -> None:
        """Every name we promised at the package boundary is importable."""
        assert RunRecord is not None
        assert BlockExecutionRecord is not None
        assert DataObjectRow is not None
        assert BlockIORow is not None
        assert LineageStore is not None
        assert LineageRecorder is not None
        assert EnvironmentSnapshot is not None
        assert RunContext is not None

    def test_provenance_graph_removed(self) -> None:
        """ADR-038 §3.4 + §5.1: ProvenanceGraph is gone."""
        with pytest.raises(ImportError):
            from scistudio.core.lineage import graph  # noqa: F401


class TestLineageStoreLifecycle:
    def test_close_is_idempotent(self) -> None:
        store = LineageStore(":memory:")
        store.close()
        # Calling close() again on a closed connection must not raise.
        store.close()

    def test_count_rejects_unknown_table(self) -> None:
        store = LineageStore(":memory:")
        with pytest.raises(ValueError):
            store.count("nope")
        store.close()

    def test_close_then_count_raises(self) -> None:
        store = LineageStore(":memory:")
        store.close()
        with pytest.raises(sqlite3.ProgrammingError):
            store.count("runs")


class TestRunContextHelpers:
    def test_set_get_reset_roundtrip(self) -> None:
        assert get_run_context() is None
        token = set_run_context(RunContext(run_id="r1", block_execution_id="be1"))
        try:
            ctx = get_run_context()
            assert ctx is not None
            assert ctx.run_id == "r1"
            assert ctx.block_execution_id == "be1"
        finally:
            reset_run_context(token)
        assert get_run_context() is None
