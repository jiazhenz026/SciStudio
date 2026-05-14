"""ADR-036 §3.2 — file GET/PUT endpoint tests (Phase 2A I36a).

Covers the test plan documented in the skeleton's docstrings:
  - read happy path / 404 / 403 traversal / 415 ext / 413 size / 400 dir
  - write happy path / atomic / mark_self_write coordination / 413 / 403 / 415
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _open(client: TestClient, project_path: Path) -> str:
    """Create + open a project under ``project_path`` and return its id."""
    response = client.post(
        "/api/projects/",
        json={"name": "T", "description": "", "path": str(project_path)},
    )
    assert response.status_code == 200, response.text
    project_id = response.json()["id"]
    # Trigger open so the runtime tracks active_project (matches GUI flow).
    client.get(f"/api/projects/{project_id}")
    return project_id


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------


def test_read_file_happy_path(client: TestClient, project_parent: Path) -> None:
    pid = _open(client, project_parent / "p1")
    project_root = Path(client.app.state.runtime.known_projects[pid].path)
    blocks_dir = project_root / "blocks"
    blocks_dir.mkdir(exist_ok=True)
    target = blocks_dir / "foo.py"
    target.write_bytes(b"x = 1\n")

    r = client.get(f"/api/projects/{pid}/file?path=blocks/foo.py")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["content"] == "x = 1\n"
    assert body["encoding"] == "utf-8"
    assert body["size"] == 6
    assert body["mtime"] > 0


def test_read_file_404_missing(client: TestClient, project_parent: Path) -> None:
    pid = _open(client, project_parent / "p2")
    r = client.get(f"/api/projects/{pid}/file?path=blocks/missing.py")
    assert r.status_code == 404


def test_read_file_403_traversal(client: TestClient, project_parent: Path) -> None:
    pid = _open(client, project_parent / "p3")
    r = client.get(f"/api/projects/{pid}/file?path=../../etc/passwd.py")
    assert r.status_code == 403


def test_read_file_415_extension(client: TestClient, project_parent: Path) -> None:
    pid = _open(client, project_parent / "p4")
    project_root = Path(client.app.state.runtime.known_projects[pid].path)
    bad = project_root / "evil.exe"
    bad.write_bytes(b"\x00")
    r = client.get(f"/api/projects/{pid}/file?path=evil.exe")
    assert r.status_code == 415


def test_read_file_413_size(client: TestClient, project_parent: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """File exceeding the size cap returns 413.

    Lower the cap via monkeypatch so we don't have to write 10 MB to disk.
    """
    from scieasy.api.routes import projects

    monkeypatch.setattr(projects, "ADR036_FILE_SIZE_CAP_BYTES", 16)
    pid = _open(client, project_parent / "p5")
    project_root = Path(client.app.state.runtime.known_projects[pid].path)
    big = project_root / "big.py"
    big.write_text("x" * 32, encoding="utf-8")
    r = client.get(f"/api/projects/{pid}/file?path=big.py")
    assert r.status_code == 413


def test_read_file_400_directory(client: TestClient, project_parent: Path) -> None:
    pid = _open(client, project_parent / "p6")
    project_root = Path(client.app.state.runtime.known_projects[pid].path)
    # Use an allowlisted extension so we get past the 415 check and reach
    # the directory-vs-file branch.
    sub = project_root / "weird.py"
    sub.mkdir(exist_ok=True)
    r = client.get(f"/api/projects/{pid}/file?path=weird.py")
    assert r.status_code == 400


def test_read_file_400_empty_path(client: TestClient, project_parent: Path) -> None:
    pid = _open(client, project_parent / "p7")
    r = client.get(f"/api/projects/{pid}/file?path=")
    assert r.status_code == 400


def test_read_file_404_unknown_project(client: TestClient) -> None:
    r = client.get("/api/projects/no-such-project/file?path=foo.py")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# PUT
# ---------------------------------------------------------------------------


def test_write_file_happy_path(client: TestClient, project_parent: Path) -> None:
    pid = _open(client, project_parent / "w1")
    project_root = Path(client.app.state.runtime.known_projects[pid].path)
    blocks = project_root / "blocks"
    blocks.mkdir(exist_ok=True)
    target = blocks / "new.py"
    target.write_text("# old\n", encoding="utf-8")

    r = client.put(
        f"/api/projects/{pid}/file?path=blocks/new.py",
        json={"content": "print('hi')\n"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["size"] == len(b"print('hi')\n")
    assert target.read_text(encoding="utf-8") == "print('hi')\n"


def test_write_file_atomic(
    client: TestClient,
    project_parent: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If os.replace fails, the destination retains the OLD content."""
    pid = _open(client, project_parent / "w2")
    project_root = Path(client.app.state.runtime.known_projects[pid].path)
    target = project_root / "scratch.py"
    target.write_text("# original\n", encoding="utf-8")

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr("scieasy.api.routes.projects.os.replace", boom)

    r = client.put(
        f"/api/projects/{pid}/file?path=scratch.py",
        json={"content": "# new content\n"},
    )
    assert r.status_code == 500
    # Original content untouched
    assert target.read_text(encoding="utf-8") == "# original\n"
    # Make sure no tmpfile was leaked
    leftovers = [p for p in target.parent.iterdir() if p.name.startswith(".__scieasy_write_")]
    assert leftovers == []


def test_write_file_self_write_suppression(client: TestClient, project_parent: Path) -> None:
    """PUT calls ``mark_self_write`` so the watcher discards the echo event."""
    from scieasy.api.routes import workflow_watcher as ww

    captured: list[Path] = []

    class FakeWatcher:
        def mark_self_write(self, path: Path) -> None:
            captured.append(Path(path))

    ww.set_active_watcher(FakeWatcher())  # type: ignore[arg-type]
    try:
        pid = _open(client, project_parent / "w3")
        project_root = Path(client.app.state.runtime.known_projects[pid].path)
        target = project_root / "blocks"
        target.mkdir(exist_ok=True)
        r = client.put(
            f"/api/projects/{pid}/file?path=blocks/x.py",
            json={"content": "y = 2\n"},
        )
        assert r.status_code == 200, r.text
        # Should be invoked at least once with the destination path.
        assert any(p.name == "x.py" for p in captured), f"mark_self_write not called with x.py; captured={captured}"
    finally:
        ww.set_active_watcher(None)


def test_write_file_413_size(
    client: TestClient,
    project_parent: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scieasy.api.routes import projects

    monkeypatch.setattr(projects, "ADR036_FILE_SIZE_CAP_BYTES", 8)
    pid = _open(client, project_parent / "w4")
    project_root = Path(client.app.state.runtime.known_projects[pid].path)
    target = project_root / "big.py"
    # Confirm pre-state.
    assert not target.exists()
    r = client.put(
        f"/api/projects/{pid}/file?path=big.py",
        json={"content": "x" * 100},
    )
    assert r.status_code == 413
    # Disk untouched.
    assert not target.exists()


def test_write_file_403_traversal(client: TestClient, project_parent: Path) -> None:
    pid = _open(client, project_parent / "w5")
    r = client.put(
        f"/api/projects/{pid}/file?path=../escaped.py",
        json={"content": "x = 1\n"},
    )
    assert r.status_code == 403


def test_write_file_415_extension(client: TestClient, project_parent: Path) -> None:
    pid = _open(client, project_parent / "w6")
    r = client.put(
        f"/api/projects/{pid}/file?path=mal.exe",
        json={"content": "x"},
    )
    assert r.status_code == 415


def test_write_file_404_parent_missing(client: TestClient, project_parent: Path) -> None:
    pid = _open(client, project_parent / "w7")
    r = client.put(
        f"/api/projects/{pid}/file?path=nosuchdir/x.py",
        json={"content": "x = 1\n"},
    )
    assert r.status_code == 404
