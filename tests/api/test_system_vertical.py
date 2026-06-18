"""System-level vertical tests for user-visible workflow paths.

These tests intentionally cross API, scheduler, lineage, git, and websocket
boundaries.  They are broader than the existing focused route/unit coverage
and serve as executable evidence for issue #1486.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Any

from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime
from scistudio.blocks.base.state import BlockState
from scistudio.engine.events import BLOCK_DONE, BLOCK_READY, BLOCK_RUNNING, WORKFLOW_COMPLETED
from tests.api.helpers import build_linear_workflow, wait_for_condition, wait_for_workflow_completion


def _read_ws_frames(websocket: Any, out: Queue[dict[str, Any] | BaseException]) -> Thread:
    """Read frames in a daemon thread so tests can time out deterministically."""

    def _reader() -> None:
        try:
            while True:
                out.put(websocket.receive_json())
        except BaseException as exc:
            out.put(exc)

    thread = Thread(target=_reader, daemon=True)
    thread.start()
    return thread


def _collect_ws_until(
    frames_in: Queue[dict[str, Any] | BaseException],
    target_types: Iterable[str],
    *,
    timeout: float = 5.0,
) -> list[dict[str, Any]]:
    """Read websocket frames until every target type has appeared."""
    targets = set(target_types)
    frames: list[dict[str, Any]] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            item = frames_in.get(timeout=min(0.1, max(deadline - time.monotonic(), 0.0)))
        except Empty:
            continue
        if isinstance(item, BaseException):
            continue
        frame = item
        frames.append(frame)
        targets.discard(frame.get("type"))
        if not targets:
            return frames
    raise AssertionError(f"Timed out waiting for websocket events: {sorted(targets)}")


def _create_workflow(client: TestClient, opened_project: Path, workflow_id: str) -> dict[str, Any]:
    payload = build_linear_workflow(opened_project, workflow_id=workflow_id)
    response = client.post("/api/workflows/", json=payload)
    assert response.status_code == 200, response.text
    return payload


def test_execute_broadcasts_runtime_lifecycle_events_to_websocket(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """Execute via REST and observe scheduler lifecycle frames through /ws."""
    _create_workflow(client, opened_project, "vertical-ws-lifecycle")

    with client.websocket_connect("/ws") as websocket:
        frames_in: Queue[dict[str, Any] | BaseException] = Queue()
        _read_ws_frames(websocket, frames_in)
        response = client.post("/api/workflows/vertical-ws-lifecycle/execute")
        assert response.status_code == 200, response.text
        wait_for_workflow_completion(runtime, "vertical-ws-lifecycle")
        frames = _collect_ws_until(
            frames_in,
            [BLOCK_READY, BLOCK_RUNNING, BLOCK_DONE, WORKFLOW_COMPLETED],
        )

    by_type = {frame["type"] for frame in frames}
    assert {BLOCK_READY, BLOCK_RUNNING, BLOCK_DONE, WORKFLOW_COMPLETED}.issubset(by_type)
    assert any(frame.get("block_id") == "final" for frame in frames if frame["type"] == BLOCK_DONE)


def test_completed_run_lineage_outputs_are_previewable(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """A completed run should expose output objects that the preview API can read.

    #1486: previously xfail — the legacy one-shot preview route could not always
    resolve completed-run outputs. Under ADR-048 (#1604) the routed session API
    resolves the output ref's storage from the catalog (``enrich_preview_query``
    / ``resolve_session_target``) and renders a real (non-error) envelope.
    """
    _create_workflow(client, opened_project, "vertical-lineage-preview")

    assert client.post("/api/workflows/vertical-lineage-preview/execute").status_code == 200
    wait_for_workflow_completion(runtime, "vertical-lineage-preview")

    runs = client.get("/api/runs?workflow_id=vertical-lineage-preview")
    assert runs.status_code == 200, runs.text
    run_id = runs.json()["runs"][0]["run_id"]

    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200, detail.text
    blocks = detail.json()["block_executions"]
    output_ids = [
        output["object_id"] for block in blocks for output in block.get("outputs", []) if output.get("object_id")
    ]
    assert output_ids, "lineage detail should include previewable output object ids"

    # ADR-048 no-compat (#1604): preview through the routed session API (the
    # legacy GET /api/data/{ref}/preview adapter was removed). #1486 tracks
    # whether completed-run outputs resolve via the preview subsystem at all.
    session = client.post(
        "/api/previews/sessions",
        json={"target": {"kind": "data_ref", "ref": output_ids[0]}, "query": {}},
    )
    assert session.status_code == 200, session.text
    body = session.json()
    # The output resolves to a real preview envelope, not an error/unroutable one.
    assert body["kind"] != "error", body
    assert body.get("error") is None, body
    assert body["session_id"]


def test_git_restore_then_get_workflow_returns_restored_definition(
    client: TestClient,
    opened_project: Path,
) -> None:
    """Soft-restore a workflow YAML and confirm the public GET returns restored content."""
    payload = _create_workflow(client, opened_project, "vertical-git-restore")

    payload["description"] = "version A"
    update_a = client.put("/api/workflows/vertical-git-restore", json=payload)
    assert update_a.status_code == 200, update_a.text
    commit_a = client.post("/api/git/commit", json={"message": "version A"})
    assert commit_a.status_code == 200, commit_a.text
    sha_a = commit_a.json()["commit_sha"]

    payload["description"] = "version B"
    update_b = client.put("/api/workflows/vertical-git-restore", json=payload)
    assert update_b.status_code == 200, update_b.text
    commit_b = client.post("/api/git/commit", json={"message": "version B"})
    assert commit_b.status_code == 200, commit_b.text

    restore = client.post(
        "/api/git/restore",
        json={
            "commit_sha": sha_a,
            "files": ["workflows/vertical-git-restore.yaml"],
        },
    )
    assert restore.status_code == 200, restore.text

    fetched = client.get("/api/workflows/vertical-git-restore")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["description"] == "version A"


def test_multi_session_execute_broadcasts_terminal_state_and_get_matches(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """Two websocket sessions should both see completion and GET should match scheduler state."""
    _create_workflow(client, opened_project, "vertical-multi-session")

    with client.websocket_connect("/ws") as tab_a, client.websocket_connect("/ws") as tab_b:
        frames_a_in: Queue[dict[str, Any] | BaseException] = Queue()
        frames_b_in: Queue[dict[str, Any] | BaseException] = Queue()
        _read_ws_frames(tab_a, frames_a_in)
        _read_ws_frames(tab_b, frames_b_in)
        response = client.post("/api/workflows/vertical-multi-session/execute")
        assert response.status_code == 200, response.text
        run = wait_for_workflow_completion(runtime, "vertical-multi-session")
        frames_a = _collect_ws_until(frames_a_in, [WORKFLOW_COMPLETED])
        frames_b = _collect_ws_until(frames_b_in, [WORKFLOW_COMPLETED])

    assert frames_a[-1]["workflow_id"] == "vertical-multi-session"
    assert frames_b[-1]["workflow_id"] == "vertical-multi-session"
    assert run.scheduler.block_states()["final"] == BlockState.DONE

    fetched = client.get("/api/workflows/vertical-multi-session")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["id"] == "vertical-multi-session"


def test_execute_from_records_parent_run_and_websocket_completion(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """Run from a downstream block, then verify parent lineage and completion frame."""
    _create_workflow(client, opened_project, "vertical-execute-from")

    assert client.post("/api/workflows/vertical-execute-from/execute").status_code == 200
    wait_for_workflow_completion(runtime, "vertical-execute-from")

    with client.websocket_connect("/ws") as websocket:
        frames_in: Queue[dict[str, Any] | BaseException] = Queue()
        _read_ws_frames(websocket, frames_in)
        rerun = client.post("/api/workflows/vertical-execute-from/execute-from", json={"block_id": "final"})
        assert rerun.status_code == 200, rerun.text
        wait_for_workflow_completion(runtime, "vertical-execute-from")
        frames = _collect_ws_until(frames_in, [WORKFLOW_COMPLETED])

    assert frames[-1]["workflow_id"] == "vertical-execute-from"

    rows = wait_for_condition(
        lambda: (
            runtime.lineage_store
            and runtime.lineage_store.list_runs(
                workflow_id="vertical-execute-from",
                limit=5,
            )
        ),
        timeout=5.0,
    )
    assert len(rows) >= 2, rows
    partial, parent = rows[0], rows[1]
    assert partial["execute_from_block_id"] == "final"
    assert partial["parent_run_id"] == parent["run_id"]
