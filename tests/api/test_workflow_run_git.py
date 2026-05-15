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


def test_start_workflow_invokes_lineage_hook_when_present(
    client: TestClient, opened_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If ``runtime.lineage_store`` exposes ``set_pending_git_commit``, it's called.

    Forward-compatibility check: when the ADR-038 schema lands and the
    LineageRecorder exposes a ``set_pending_git_commit(workflow_id, sha)``
    hook, ``start_workflow`` must hand off the captured SHA. On the
    ADR-039 tracking branch alone there is no lineage_store; we
    monkey-patch one in to exercise the cross-track wiring contract.
    """
    runtime: ApiRuntime = client.app.state.runtime
    _commit_initial_workflow(opened_project, runtime)

    # Make tree dirty so an auto-commit + SHA capture happens.
    (opened_project / "workflows" / "main.yaml").write_text(_DIRTY_YAML_VAR, encoding="utf-8")

    received: list[tuple[str, str]] = []

    class _StubLineageStore:
        def set_pending_git_commit(self, workflow_id: str, sha: str) -> None:
            received.append((workflow_id, sha))

    monkeypatch.setattr(runtime, "lineage_store", _StubLineageStore(), raising=False)

    resp = client.post("/api/workflows/main/execute")
    assert resp.status_code == 200, resp.text

    run = runtime.workflow_runs["main"]
    try:
        assert run.workflow_git_commit is not None
        assert received == [("main", run.workflow_git_commit)]
    finally:
        _cancel_run(runtime, "main")
