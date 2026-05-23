"""Tests for ``scistudio.api.routes.git`` REST endpoints (ADR-039).

Phase D39-2.2b — bodies filled, xfail flipped to passing.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from scistudio.engine.events import WORKFLOW_CHANGED

# ---------------------------------------------------------------------------
# Commit / log / diff / restore
# ---------------------------------------------------------------------------


def test_commit_endpoint_round_trip(client: TestClient, opened_project: Path) -> None:
    """POST /api/git/commit → 200 with sha; GET /api/git/log returns it."""
    (opened_project / "workflows" / "main.yaml").write_text("id: main\nnodes: []\n", encoding="utf-8")
    resp = client.post("/api/git/commit", json={"message": "test commit"})
    assert resp.status_code == 200, resp.text
    sha = resp.json()["commit_sha"]
    assert len(sha) == 40

    log_resp = client.get("/api/git/log")
    assert log_resp.status_code == 200
    entries = log_resp.json()
    assert entries[0]["sha"] == sha
    assert entries[0]["subject"] == "test commit"


def test_commit_endpoint_clean_tree_409(client: TestClient, opened_project: Path) -> None:
    """POST /api/git/commit on clean tree returns 409."""
    # First drain any residual untracked state (e.g. metadata.db).
    if client.get("/api/git/status").json()["dirty"]:
        client.post("/api/git/commit", json={"message": "drain"})
    resp = client.post("/api/git/commit", json={"message": "noop"})
    assert resp.status_code == 409


def test_commit_endpoint_empty_message_400(client: TestClient, opened_project: Path) -> None:
    (opened_project / "x.txt").write_text("x", encoding="utf-8")
    resp = client.post("/api/git/commit", json={"message": ""})
    assert resp.status_code in (400, 422)


def test_log_endpoint_returns_commits(client: TestClient, opened_project: Path) -> None:
    """GET /api/git/log returns the seeded initial commit."""
    resp = client.get("/api/git/log")
    assert resp.status_code == 200
    entries = resp.json()
    # auto-init produces one initial commit + workflows/main.yaml scaffold
    assert len(entries) >= 1


def test_log_endpoint_respects_limit(client: TestClient, opened_project: Path) -> None:
    # Create some additional commits.
    for i in range(3):
        (opened_project / f"file{i}.txt").write_text(str(i), encoding="utf-8")
        client.post("/api/git/commit", json={"message": f"c{i}"})
    resp = client.get("/api/git/log", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_log_endpoint_includes_remote_and_tag_refs(client: TestClient, opened_project: Path) -> None:
    """Hotfix #1011: log surfaces refs/remotes/ + refs/tags/, not only local.

    Before the fix, a commit only known via a remote-tracking ref or a
    tag came back with `branches: []` — the frontend then had no chip to
    render and the orphan dot looked like an unlabelled "broken head".
    """
    import subprocess

    (opened_project / "tagged.txt").write_text("x", encoding="utf-8")
    sha = client.post("/api/git/commit", json={"message": "for tag"}).json()["commit_sha"]
    subprocess.run(
        ["git", "-C", str(opened_project), "tag", "v0.1.0", sha],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(opened_project),
            "update-ref",
            "refs/remotes/origin/synthetic-branch",
            sha,
        ],
        check=True,
        capture_output=True,
    )
    resp = client.get("/api/git/log")
    assert resp.status_code == 200
    entry = next(c for c in resp.json() if c["sha"] == sha)
    refs = entry["branches"]
    assert "v0.1.0" in refs, refs
    assert "origin/synthetic-branch" in refs, refs


def test_log_endpoint_default_is_unbounded(client: TestClient, opened_project: Path) -> None:
    """Hotfix #1010: default `limit` is None (no cap), not 500.

    The 500 cap silently truncated dev histories. Verify that omitting the
    `limit` query parameter returns more rows than 500 when the repo has
    more commits — emulated here by creating 6 commits and asserting all
    of them come back (seed initial + 6 = 7 >= 6).
    """
    for i in range(6):
        (opened_project / f"f{i}.txt").write_text(str(i), encoding="utf-8")
        client.post("/api/git/commit", json={"message": f"c{i}"})
    resp = client.get("/api/git/log")
    assert resp.status_code == 200
    entries = resp.json()
    # 1 seed commit + 6 added = 7
    assert len(entries) >= 7


def test_diff_endpoint_commit_to_working(client: TestClient, opened_project: Path) -> None:
    (opened_project / "a.txt").write_text("one", encoding="utf-8")
    sha = client.post("/api/git/commit", json={"message": "v1"}).json()["commit_sha"]
    (opened_project / "a.txt").write_text("two", encoding="utf-8")
    resp = client.get("/api/git/diff", params={"from": sha, "to": "WORKING", "file": "a.txt"})
    assert resp.status_code == 200
    diff_text = resp.json()["diff"]
    assert "one" in diff_text or "two" in diff_text


def test_diff_endpoint_404_on_bad_sha(client: TestClient, opened_project: Path) -> None:
    resp = client.get("/api/git/diff", params={"from": "deadbeef" * 5, "to": "WORKING"})
    assert resp.status_code in (404, 500)


def test_restore_endpoint_soft_restore(client: TestClient, opened_project: Path) -> None:
    target = opened_project / "file.yaml"
    target.write_text("A", encoding="utf-8")
    sha_a = client.post("/api/git/commit", json={"message": "A"}).json()["commit_sha"]
    target.write_text("B", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "B"})
    # Restore to sha_a; HEAD remains at B but file content reverts.
    resp = client.post("/api/git/restore", json={"commit_sha": sha_a, "files": ["file.yaml"]})
    assert resp.status_code == 200
    body = resp.json()
    # ADR-039 Addendum 1 (#1354): the response now carries an explicit
    # `auto_commit_sha` field (null on a clean tree).
    assert body["status"] == "ok"
    assert body["auto_commit_sha"] is None
    assert target.read_text(encoding="utf-8") == "A"


def test_restore_endpoint_auto_commits_dirty_tree(client: TestClient, opened_project: Path) -> None:
    """ADR-039 Addendum 1 (#1354): when the working tree is dirty and
    the target file differs from the current working-tree content (so
    hotfix #997 does NOT short-circuit), ``/restore`` auto-commits the
    dirty content first via ``engine.commit(prefix="auto", ...)`` and
    returns the new SHA in ``auto_commit_sha``. The auto-commit
    subject must start with ``auto: pre-restore @``.
    """
    target = opened_project / "file.yaml"
    target.write_text("A", encoding="utf-8")
    sha_a = client.post("/api/git/commit", json={"message": "A"}).json()["commit_sha"]
    target.write_text("B", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "B"})

    # Dirty `file.yaml` itself so the hotfix #997 short-circuit cannot
    # kick in (the target diverges from both worktree AND sha_a's
    # content). Now restore to sha_a.
    target.write_text("DIRTY-WIP", encoding="utf-8")
    assert client.get("/api/git/status").json()["dirty"] is True

    resp = client.post(
        "/api/git/restore",
        json={"commit_sha": sha_a, "files": ["file.yaml"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    auto_sha = body["auto_commit_sha"]
    assert auto_sha is not None and isinstance(auto_sha, str)
    assert len(auto_sha) == 40

    # Confirm the auto: pre-restore commit sits on HEAD's history.
    log = client.get("/api/git/log", params={"limit": 5}).json()
    head_subject = log[0]["subject"]
    assert head_subject.startswith("auto: pre-restore @"), head_subject
    assert f"target={sha_a[:7]}" in head_subject

    # File content matches sha_a (the restore actually ran after the
    # auto-commit).
    assert target.read_text(encoding="utf-8") == "A"


def test_restore_endpoint_to_commit_missing_file_deletes_after_auto_commit(
    client: TestClient, opened_project: Path, runtime
) -> None:
    """Restoring a file to a commit that did not contain it means the
    file is deleted in the working tree, not a post-auto-commit failure.
    """
    _drain(client)
    sha_without_file = client.get("/api/git/log", params={"limit": 1}).json()[0]["sha"]
    target = opened_project / "workflows" / "added-later.yaml"
    target.write_text("workflow:\n  id: added-later\n  nodes: []\n  edges: []\n", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "add workflow"})

    target.write_text("workflow:\n  id: added-later\n  nodes: [{id: dirty}]\n  edges: []\n", encoding="utf-8")
    assert client.get("/api/git/status").json()["dirty"] is True
    captured = _subscribe_workflow_changed(runtime)

    resp = client.post(
        "/api/git/restore",
        json={"commit_sha": sha_without_file, "files": ["workflows/added-later.yaml"]},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["auto_commit_sha"]
    assert not target.exists()
    event = next(ev for ev in captured if ev.data["path"] == "workflows/added-later.yaml")
    assert event.data["kind"] == "deleted"


def test_restore_endpoint_clean_tree_no_auto_commit(client: TestClient, opened_project: Path) -> None:
    """A clean working tree at restore time produces ``auto_commit_sha=null``
    and no new commit on HEAD.
    """
    target = opened_project / "file.yaml"
    target.write_text("A", encoding="utf-8")
    sha_a = client.post("/api/git/commit", json={"message": "A"}).json()["commit_sha"]
    target.write_text("B", encoding="utf-8")
    sha_b = client.post("/api/git/commit", json={"message": "B"}).json()["commit_sha"]

    # Working tree is clean (just committed). Status check confirms.
    assert client.get("/api/git/status").json()["dirty"] is False

    resp = client.post(
        "/api/git/restore",
        json={"commit_sha": sha_a, "files": ["file.yaml"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["auto_commit_sha"] is None
    # HEAD unchanged.
    assert client.get("/api/git/log", params={"limit": 1}).json()[0]["sha"] == sha_b


def test_restore_skips_when_file_unchanged(client: TestClient, opened_project: Path) -> None:
    """Hotfix #997: ``engine.restore`` is a no-op when the target file
    content already matches the requested commit. Pre-fix, repeat
    clicks on Restore (e.g. while a different file was dirty)
    accumulated auto-handler entries that showed up in the graph as
    commit nodes and confused users.

    ADR-039 Addendum 1 (#1354): the route layer auto-commits ANY
    dirty tree before invoking ``engine.restore``, so the no-op
    measure is now: when the working tree is CLEAN and the target
    matches HEAD's content, the restore creates no new commit (no
    auto-commit because clean, no restore because unchanged). This
    test pins that contract.
    """
    _drain(client)
    target = opened_project / "file.yaml"
    target.write_text("A", encoding="utf-8")
    sha_a = client.post("/api/git/commit", json={"message": "A"}).json()["commit_sha"]

    # Clean tree — confirm before the restore.
    assert client.get("/api/git/status").json()["dirty"] is False

    head_before = client.get("/api/git/log", params={"limit": 1}).json()[0]["sha"]

    resp = client.post(
        "/api/git/restore",
        json={"commit_sha": sha_a, "files": ["file.yaml"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["auto_commit_sha"] is None  # clean tree → no auto-commit

    head_after = client.get("/api/git/log", params={"limit": 1}).json()[0]["sha"]
    assert head_after == head_before, (
        "Restore on a clean tree where target matches HEAD must not "
        "change HEAD (hotfix #997 short-circuit still applies)."
    )
    # File content unchanged.
    assert target.read_text(encoding="utf-8") == "A"


# ---------------------------------------------------------------------------
# Branch endpoints
# ---------------------------------------------------------------------------


def test_branches_endpoint_lists_default(client: TestClient, opened_project: Path) -> None:
    resp = client.get("/api/git/branches")
    assert resp.status_code == 200
    branches = resp.json()
    names = [b["name"] for b in branches]
    assert "main" in names
    main = next(b for b in branches if b["name"] == "main")
    assert main["is_current"] is True


def test_branch_create_endpoint(client: TestClient, opened_project: Path) -> None:
    resp = client.post("/api/git/branch/create", json={"name": "feature"})
    assert resp.status_code == 200, resp.text
    assert "feature" in [b["name"] for b in client.get("/api/git/branches").json()]


def test_branch_switch_endpoint(client: TestClient, opened_project: Path) -> None:
    # Ensure a clean tree first — the opened_project fixture may have
    # residual untracked state (metadata.db etc).
    _drain(client)
    client.post("/api/git/branch/create", json={"name": "feature"})
    resp = client.post("/api/git/branch/switch", json={"branch_name": "feature"})
    assert resp.status_code == 200
    body = resp.json()
    # ADR-039 Addendum 1 (#1354): the response carries `auto_commit_sha`
    # (null on a clean tree).
    assert body["current_branch"] == "feature"
    assert body["auto_commit_sha"] is None
    branches = client.get("/api/git/branches").json()
    current = next(b for b in branches if b["is_current"])
    assert current["name"] == "feature"


def test_branch_switch_auto_commits_dirty_tree(client: TestClient, opened_project: Path) -> None:
    """ADR-039 Addendum 1 (#1354): a branch switch with a dirty working
    tree auto-commits the dirty content first via
    ``engine.commit(prefix="auto", message="pre-switch @ ...")`` and
    only then runs ``git checkout <branch>``. The pre-addendum behavior
    was a raw "your local changes would be overwritten" error.
    """
    main_yaml = opened_project / "workflows" / "main.yaml"
    if not main_yaml.exists():
        main_yaml.parent.mkdir(parents=True, exist_ok=True)
        main_yaml.write_text("v: 1\n", encoding="utf-8")
        client.post("/api/git/commit", json={"message": "init main"})

    # Create a feature branch with a different main.yaml content.
    client.post("/api/git/branch/create", json={"name": "feature"})
    client.post("/api/git/branch/switch", json={"branch_name": "feature"})
    main_yaml.write_text("v: feature\n", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "feature v"})

    # Switch back to main (clean — pre-warm).
    client.post("/api/git/branch/switch", json={"branch_name": "main"})

    # Now make main dirty in a way that conflicts with feature's
    # main.yaml — switching back to feature would otherwise fail.
    main_yaml.write_text("v: WIP\n", encoding="utf-8")
    assert client.get("/api/git/status").json()["dirty"] is True

    resp = client.post("/api/git/branch/switch", json={"branch_name": "feature"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current_branch"] == "feature"
    auto_sha = body["auto_commit_sha"]
    assert auto_sha is not None
    assert isinstance(auto_sha, str) and len(auto_sha) == 40

    # The auto: pre-switch commit landed on `main` (the old branch).
    # Switching back to main, that commit must be at the tip.
    client.post("/api/git/branch/switch", json={"branch_name": "main"})
    main_log = client.get("/api/git/log", params={"branch": "main", "limit": 5}).json()
    head_subject = main_log[0]["subject"]
    assert head_subject.startswith("auto: pre-switch @"), head_subject
    assert "from=main" in head_subject and "to=feature" in head_subject


def test_branch_switch_rejects_unknown_branch_without_mutating_history(
    client: TestClient, opened_project: Path
) -> None:
    """Codex P1 on PR #1378: validate the target branch exists BEFORE
    creating the auto-commit. Pre-fix, a stale/invalid branch name
    would cause an ``auto: pre-switch`` commit to land on the OLD
    branch *and* the endpoint to return an error — non-atomic.
    """
    _drain(client)
    main_yaml = opened_project / "workflows" / "main.yaml"
    if not main_yaml.exists():
        main_yaml.parent.mkdir(parents=True, exist_ok=True)
        main_yaml.write_text("v: 1\n", encoding="utf-8")
        client.post("/api/git/commit", json={"message": "init"})

    head_before = client.get("/api/git/log", params={"limit": 1}).json()[0]["sha"]

    # Dirty the tree.
    main_yaml.write_text("v: WIP\n", encoding="utf-8")
    assert client.get("/api/git/status").json()["dirty"] is True

    resp = client.post(
        "/api/git/branch/switch",
        json={"branch_name": "nonexistent-branch"},
    )
    assert resp.status_code == 404

    # HEAD must NOT have advanced — no `auto: pre-switch` commit landed.
    head_after = client.get("/api/git/log", params={"limit": 1}).json()[0]["sha"]
    assert head_after == head_before, "branch_switch with an invalid target must not mutate history (Codex P1 #1378)."
    # The dirty content is still in the working tree.
    assert main_yaml.read_text(encoding="utf-8") == "v: WIP\n"


def test_restore_rejects_unknown_commit_without_mutating_history(client: TestClient, opened_project: Path) -> None:
    """Codex P2 on PR #1378: validate the restore target BEFORE creating
    the auto-commit. Pre-fix, an invalid commit_sha would mutate
    history with an `auto: pre-restore` commit *and* the endpoint
    would return an error — non-atomic.
    """
    _drain(client)
    target = opened_project / "file.yaml"
    target.write_text("A", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "A"})

    # Dirty the tree.
    target.write_text("WIP\n", encoding="utf-8")
    assert client.get("/api/git/status").json()["dirty"] is True

    head_before = client.get("/api/git/log", params={"limit": 1}).json()[0]["sha"]

    # Try restore with an unknown SHA.
    resp = client.post(
        "/api/git/restore",
        json={"commit_sha": "deadbeef" * 5, "files": ["file.yaml"]},
    )
    assert resp.status_code in (404, 500)

    head_after = client.get("/api/git/log", params={"limit": 1}).json()[0]["sha"]
    assert head_after == head_before, "restore with an invalid commit_sha must not mutate history (Codex P2 #1378)."
    # Dirty content preserved.
    assert target.read_text(encoding="utf-8") == "WIP\n"


# ---------------------------------------------------------------------------
# Hotfix #988: tree-mutating endpoints emit workflow.changed per file.
#
# Rationale (see ``_snapshot_workflows`` docstring in routes/git.py): the
# filesystem watcher is unreliable for bulk file rewrites that a git op
# completes inside a debounce window. The endpoints actively diff workflow
# YAMLs pre/post-op and emit ``workflow.changed`` per changed file so the
# frontend's existing ``workflow.changed`` handler reloads the canvas.
# These tests pin the contract end-to-end via the runtime's event bus.
# ---------------------------------------------------------------------------


def _subscribe_workflow_changed(runtime) -> list:
    captured: list = []
    runtime.event_bus.subscribe(WORKFLOW_CHANGED, lambda ev: captured.append(ev))
    return captured


def test_branch_switch_emits_workflow_changed_per_modified_yaml(
    client: TestClient, opened_project: Path, runtime
) -> None:
    """Hotfix #988: branch switch that rewrites workflows/main.yaml must emit
    ``workflow.changed`` so the canvas reloads. Failure mode pre-fix: the
    canvas kept showing the previous branch's YAML until manual reload.
    """
    main_yaml = opened_project / "workflows" / "main.yaml"
    main_yaml.write_text("workflow:\n  id: main\n  nodes: []\n  edges: []\n", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "main yaml v1"})
    client.post("/api/git/branch/create", json={"name": "feature"})
    client.post("/api/git/branch/switch", json={"branch_name": "feature"})
    # Diverge feature so a switch back to main actually rewrites the file.
    main_yaml.write_text(
        "workflow:\n  id: main\n  nodes: [{id: a}]\n  edges: []\n",
        encoding="utf-8",
    )
    client.post("/api/git/commit", json={"message": "feature yaml v2"})

    captured = _subscribe_workflow_changed(runtime)

    resp = client.post("/api/git/branch/switch", json={"branch_name": "main"})
    assert resp.status_code == 200

    # At least one event for workflows/main.yaml (modified — both branches
    # have the file but with different content).
    paths = [(ev.data["path"], ev.data["kind"]) for ev in captured]
    assert ("workflows/main.yaml", "modified") in paths
    # changed_by must be "git" so the frontend handler can disambiguate from
    # watcher-driven events if needed.
    main_event = next(ev for ev in captured if ev.data["path"] == "workflows/main.yaml")
    assert main_event.data["changed_by"] == "git"
    assert main_event.data["workflow_id"] == "main"


def test_branch_switch_no_yaml_change_emits_nothing(client: TestClient, opened_project: Path, runtime) -> None:
    """Switching to a branch with the same YAML content emits nothing.
    Diff-based emission must be quiet for no-op switches.
    """
    main_yaml = opened_project / "workflows" / "main.yaml"
    main_yaml.write_text("workflow:\n  id: main\n  nodes: []\n", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "v1"})
    client.post("/api/git/branch/create", json={"name": "twin"})
    # No edits on twin; immediately switch back.
    captured = _subscribe_workflow_changed(runtime)
    client.post("/api/git/branch/switch", json={"branch_name": "twin"})
    assert captured == []


def test_restore_endpoint_emits_workflow_changed(client: TestClient, opened_project: Path, runtime) -> None:
    """``/api/git/restore`` rewrites a workflow YAML → workflow.changed."""
    target = opened_project / "workflows" / "main.yaml"
    target.write_text("workflow:\n  id: main\n  v: 1\n", encoding="utf-8")
    sha_a = client.post("/api/git/commit", json={"message": "A"}).json()["commit_sha"]
    target.write_text("workflow:\n  id: main\n  v: 2\n", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "B"})

    captured = _subscribe_workflow_changed(runtime)
    resp = client.post(
        "/api/git/restore",
        json={"commit_sha": sha_a, "files": ["workflows/main.yaml"]},
    )
    assert resp.status_code == 200
    paths = [ev.data["path"] for ev in captured]
    assert "workflows/main.yaml" in paths
    main_event = next(ev for ev in captured if ev.data["path"] == "workflows/main.yaml")
    assert main_event.data["entity_class"] == "workflow"
    assert main_event.data["entity_id"] == "main"
    assert isinstance(main_event.data["version"], int)
    assert main_event.data["source"] == "gitRestore"
    assert main_event.data["source_id"] == sha_a
    assert main_event.data["kind"] == "modified"
    assert main_event.data["timestamp"]


def test_branch_switch_emits_created_for_new_yaml(client: TestClient, opened_project: Path, runtime) -> None:
    """When the target branch has a workflow YAML that the source branch
    doesn't, the switch must emit ``kind=created`` so the frontend opens
    a new tab for it.
    """
    # Start on main; commit baseline (only main.yaml from project init).
    main_yaml = opened_project / "workflows" / "main.yaml"
    if not main_yaml.exists():
        main_yaml.write_text("workflow:\n  id: main\n  nodes: []\n", encoding="utf-8")
        client.post("/api/git/commit", json={"message": "init main"})
    client.post("/api/git/branch/create", json={"name": "feature"})
    client.post("/api/git/branch/switch", json={"branch_name": "feature"})
    extra = opened_project / "workflows" / "extra.yaml"
    extra.write_text("workflow:\n  id: extra\n  nodes: []\n", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "add extra"})

    captured = _subscribe_workflow_changed(runtime)
    client.post("/api/git/branch/switch", json={"branch_name": "main"})
    # extra.yaml exists on feature but not main — switch to main = deleted.
    events = {(ev.data["path"], ev.data["kind"]) for ev in captured}
    assert ("workflows/extra.yaml", "deleted") in events


def test_branch_delete_endpoint(client: TestClient, opened_project: Path) -> None:
    """ADR-039 Addendum 1 §11.4 row #1356 — auto-tag safety net.

    Setup: create a feature branch with a unique tip commit, insert a
    ``runs`` row whose ``workflow_git_commit`` points at that tip, then
    delete the branch via the REST endpoint. Expectation:

    1. The delete succeeds (status 200).
    2. The feature branch is gone from ``/api/git/branches``.
    3. A ``refs/scistudio/lineage/<tip-sha>`` ref exists pointing at the
       formerly-orphan commit, so the SHA is still reachable.
    """
    import subprocess

    from scistudio.core.lineage.record import RunRecord

    # Drain any residual untracked state.
    if client.get("/api/git/status").json()["dirty"]:
        client.post("/api/git/commit", json={"message": "drain"})

    # Create feature branch with a unique tip commit.
    client.post("/api/git/branch/create", json={"name": "feature"})
    client.post("/api/git/branch/switch", json={"branch_name": "feature"})
    (opened_project / "feature_only.txt").write_text("D", encoding="utf-8")
    feature_tip_sha = client.post("/api/git/commit", json={"message": "feature tip"}).json()["commit_sha"]
    client.post("/api/git/branch/switch", json={"branch_name": "main"})

    # Insert a lineage row that references the feature tip.
    runtime = client.app.state.runtime
    runtime.lineage_store.insert_run(
        RunRecord(
            run_id="run-1356",
            workflow_id="wf-1356",
            workflow_git_commit=feature_tip_sha,
            workflow_yaml_snapshot="id: wf-1356\n",
            workflow_dirty=False,
            started_at="2026-05-21T00:00:00Z",
            finished_at="2026-05-21T00:00:01Z",
            status="completed",
            environment_snapshot={
                "python_version": "3.13.0",
                "platform": "test",
                "key_packages": {},
            },
            triggered_by="test",
            parent_run_id=None,
            execute_from_block_id=None,
            user_notes=None,
        )
    )

    # Delete via REST. We use force=true because the feature branch
    # diverged from main (that's the precondition for orphan candidates);
    # plain ``git branch -d`` refuses unmerged branches.
    resp = client.delete("/api/git/branches/feature?force=true")
    assert resp.status_code == 200, resp.text

    # Branch is gone.
    names = [b["name"] for b in client.get("/api/git/branches").json()]
    assert "feature" not in names

    # The lineage-pinning ref exists and resolves to the formerly-orphan SHA.
    ref_name = f"refs/scistudio/lineage/{feature_tip_sha}"
    rev = subprocess.run(
        ["git", "-C", str(opened_project), "rev-parse", ref_name],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rev.returncode == 0, f"lineage ref missing: {rev.stderr}"
    assert rev.stdout.strip() == feature_tip_sha


def test_branch_delete_endpoint_no_lineage_reference_leaves_no_refs(client: TestClient, opened_project: Path) -> None:
    """Clean delete (no lineage reference) creates no ``refs/scistudio/lineage/*``."""
    import subprocess

    if client.get("/api/git/status").json()["dirty"]:
        client.post("/api/git/commit", json={"message": "drain"})

    client.post("/api/git/branch/create", json={"name": "temp"})
    client.post("/api/git/branch/switch", json={"branch_name": "temp"})
    (opened_project / "temp_only.txt").write_text("x", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "temp tip"})
    client.post("/api/git/branch/switch", json={"branch_name": "main"})

    # No RunRecord referencing the tip — safety net should pin nothing.
    resp = client.delete("/api/git/branches/temp?force=true")
    assert resp.status_code == 200, resp.text

    # Verify no refs/scistudio/lineage/* exist.
    proc = subprocess.run(
        ["git", "-C", str(opened_project), "for-each-ref", "--format=%(refname)", "refs/scistudio/"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "", f"safety net created refs without a lineage reference: {proc.stdout!r}"


def test_branch_delete_endpoint_safety_net_keeps_sha_reachable(client: TestClient, opened_project: Path) -> None:
    """After branch delete + safety-net pin, the SHA can still be diffed/restored.

    This is the end-state guarantee: the Lineage tab's "Restore this
    run's workflow" path resolves ``runs.workflow_git_commit`` via
    plain ``git`` — as long as the SHA is reachable (via any ref), the
    restore endpoint works.
    """
    import subprocess

    from scistudio.core.lineage.record import RunRecord

    if client.get("/api/git/status").json()["dirty"]:
        client.post("/api/git/commit", json={"message": "drain"})

    client.post("/api/git/branch/create", json={"name": "feature"})
    client.post("/api/git/branch/switch", json={"branch_name": "feature"})
    (opened_project / "workflows" / "kept.yaml").write_text("id: kept\nnodes: []\n", encoding="utf-8")
    feature_tip_sha = client.post("/api/git/commit", json={"message": "feature tip"}).json()["commit_sha"]
    client.post("/api/git/branch/switch", json={"branch_name": "main"})

    runtime = client.app.state.runtime
    runtime.lineage_store.insert_run(
        RunRecord(
            run_id="run-1356-restore",
            workflow_id="wf-1356-restore",
            workflow_git_commit=feature_tip_sha,
            workflow_yaml_snapshot="id: wf-1356-restore\n",
            workflow_dirty=False,
            started_at="2026-05-21T00:00:00Z",
            finished_at="2026-05-21T00:00:01Z",
            status="completed",
            environment_snapshot={
                "python_version": "3.13.0",
                "platform": "test",
                "key_packages": {},
            },
            triggered_by="test",
            parent_run_id=None,
            execute_from_block_id=None,
            user_notes=None,
        )
    )

    # Delete the branch (force=true because feature diverged from main).
    assert client.delete("/api/git/branches/feature?force=true").status_code == 200

    # SHA must still resolve through plain git after the delete — this
    # is what the lineage Restore path depends on.
    rev = subprocess.run(
        ["git", "-C", str(opened_project), "cat-file", "-e", feature_tip_sha],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rev.returncode == 0, "orphan SHA is no longer reachable"


def test_branch_delete_current_409(client: TestClient, opened_project: Path) -> None:
    resp = client.delete("/api/git/branches/main")
    assert resp.status_code == 409


def test_branch_delete_failed_delete_creates_no_lineage_refs(client: TestClient, opened_project: Path) -> None:
    """Codex P2 on PR #1381 — pins must NOT be created when delete fails.

    Setup a divergent feature branch with a lineage-referenced tip, but
    delete WITHOUT force=true. Git refuses to delete the unmerged branch
    (returns 500 via GitError). The safety net must leave the repository
    in its original state: no ``refs/scistudio/lineage/*`` refs created.
    """
    import subprocess

    from scistudio.core.lineage.record import RunRecord

    if client.get("/api/git/status").json()["dirty"]:
        client.post("/api/git/commit", json={"message": "drain"})

    client.post("/api/git/branch/create", json={"name": "unmerged-feature"})
    client.post("/api/git/branch/switch", json={"branch_name": "unmerged-feature"})
    (opened_project / "unmerged.txt").write_text("D", encoding="utf-8")
    feature_tip_sha = client.post("/api/git/commit", json={"message": "feature tip"}).json()["commit_sha"]
    client.post("/api/git/branch/switch", json={"branch_name": "main"})

    runtime = client.app.state.runtime
    runtime.lineage_store.insert_run(
        RunRecord(
            run_id="run-1356-p2",
            workflow_id="wf-1356-p2",
            workflow_git_commit=feature_tip_sha,
            workflow_yaml_snapshot="id: wf-1356-p2\n",
            workflow_dirty=False,
            started_at="2026-05-21T00:00:00Z",
            finished_at="2026-05-21T00:00:01Z",
            status="completed",
            environment_snapshot={
                "python_version": "3.13.0",
                "platform": "test",
                "key_packages": {},
            },
            triggered_by="test",
            parent_run_id=None,
            execute_from_block_id=None,
            user_notes=None,
        )
    )

    # Delete WITHOUT force — git refuses unmerged branches.
    resp = client.delete("/api/git/branches/unmerged-feature")
    assert resp.status_code != 200, (
        "Expected non-200 from unmerged delete without force; got 200 — the route may be silently force-deleting."
    )

    # The branch must still exist (delete failed).
    names = [b["name"] for b in client.get("/api/git/branches").json()]
    assert "unmerged-feature" in names

    # NO refs/scistudio/lineage/* refs may have been created — Phase 1/2/3
    # ordering guarantees we never pin without a successful delete.
    proc = subprocess.run(
        ["git", "-C", str(opened_project), "for-each-ref", "--format=%(refname)", "refs/scistudio/"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "", f"safety net wrote refs even though branch_delete failed: {proc.stdout!r}"


# NOTE: Codex P1 (PR #1381) "fully-qualified refname avoids tag/branch
# collision" is unit-tested at the engine layer in
# tests/core/test_git_engine.py::test_commits_reachable_only_from_disambiguates_branch_vs_tag.
# A pre-existing engine.branches() short-form quirk (when a tag shares a
# branch's short name, for-each-ref --format=%(refname:short) returns
# "heads/<name>" instead of "<name>") makes the route-layer
# branch_switch validation reject the colliding branch name as 404,
# preventing this scenario from being exercised cleanly through the
# REST surface in a single test. The engine-layer test is sufficient
# because the route just delegates to engine.commits_reachable_only_from.


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def test_status_endpoint_reports_clean(client: TestClient, opened_project: Path) -> None:
    # Note: a freshly opened project may have residual untracked
    # per-machine state (e.g. metadata.db from ADR-032) that the default
    # .gitignore does not cover. The endpoint contract is "returns
    # current state", so we assert shape rather than emptiness.
    resp = client.get("/api/git/status")
    assert resp.status_code == 200
    s = resp.json()
    assert isinstance(s["dirty"], bool)
    assert isinstance(s["modified"], list)
    assert isinstance(s["untracked"], list)


def test_status_endpoint_reports_dirty(client: TestClient, opened_project: Path) -> None:
    (opened_project / "fresh.txt").write_text("x", encoding="utf-8")
    s = client.get("/api/git/status").json()
    assert s["dirty"] is True
    assert "fresh.txt" in s["untracked"]


# ---------------------------------------------------------------------------
# Merge / cherry-pick
# ---------------------------------------------------------------------------


def _drain(client: TestClient) -> None:
    """Commit any residual untracked working-tree state."""
    if client.get("/api/git/status").json()["dirty"]:
        client.post("/api/git/commit", json={"message": "drain"})


def test_merge_endpoint_fast_forward(client: TestClient, opened_project: Path) -> None:
    _drain(client)
    client.post("/api/git/branch/create", json={"name": "feature"})
    client.post("/api/git/branch/switch", json={"branch_name": "feature"})
    (opened_project / "b.txt").write_text("b", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "add b on feature"})
    client.post("/api/git/branch/switch", json={"branch_name": "main"})
    resp = client.post("/api/git/merge", json={"source_branch": "feature"})
    assert resp.status_code == 200
    assert resp.json()["result"] == "fast-forward"


def test_merge_endpoint_conflict(client: TestClient, opened_project: Path) -> None:
    target = opened_project / "a.txt"
    target.write_text("base\n", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "baseline"})
    client.post("/api/git/branch/create", json={"name": "feature"})
    client.post("/api/git/branch/switch", json={"branch_name": "feature"})
    target.write_text("FEATURE\n", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "feat"})
    client.post("/api/git/branch/switch", json={"branch_name": "main"})
    target.write_text("MAIN\n", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "main"})
    resp = client.post("/api/git/merge", json={"source_branch": "feature"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["result"] == "conflict"
    assert "a.txt" in payload["conflicted_files"]
    # Cleanup.
    client.post("/api/git/merge/abort")


def test_cherry_pick_endpoint_clean(client: TestClient, opened_project: Path) -> None:
    (opened_project / "a.txt").write_text("a", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "add a"})
    client.post("/api/git/branch/create", json={"name": "feature"})
    client.post("/api/git/branch/switch", json={"branch_name": "feature"})
    (opened_project / "b.txt").write_text("b", encoding="utf-8")
    feat_sha = client.post("/api/git/commit", json={"message": "feat b"}).json()["commit_sha"]
    client.post("/api/git/branch/switch", json={"branch_name": "main"})
    resp = client.post("/api/git/cherry-pick", json={"commit_sha": feat_sha})
    assert resp.status_code == 200
    assert resp.json()["result"] == "clean"


# ---------------------------------------------------------------------------
# Conflict-resolution finalization
# ---------------------------------------------------------------------------


def _setup_conflict(client: TestClient, opened_project: Path) -> None:
    target = opened_project / "a.txt"
    target.write_text("base\n", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "baseline"})
    client.post("/api/git/branch/create", json={"name": "feature"})
    client.post("/api/git/branch/switch", json={"branch_name": "feature"})
    target.write_text("FEATURE\n", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "feat"})
    client.post("/api/git/branch/switch", json={"branch_name": "main"})
    target.write_text("MAIN\n", encoding="utf-8")
    client.post("/api/git/commit", json={"message": "main"})
    client.post("/api/git/merge", json={"source_branch": "feature"})


def test_merge_stage_file_endpoint(client: TestClient, opened_project: Path) -> None:
    _setup_conflict(client, opened_project)
    (opened_project / "a.txt").write_text("RESOLVED\n", encoding="utf-8")
    resp = client.post("/api/git/merge/stage-file", json={"file": "a.txt"})
    assert resp.status_code == 200
    client.post("/api/git/merge/complete")


def test_merge_complete_endpoint(client: TestClient, opened_project: Path) -> None:
    _setup_conflict(client, opened_project)
    (opened_project / "a.txt").write_text("RESOLVED\n", encoding="utf-8")
    client.post("/api/git/merge/stage-file", json={"file": "a.txt"})
    resp = client.post("/api/git/merge/complete")
    assert resp.status_code == 200
    assert resp.json()["commit_sha"]


def test_merge_abort_endpoint(client: TestClient, opened_project: Path) -> None:
    _setup_conflict(client, opened_project)
    resp = client.post("/api/git/merge/abort")
    assert resp.status_code == 200


def test_merge_abort_no_op_409(client: TestClient, opened_project: Path) -> None:
    resp = client.post("/api/git/merge/abort")
    assert resp.status_code == 409


def test_no_active_project_409(client: TestClient) -> None:
    """All endpoints return 409 when no project is active."""
    resp = client.get("/api/git/status")
    assert resp.status_code == 409
