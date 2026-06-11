"""Tests for the filesystem browse endpoint (GET /api/filesystem/browse)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def browse_dir(tmp_path: Path) -> Path:
    """Create a small directory tree for testing."""
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "file_a.txt").write_text("hello")
    (tmp_path / "file_b.csv").write_text("a,b\n1,2")
    return tmp_path


class TestBrowseFilesystem:
    """GET /api/filesystem/browse?path=..."""

    def test_empty_path_returns_roots(self, client: TestClient) -> None:
        resp = client.get("/api/filesystem/browse", params={"path": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        # Should return at least one root entry
        assert len(data["entries"]) >= 1
        # All entries should be directories
        for entry in data["entries"]:
            assert entry["type"] == "directory"

    def test_list_directory(self, client: TestClient, browse_dir: Path) -> None:
        resp = client.get(
            "/api/filesystem/browse",
            params={"path": str(browse_dir)},
        )
        assert resp.status_code == 200
        data = resp.json()
        names = [e["name"] for e in data["entries"]]
        # Directories first, then files
        assert "alpha" in names
        assert "beta" in names
        assert "file_a.txt" in names
        assert "file_b.csv" in names
        # Verify ordering: directories before files
        dir_indices = [i for i, e in enumerate(data["entries"]) if e["type"] == "directory"]
        file_indices = [i for i, e in enumerate(data["entries"]) if e["type"] == "file"]
        if dir_indices and file_indices:
            assert max(dir_indices) < min(file_indices)

    def test_file_entries_have_size(self, client: TestClient, browse_dir: Path) -> None:
        resp = client.get(
            "/api/filesystem/browse",
            params={"path": str(browse_dir)},
        )
        assert resp.status_code == 200
        data = resp.json()
        file_entries = [e for e in data["entries"] if e["type"] == "file"]
        for entry in file_entries:
            assert entry["size"] is not None
            assert entry["size"] >= 0

    def test_nonexistent_path_returns_404(self, client: TestClient, browse_dir: Path) -> None:
        # The sanitiser (#1524) rejects anything outside the home/temp
        # allowlist with 400, so a 404 can only be observed for a path that
        # IS under an allowed root but does not exist. ``browse_dir`` lives
        # under the pytest tmp tree (system temp), which is allowed.
        missing = browse_dir / "does_not_exist_abc123"
        resp = client.get(
            "/api/filesystem/browse",
            params={"path": str(missing)},
        )
        assert resp.status_code == 404

    def test_path_outside_allowlist_is_rejected(self, client: TestClient) -> None:
        # #1524 regression: an unauthenticated client must not be able to
        # enumerate arbitrary directories (e.g. ``/etc``). The sanitiser
        # restricts browse to the home/temp allowlist and returns 400 for
        # anything else — BEFORE any iterdir() / existence probe runs.
        resp = client.get(
            "/api/filesystem/browse",
            params={"path": "/etc"},
        )
        assert resp.status_code == 400

    def test_path_traversal_outside_allowlist_is_rejected(self, client: TestClient, browse_dir: Path) -> None:
        # A ``..`` escape that canonicalises outside the allowlist is rejected
        # by the realpath+commonpath guard, not silently followed. Use enough
        # ``..`` segments to climb to the filesystem/drive root from any depth
        # (excess ``..`` at the root are no-ops under realpath), so the escape
        # lands outside the home/temp allowlist on every OS. A fixed shallow
        # ``..`` depth is NOT portable: on Windows the tempdir nests under the
        # home dir (``C:\\Users\\<u>\\AppData\\Local\\Temp``), so a shallow climb
        # stays inside the home allowlist and the guard never fires.
        escape = browse_dir.joinpath(*([".."] * 64), "scistudio_nonexistent_outside_allowlist")
        resp = client.get(
            "/api/filesystem/browse",
            params={"path": str(escape)},
        )
        assert resp.status_code == 400

    def test_file_path_returns_400(self, client: TestClient, browse_dir: Path) -> None:
        file_path = browse_dir / "file_a.txt"
        resp = client.get(
            "/api/filesystem/browse",
            params={"path": str(file_path)},
        )
        assert resp.status_code == 400

    def test_entries_sorted_alphabetically(self, client: TestClient, browse_dir: Path) -> None:
        resp = client.get(
            "/api/filesystem/browse",
            params={"path": str(browse_dir)},
        )
        assert resp.status_code == 200
        data = resp.json()
        dirs = [e["name"] for e in data["entries"] if e["type"] == "directory"]
        files = [e["name"] for e in data["entries"] if e["type"] == "file"]
        assert dirs == sorted(dirs, key=str.lower)
        assert files == sorted(files, key=str.lower)
