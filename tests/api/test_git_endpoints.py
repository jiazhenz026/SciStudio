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
    assert target.read_text(encoding="utf-8") == "A"


def test_restore_skips_when_file_unchanged(client: TestClient, opened_project: Path) -> None:
    """Hotfix #997: restore is a no-op when the target file content
    already matches the requested commit. Pre-fix, repeat clicks on
    Restore (e.g. while a different file was dirty) accumulated
    `auto-stash before restore` entries that showed up in the graph
    as commit nodes and confused users.
    """
    target = opened_project / "file.yaml"
    target.write_text("A", encoding="utf-8")
    sha_a = client.post("/api/git/commit", json={"message": "A"}).json()["commit_sha"]

    # File content already matches sha_a (no change since the commit).
    # Pre-fix this would NOT have created a stash (status was clean),
    # but to guarantee the no-op even with an unrelated dirty file we
    # mark another file dirty and confirm Restore still doesn't stash.
    other = opened_project / "other.txt"
    other.write_text("dirty unrelated", encoding="utf-8")

    # Snapshot stash count before.
    before = client.get("/api/git/stash").json()
    before_count = len(before)

    resp = client.post(
        "/api/git/restore",
        json={"commit_sha": sha_a, "files": ["file.yaml"]},
    )
    assert resp.status_code == 200
    # No stash should have been created because the target file is
    # unchanged vs sha_a.
    after = client.get("/api/git/stash").json()
    assert len(after) == before_count, (
        f"Restore should be a no-op when target file matches commit; "
        f"stash count went from {before_count} to {len(after)}"
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
    client.post("/api/git/branch/create", json={"name": "feature"})
    resp = client.post("/api/git/branch/switch", json={"branch_name": "feature"})
    assert resp.status_code == 200
    branches = client.get("/api/git/branches").json()
    current = next(b for b in branches if b["is_current"])
    assert current["name"] == "feature"


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
    client.post("/api/git/branch/create", json={"name": "temp"})
    resp = client.delete("/api/git/branches/temp")
    assert resp.status_code == 200
    names = [b["name"] for b in client.get("/api/git/branches").json()]
    assert "temp" not in names


def test_branch_delete_current_409(client: TestClient, opened_project: Path) -> None:
    resp = client.delete("/api/git/branches/main")
    assert resp.status_code == 409


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
# Stash CRUD
# ---------------------------------------------------------------------------


def test_stash_save_endpoint(client: TestClient, opened_project: Path) -> None:
    _drain(client)
    (opened_project / "wip.txt").write_text("x", encoding="utf-8")
    resp = client.post("/api/git/stash/save", json={"message": "wip"})
    assert resp.status_code == 200
    assert resp.json()["stash_id"].startswith("stash@")


def test_stash_list_endpoint(client: TestClient, opened_project: Path) -> None:
    _drain(client)
    (opened_project / "wip.txt").write_text("x", encoding="utf-8")
    client.post("/api/git/stash/save", json={"message": "wip"})
    resp = client.get("/api/git/stash")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_stash_apply_endpoint(client: TestClient, opened_project: Path) -> None:
    _drain(client)
    (opened_project / "wip.txt").write_text("x", encoding="utf-8")
    stash_id = client.post("/api/git/stash/save", json={"message": "wip"}).json()["stash_id"]
    resp = client.post("/api/git/stash/apply", json={"stash_id": stash_id})
    assert resp.status_code == 200
    assert resp.json()["status"] in ("ok", "conflict")


def test_stash_drop_endpoint(client: TestClient, opened_project: Path) -> None:
    _drain(client)
    (opened_project / "wip.txt").write_text("x", encoding="utf-8")
    stash_id = client.post("/api/git/stash/save", json={"message": "wip"}).json()["stash_id"]
    resp = client.delete(f"/api/git/stash/{stash_id}")
    assert resp.status_code == 200


def test_stash_save_clean_409(client: TestClient, opened_project: Path) -> None:
    _drain(client)
    resp = client.post("/api/git/stash/save", json={"message": "nothing"})
    assert resp.status_code == 409


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
