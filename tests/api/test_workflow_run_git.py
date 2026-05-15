"""ADR-039 D39-2.5 — integration test for the workflow-run git join.

Asserts that ``ApiRuntime.start_workflow`` (driven via the public
``POST /api/workflows/{id}/execute`` route) captures the post-auto-commit
HEAD SHA on the resulting ``WorkflowRun.workflow_git_commit`` field. This
is the join key the ADR-038 ``runs`` row will read at insert time once
the Phase 4 final-merge PRs reconcile both tracking branches into main.

End-to-end coverage:
- Dirty working tree → pre-run auto-commit fires → SHA captured.
- Clean working tree → no commit, SHA = current HEAD.
- No git repo (degraded mode per ADR-039 §3.9) → SHA is ``None`` and
  the workflow still starts (no exception leaks out of the hook).
- ``runtime.lineage_store.set_pending_git_commit`` hook fires when
  present (forward compatibility for ADR-038 integration at Phase 4).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scieasy.api.runtime import ApiRuntime, _rmtree_force

_DIRTY_YAML = (
    "workflow:\n  id: main\n  version: 1.0.1\n"
    "  description: 'dirty for git-commit capture test'\n"
    "  nodes: []\n  edges: []\n  metadata: {}\n"
)
_DIRTY_YAML_VAR = _DIRTY_YAML.replace("dirty for", "dirty-variant for")


def _commit_initial_workflow(project_path: Path, runtime: ApiRuntime) -> str:
    """Drain the seed dirty tree (lineage.db etc.) so HEAD is clean."""
    if runtime.workflow_runs:
        runtime.workflow_runs.clear()
    from scieasy.core.versioning.git_engine import GitEngine

    engine = GitEngine(project_path)
    if engine.status()["dirty"]:
        engine.commit("test fixture: drain seed", prefix=None)
    return engine.head_state().commit_sha


def _cancel_run(runtime: ApiRuntime, workflow_id: str) -> None:
    """Best-effort cancel of the background scheduler task post-assert."""
    run = runtime.workflow_runs.get(workflow_id)
    if run is None:
        return
    if not run.task.done():
        run.task.cancel()


def test_start_workflow_captures_git_commit_dirty_tree(client: TestClient, opened_project: Path) -> None:
    """Dirty workflow YAML → pre-run auto-commit fires → SHA on WorkflowRun.

    This is the canonical happy path for ADR-039 §3.4 + D39-2.5 wiring.
    Driven via the public REST route so the asyncio loop is live.
    """
    runtime: ApiRuntime = client.app.state.runtime

    from scieasy.core.versioning.git_engine import GitEngine

    engine = GitEngine(opened_project)
    head_before_dirty = _commit_initial_workflow(opened_project, runtime)

    # Now make a dirty edit to the seed workflow so start_workflow's
    # pre-run auto-commit hook has something to squash.
    wf_path = opened_project / "workflows" / "main.yaml"
    wf_path.write_text(_DIRTY_YAML, encoding="utf-8")
    assert engine.status()["dirty"] is True

    # Drive ApiRuntime.start_workflow via the public route so the test
    # runs inside the FastAPI asyncio loop (the route handler awaits
    # ``asyncio.create_task`` internally).
    resp = client.post("/api/workflows/main/execute")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workflow_id"] == "main"
    assert body["status"] == "started"

    run = runtime.workflow_runs["main"]
    try:
        assert run.workflow_git_commit is not None
        # 40-char hex SHA from git.
        assert len(run.workflow_git_commit) == 40
        # The captured SHA is the NEW post-auto-commit HEAD, not the prior one.
        assert run.workflow_git_commit != head_before_dirty

        # Confirm git itself recorded an ``auto:``-prefixed commit at HEAD.
        log = engine.log(limit=1)
        assert log
        assert log[0]["sha"] == run.workflow_git_commit
        assert log[0]["subject"].startswith("auto: pre-run @")
    finally:
        _cancel_run(runtime, "main")


def test_start_workflow_captures_git_commit_clean_tree(client: TestClient, opened_project: Path) -> None:
    """Clean working tree → no new commit, SHA = current HEAD."""
    runtime: ApiRuntime = client.app.state.runtime
    head_clean = _commit_initial_workflow(opened_project, runtime)

    from scieasy.core.versioning.git_engine import GitEngine

    engine = GitEngine(opened_project)
    assert engine.status()["dirty"] is False

    resp = client.post("/api/workflows/main/execute")
    assert resp.status_code == 200, resp.text

    run = runtime.workflow_runs["main"]
    try:
        assert run.workflow_git_commit == head_clean
        # No new commit was created.
        assert engine.head_state().commit_sha == head_clean
    finally:
        _cancel_run(runtime, "main")


def test_start_workflow_degraded_mode_when_no_git_repo(client: TestClient, opened_project: Path) -> None:
    """Project without ``.git`` → workflow still starts, SHA is ``None``.

    Per ADR-039 §3.9: removing ``.git/`` puts the project in degraded
    mode. ``start_workflow`` MUST still succeed; only the version-control
    join is unavailable.
    """
    runtime: ApiRuntime = client.app.state.runtime

    # Forcibly remove the auto-init'd repo to simulate degraded mode.
    # Use ``_rmtree_force`` because git's pack/object files are read-only
    # on Windows; plain ``shutil.rmtree`` raises PermissionError.
    _rmtree_force(opened_project / ".git")

    resp = client.post("/api/workflows/main/execute")
    assert resp.status_code == 200, resp.text

    run = runtime.workflow_runs["main"]
    try:
        assert run.workflow_git_commit is None
    finally:
        _cancel_run(runtime, "main")


def test_start_workflow_dirty_tree_commit_failure_degrades_to_none(
    client: TestClient, opened_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex P1 on PR #959 — commit failure → workflow_git_commit = None.

    When the dirty-tree pre-run auto-commit raises, the workflow is
    about to execute against an uncommitted working tree. Persisting
    the prior HEAD SHA in that case would let "Restore this run's
    workflow" restore the wrong revision and silently corrupt
    reproducibility. The right behaviour is to degrade to ``None`` so
    the ADR-038 ``runs.workflow_dirty=1`` safety net takes over.
    """
    runtime: ApiRuntime = client.app.state.runtime
    _commit_initial_workflow(opened_project, runtime)

    # Force a dirty tree.
    (opened_project / "workflows" / "main.yaml").write_text(_DIRTY_YAML, encoding="utf-8")

    # Monkeypatch GitEngine.commit to raise, simulating a stuck index
    # / locked .git / disk-full failure during auto-commit.
    from scieasy.core.versioning.git_engine import GitEngine, GitError

    def _fail_commit(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise GitError(1, "simulated auto-commit failure", ["commit"])

    monkeypatch.setattr(GitEngine, "commit", _fail_commit)

    resp = client.post("/api/workflows/main/execute")
    assert resp.status_code == 200, resp.text

    run = runtime.workflow_runs["main"]
    try:
        # The PRIOR HEAD must NOT be persisted — degraded mode wins.
        assert run.workflow_git_commit is None
    finally:
        _cancel_run(runtime, "main")


def test_start_workflow_threads_git_commit_into_lineage_insert(client: TestClient, opened_project: Path) -> None:
    """The captured SHA is threaded into the lineage ``runs`` row at INSERT time.

    Phase 3.5 integration audit P1-1 + P1-2: previously the SHA was
    written by a separate ``set_pending_git_commit`` UPDATE call AFTER
    ``_build_lineage_recorder`` had already inserted the runs row — that
    raced with the previous run and stamped the SHA on the wrong row.
    The fix routes the SHA + workflow_dirty flag through
    ``_build_lineage_recorder`` into the ``RunRecord`` constructor so
    both fields land on THIS run's row on the INSERT itself. This test
    proves the runs row carries the right SHA.
    """
    runtime: ApiRuntime = client.app.state.runtime
    _commit_initial_workflow(opened_project, runtime)

    # Make tree dirty so an auto-commit + SHA capture happens.
    (opened_project / "workflows" / "main.yaml").write_text(_DIRTY_YAML_VAR, encoding="utf-8")

    resp = client.post("/api/workflows/main/execute")
    assert resp.status_code == 200, resp.text

    run = runtime.workflow_runs["main"]
    try:
        assert run.workflow_git_commit is not None
        # The ADR-038 LineageStore is live in the integrated runtime; the
        # runs row inserted by ``_build_lineage_recorder`` should carry
        # the same SHA on the same workflow_id.
        if runtime.lineage_store is not None:
            rows = runtime.lineage_store.list_runs(workflow_id="main")
            assert rows, "lineage store should hold at least one runs row"
            assert rows[0]["workflow_git_commit"] == run.workflow_git_commit
    finally:
        _cancel_run(runtime, "main")


# ---------------------------------------------------------------------------
# D39-3.2 (#968) P1-B / Phase 3.5 integration audit P1-1: defensive guards.
#
# After the Phase 3.5 fix, ``start_workflow`` no longer calls
# ``lineage_store.set_pending_git_commit`` — the SHA is threaded into
# ``_build_lineage_recorder`` and lands on the runs row at INSERT time.
# The defensive guards below still apply: the lineage recorder is
# best-effort, and a missing / misbehaving lineage_store must not take
# down the workflow execution path. The SHA must still appear on
# ``WorkflowRun.workflow_git_commit`` regardless.
# ---------------------------------------------------------------------------


def test_start_workflow_handles_missing_lineage_store(
    client: TestClient, opened_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lineage_store=None: workflow still starts; SHA still on WorkflowRun.

    Simulates the degraded mode where lineage init failed
    (P2-1 covers the same scenario at the ``open_project`` boundary).
    """
    runtime: ApiRuntime = client.app.state.runtime
    _commit_initial_workflow(opened_project, runtime)

    (opened_project / "workflows" / "main.yaml").write_text(_DIRTY_YAML_VAR, encoding="utf-8")

    monkeypatch.setattr(runtime, "lineage_store", None, raising=False)

    resp = client.post("/api/workflows/main/execute")
    assert resp.status_code == 200, resp.text

    run = runtime.workflow_runs["main"]
    try:
        assert run.workflow_git_commit is not None
    finally:
        _cancel_run(runtime, "main")


def test_start_workflow_swallows_lineage_insert_exception(
    client: TestClient, opened_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If LineageStore.insert_run raises, the workflow still starts.

    The lineage recorder is best-effort — a misbehaving lineage store
    must not take down the ADR-039 pre-run capture path. The captured
    SHA must still be on ``WorkflowRun.workflow_git_commit``.
    """
    runtime: ApiRuntime = client.app.state.runtime
    _commit_initial_workflow(opened_project, runtime)

    (opened_project / "workflows" / "main.yaml").write_text(_DIRTY_YAML_VAR, encoding="utf-8")

    # Patch the live lineage store's insert_run to raise.
    if runtime.lineage_store is not None:

        def _boom(*_args, **_kwargs):
            raise RuntimeError("simulated lineage insert failure")

        monkeypatch.setattr(runtime.lineage_store, "insert_run", _boom, raising=False)

    resp = client.post("/api/workflows/main/execute")
    assert resp.status_code == 200, resp.text

    run = runtime.workflow_runs["main"]
    try:
        assert run.workflow_git_commit is not None
    finally:
        _cancel_run(runtime, "main")
