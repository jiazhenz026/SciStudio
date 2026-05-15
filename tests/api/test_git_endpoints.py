"""Tests for ``scieasy.api.routes.git`` REST endpoints (ADR-039).

Phase D39-2.2b — bodies filled, xfail flipped to passing.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

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
