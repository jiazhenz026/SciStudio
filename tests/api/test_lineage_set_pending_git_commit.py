"""Tests for ``LineageStore.set_pending_git_commit`` (D38-3.2 / Phase 3.5 H-A1).

Phase 3.5 hazard H-A1: ``D39-2.5`` (PR #959 on ``track/adr-039/git-versioning``)
calls ``lineage_store.set_pending_git_commit(workflow_id, sha)`` from
``ApiRuntime.start_workflow`` as a forward-compatible hook to stamp the
pre-run auto-commit SHA into ``runs.workflow_git_commit``. D38-3.2 adds
the method on the lineage track so the hook lands on a real implementation
at final-merge.
"""

from __future__ import annotations

from scistudio.core.lineage.record import RunRecord
from scistudio.core.lineage.store import LineageStore


def _new_store_with_run(
    *,
    workflow_id: str,
    started_at: str = "2026-05-15T10:00:00",
    run_id: str = "run-abc",
    initial_commit: str | None = None,
) -> LineageStore:
    store = LineageStore(":memory:")
    store.insert_run(
        RunRecord(
            run_id=run_id,
            workflow_id=workflow_id,
            workflow_yaml_snapshot="id: " + workflow_id,
            started_at=started_at,
            status="running",
            environment_snapshot={},
            workflow_git_commit=initial_commit,
        )
    )
    return store


class TestSetPendingGitCommit:
    def test_stamps_sha_on_latest_run(self) -> None:
        """The most recent run for a workflow gets its column updated."""
        store = _new_store_with_run(workflow_id="wf-1")

        store.set_pending_git_commit("wf-1", "abc1234")

        row = store.get_run("run-abc")
        assert row is not None
        assert row["workflow_git_commit"] == "abc1234"

    def test_picks_most_recent_when_multiple_runs(self) -> None:
        """When multiple runs exist for a workflow_id, the latest is updated."""
        store = _new_store_with_run(
            workflow_id="wf-1",
            started_at="2026-05-15T08:00:00",
            run_id="run-older",
        )
        # Insert a second, newer run.
        store.insert_run(
            RunRecord(
                run_id="run-newer",
                workflow_id="wf-1",
                workflow_yaml_snapshot="id: wf-1",
                started_at="2026-05-15T12:00:00",
                status="running",
                environment_snapshot={},
            )
        )

        store.set_pending_git_commit("wf-1", "deadbeef")

        older = store.get_run("run-older")
        newer = store.get_run("run-newer")
        assert older is not None and newer is not None
        # Newer run got the update; older row untouched.
        assert newer["workflow_git_commit"] == "deadbeef"
        assert older["workflow_git_commit"] is None

    def test_none_sha_clears_column(self) -> None:
        """``set_pending_git_commit(workflow_id, None)`` clears the column.

        Per ADR-039 §5.2: when commit creation fails, the hook records
        ``None`` so the column is explicitly empty rather than left at a
        stale previous value.
        """
        store = _new_store_with_run(workflow_id="wf-2", initial_commit="oldsha")

        store.set_pending_git_commit("wf-2", None)

        row = store.get_run("run-abc")
        assert row is not None
        assert row["workflow_git_commit"] is None

    def test_no_matching_run_is_noop(self) -> None:
        """Unknown workflow_id silently does nothing — no error."""
        store = _new_store_with_run(workflow_id="wf-1")

        # Should not raise.
        store.set_pending_git_commit("wf-not-present", "ignored")

        # Existing run untouched.
        row = store.get_run("run-abc")
        assert row is not None
        assert row["workflow_git_commit"] is None

    def test_does_not_affect_other_workflows(self) -> None:
        """Updating workflow_id 'wf-A' does not touch rows for 'wf-B'."""
        store = _new_store_with_run(workflow_id="wf-A", run_id="run-A")
        store.insert_run(
            RunRecord(
                run_id="run-B",
                workflow_id="wf-B",
                workflow_yaml_snapshot="id: wf-B",
                started_at="2026-05-15T11:00:00",
                status="running",
                environment_snapshot={},
            )
        )

        store.set_pending_git_commit("wf-A", "shaA")

        a = store.get_run("run-A")
        b = store.get_run("run-B")
        assert a is not None and b is not None
        assert a["workflow_git_commit"] == "shaA"
        assert b["workflow_git_commit"] is None
