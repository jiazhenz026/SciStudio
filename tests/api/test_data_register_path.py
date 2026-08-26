"""Tests for ``POST /api/data/register-path`` (#2112).

The endpoint registers a file already inside a project (e.g.
``data/foo.parquet``) into the data catalog so the data-preview tab can open
it through the standard routed preview session API.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime


def _write_parquet(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"a": [1, 2], "b": ["x", "y"]}), path)


def test_register_path_parquet_infers_dataframe(client: TestClient, opened_project: Path) -> None:
    """A project-relative parquet path registers as a DataFrame."""
    target = opened_project / "data" / "table.parquet"
    _write_parquet(target)

    resp = client.post("/api/data/register-path", json={"path": "data/table.parquet"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ref"].startswith("data-")
    assert body["recorded_type"] == "DataFrame"
    assert body["type_chain"] == ["DataFrame"]
    assert body["display_name"] == "table.parquet"


def test_register_path_unknown_extension_infers_artifact(client: TestClient, opened_project: Path) -> None:
    """An unknown suffix falls back to Artifact via the extension heuristic."""
    target = opened_project / "data" / "blob.xyz"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\x00\x01\x02")

    resp = client.post("/api/data/register-path", json={"path": "data/blob.xyz"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["recorded_type"] == "Artifact"
    assert resp.json()["type_chain"] == ["Artifact"]


def test_register_path_accepts_absolute_path_inside_project(client: TestClient, opened_project: Path) -> None:
    """An absolute path is accepted when it resolves inside the project root."""
    target = opened_project / "data" / "notes.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("hello", encoding="utf-8")

    resp = client.post("/api/data/register-path", json={"path": str(target)})
    assert resp.status_code == 200, resp.text
    assert resp.json()["recorded_type"] == "Text"


def test_register_path_with_explicit_project_id(client: TestClient, runtime: ApiRuntime, opened_project: Path) -> None:
    """``project_id`` selects the project instead of the active one."""
    target = opened_project / "data" / "explicit.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("hi", encoding="utf-8")
    project = runtime.active_project
    assert project is not None

    resp = client.post("/api/data/register-path", json={"project_id": project.id, "path": "data/explicit.txt"})
    assert resp.status_code == 200, resp.text


def test_register_path_unknown_project_id_404(client: TestClient, opened_project: Path) -> None:
    resp = client.post("/api/data/register-path", json={"project_id": "nope", "path": "data/x.csv"})
    assert resp.status_code == 404


def test_register_path_traversal_rejected(client: TestClient, opened_project: Path) -> None:
    """Relative ``..`` escapes and out-of-root absolute paths are refused."""
    outside = opened_project.parent / "secret.txt"
    outside.write_text("nope", encoding="utf-8")

    resp = client.post("/api/data/register-path", json={"path": "../secret.txt"})
    assert resp.status_code == 403

    resp_abs = client.post("/api/data/register-path", json={"path": str(outside)})
    assert resp_abs.status_code == 403


def test_register_path_missing_file_404(client: TestClient, opened_project: Path) -> None:
    resp = client.post("/api/data/register-path", json={"path": "data/missing.csv"})
    assert resp.status_code == 404


def test_registered_ref_opens_preview_session(client: TestClient, opened_project: Path) -> None:
    """The returned ref is directly consumable by POST /api/previews/sessions."""
    target = opened_project / "data" / "table.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")

    registered = client.post("/api/data/register-path", json={"path": "data/table.csv"})
    assert registered.status_code == 200, registered.text
    ref = registered.json()["ref"]

    session = client.post(
        "/api/previews/sessions",
        json={"target": {"kind": "data_ref", "ref": ref}, "query": {}},
    )
    assert session.status_code == 200, session.text
    assert session.json()["kind"] == "dataframe"
    assert session.json()["payload"]["total_rows"] == 2
