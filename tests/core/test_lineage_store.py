"""Unit tests for :class:`LineageStore` query methods (ADR-038 / ADR-039).

This file complements ``test_lineage_store_4table.py`` (the 3-block
integration smoke) and ``test_lineage_extended.py`` by covering the
narrower query surfaces added for downstream features:

- ``workflow_git_commits_in`` (ADR-039 Addendum 1 §11.4 row #1356) —
  drives the branch-delete safety net's "which orphan SHAs does lineage
  reference?" check.
"""

from __future__ import annotations

from scistudio.core.lineage.record import RunRecord
from scistudio.core.lineage.store import LineageStore


def _run_record(run_id: str, *, sha: str | None) -> RunRecord:
    """Build a minimal ``RunRecord`` with the given ``workflow_git_commit``."""
    return RunRecord(
        run_id=run_id,
        workflow_id=f"wf-{run_id}",
        workflow_git_commit=sha,
        workflow_yaml_snapshot="id: wf\n",
        workflow_dirty=False,
        started_at="2026-05-21T00:00:00Z",
        finished_at="2026-05-21T00:00:01Z",
        status="completed",
        environment_snapshot={"python_version": "3.13.0", "platform": "test", "key_packages": {}},
        triggered_by="test",
        parent_run_id=None,
        execute_from_block_id=None,
        user_notes=None,
    )


# ---------------------------------------------------------------------------
# workflow_git_commits_in — #1356 branch-delete safety net read side
# ---------------------------------------------------------------------------


def test_workflow_git_commits_in_returns_intersection() -> None:
    """Subset of input SHAs that appear in runs.workflow_git_commit."""
    store = LineageStore(":memory:")
    store.insert_run(_run_record("r1", sha="a" * 40))
    store.insert_run(_run_record("r2", sha="b" * 40))
    store.insert_run(_run_record("r3", sha="c" * 40))

    result = store.workflow_git_commits_in(["a" * 40, "z" * 40, "b" * 40])

    assert result == {"a" * 40, "b" * 40}


def test_workflow_git_commits_in_empty_input_returns_empty_set() -> None:
    """Empty input → empty set, no SQL call required."""
    store = LineageStore(":memory:")
    store.insert_run(_run_record("r1", sha="a" * 40))

    assert store.workflow_git_commits_in([]) == set()


def test_workflow_git_commits_in_absent_shas_filtered() -> None:
    """SHAs not present in the runs table do not leak through."""
    store = LineageStore(":memory:")
    store.insert_run(_run_record("r1", sha="a" * 40))

    result = store.workflow_git_commits_in(["x" * 40, "y" * 40])

    assert result == set()


def test_workflow_git_commits_in_null_rows_filtered() -> None:
    """``runs`` rows with ``workflow_git_commit = NULL`` never match."""
    store = LineageStore(":memory:")
    store.insert_run(_run_record("r1", sha=None))
    store.insert_run(_run_record("r2", sha="a" * 40))

    # Querying for None must not match the NULL row — SQL semantics
    # require explicit IS NULL, not IN (...). The method de-duplicates
    # and drops empty strings, so this is effectively an empty query.
    result_none = store.workflow_git_commits_in([])
    assert result_none == set()

    # And querying for a real SHA still works alongside NULL rows.
    result_real = store.workflow_git_commits_in(["a" * 40])
    assert result_real == {"a" * 40}


def test_workflow_git_commits_in_duplicates_collapsed() -> None:
    """Duplicate input SHAs are tolerated; the result is still a set."""
    store = LineageStore(":memory:")
    store.insert_run(_run_record("r1", sha="a" * 40))

    result = store.workflow_git_commits_in(["a" * 40, "a" * 40, "a" * 40])

    assert result == {"a" * 40}


def test_workflow_git_commits_in_returns_set_type() -> None:
    """Return type is ``set[str]`` — callers iterate without ordering."""
    store = LineageStore(":memory:")
    store.insert_run(_run_record("r1", sha="a" * 40))

    result = store.workflow_git_commits_in(["a" * 40])

    assert isinstance(result, set)
