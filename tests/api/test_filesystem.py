"""Tests for the filesystem browsing and reveal API endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


class TestProjectTree:
    """Tests for GET /api/projects/{project_id}/tree."""

    def test_list_root(self, client: TestClient, opened_project: Path) -> None:
        """Root listing returns project-standard directories."""
        runtime = client.app.state.runtime
        project_id = runtime.active_project.id

        resp = client.get(f"/api/projects/{project_id}/tree")
        assert resp.status_code == 200
        data = resp.json()
        names = [e["name"] for e in data["entries"]]
        # Standard project directories created by create_project
        assert "workflows" in names
        assert "blocks" in names
        assert "data" in names

    def test_directories_before_files(self, client: TestClient, opened_project: Path) -> None:
        """Directories are listed before files, both alphabetical."""
        # Create a file in the project root
        (opened_project / "readme.txt").write_text("hello")
        runtime = client.app.state.runtime
        project_id = runtime.active_project.id

        resp = client.get(f"/api/projects/{project_id}/tree")
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        # All directories come before all files
        dir_indices = [i for i, e in enumerate(entries) if e["type"] == "directory"]
        file_indices = [i for i, e in enumerate(entries) if e["type"] == "file"]
        if dir_indices and file_indices:
            assert max(dir_indices) < min(file_indices)

    def test_subdirectory_listing(self, client: TestClient, opened_project: Path) -> None:
        """Listing a subdirectory returns its contents."""
        (opened_project / "data" / "raw" / "sample.csv").write_text("a,b\n1,2")
        runtime = client.app.state.runtime
        project_id = runtime.active_project.id

        resp = client.get(f"/api/projects/{project_id}/tree", params={"path": "data/raw"})
        assert resp.status_code == 200
        names = [e["name"] for e in resp.json()["entries"]]
        assert "sample.csv" in names

    def test_file_size_returned(self, client: TestClient, opened_project: Path) -> None:
        """File entries include a size field."""
        content = "test content"
        (opened_project / "test.txt").write_text(content)
        runtime = client.app.state.runtime
        project_id = runtime.active_project.id

        resp = client.get(f"/api/projects/{project_id}/tree")
        entries = resp.json()["entries"]
        txt = next(e for e in entries if e["name"] == "test.txt")
        assert txt["size"] is not None
        assert txt["size"] > 0

    def test_reject_path_traversal(self, client: TestClient, opened_project: Path) -> None:
        """Paths containing '..' are rejected."""
        runtime = client.app.state.runtime
        project_id = runtime.active_project.id

        resp = client.get(f"/api/projects/{project_id}/tree", params={"path": "../"})
        assert resp.status_code == 400

    def test_nonexistent_directory(self, client: TestClient, opened_project: Path) -> None:
        """Listing a path that does not exist returns 404."""
        runtime = client.app.state.runtime
        project_id = runtime.active_project.id

        resp = client.get(f"/api/projects/{project_id}/tree", params={"path": "nonexistent"})
        assert resp.status_code == 404

    def test_unknown_project(self, client: TestClient) -> None:
        """Unknown project ID returns 404."""
        resp = client.get("/api/projects/no-such-project/tree")
        assert resp.status_code == 404

    def test_hidden_files_excluded(self, client: TestClient, opened_project: Path) -> None:
        """Files and directories starting with '.' are not listed."""
        (opened_project / ".hidden_dir").mkdir()
        (opened_project / ".hidden_file").write_text("secret")
        runtime = client.app.state.runtime
        project_id = runtime.active_project.id

        resp = client.get(f"/api/projects/{project_id}/tree")
        names = [e["name"] for e in resp.json()["entries"]]
        assert ".hidden_dir" not in names
        assert ".hidden_file" not in names


class TestNativeDialog:
    """Tests for POST /api/filesystem/native-dialog."""

    def test_invalid_mode(self, client: TestClient) -> None:
        """Mode must be 'file' or 'directory'."""
        resp = client.post(
            "/api/filesystem/native-dialog",
            json={"mode": "invalid"},
        )
        assert resp.status_code == 422

    def test_directory_dialog_returns_paths(
        self, client: TestClient, opened_project: Path, monkeypatch: object
    ) -> None:
        """Successful directory dialog returns the selected path in a list."""
        import subprocess

        import scieasy.api.routes.filesystem as fs_mod

        fake_dir = str(opened_project / "data")

        class FakeCompletedProcess:
            stdout = fake_dir + "\n"
            stderr = ""
            returncode = 0

        original_run = subprocess.run
        fs_mod.subprocess.run = lambda *_args, **_kwargs: FakeCompletedProcess()  # type: ignore[assignment]
        try:
            resp = client.post(
                "/api/filesystem/native-dialog",
                json={"mode": "directory", "initial_dir": str(opened_project)},
            )
            assert resp.status_code == 200
            assert resp.json()["paths"] == [fake_dir]
        finally:
            fs_mod.subprocess.run = original_run  # type: ignore[assignment]

    def test_file_dialog_returns_paths(self, client: TestClient, opened_project: Path, monkeypatch: object) -> None:
        """Successful file dialog returns the selected file path in a list."""
        import subprocess

        import scieasy.api.routes.filesystem as fs_mod

        fake_file = str(opened_project / "data" / "sample.csv")

        class FakeCompletedProcess:
            stdout = fake_file + "\n"
            stderr = ""
            returncode = 0

        original_run = subprocess.run
        fs_mod.subprocess.run = lambda *_args, **_kwargs: FakeCompletedProcess()  # type: ignore[assignment]
        try:
            resp = client.post(
                "/api/filesystem/native-dialog",
                json={"mode": "file"},
            )
            assert resp.status_code == 200
            assert resp.json()["paths"] == [fake_file]
        finally:
            fs_mod.subprocess.run = original_run  # type: ignore[assignment]

    def test_file_dialog_multi_select(self, client: TestClient, opened_project: Path, monkeypatch: object) -> None:
        """File dialog with multiple selections returns pipe-separated paths."""
        import subprocess

        import scieasy.api.routes.filesystem as fs_mod

        fake_a = str(opened_project / "data" / "a.csv")
        fake_b = str(opened_project / "data" / "b.csv")

        class FakeCompletedProcess:
            stdout = f"{fake_a}|{fake_b}\n"
            stderr = ""
            returncode = 0

        original_run = subprocess.run
        fs_mod.subprocess.run = lambda *_args, **_kwargs: FakeCompletedProcess()  # type: ignore[assignment]
        try:
            resp = client.post(
                "/api/filesystem/native-dialog",
                json={"mode": "file"},
            )
            assert resp.status_code == 200
            assert resp.json()["paths"] == [fake_a, fake_b]
        finally:
            fs_mod.subprocess.run = original_run  # type: ignore[assignment]

    def test_cancelled_dialog_returns_empty_list(self, client: TestClient, monkeypatch: object) -> None:
        """Cancelled dialog returns empty paths list."""
        import subprocess

        import scieasy.api.routes.filesystem as fs_mod

        class FakeCompletedProcess:
            stdout = "\n"
            stderr = ""
            returncode = 1

        original_run = subprocess.run
        fs_mod.subprocess.run = lambda *_args, **_kwargs: FakeCompletedProcess()  # type: ignore[assignment]
        try:
            resp = client.post(
                "/api/filesystem/native-dialog",
                json={"mode": "directory"},
            )
            assert resp.status_code == 200
            assert resp.json()["paths"] == []
        finally:
            fs_mod.subprocess.run = original_run  # type: ignore[assignment]

    def test_timeout_returns_504(self, client: TestClient, monkeypatch: object) -> None:
        """Dialog timeout returns 504."""
        import subprocess

        import scieasy.api.routes.filesystem as fs_mod

        original_run = subprocess.run

        def timeout_run(*_args: object, **_kwargs: object) -> None:
            raise subprocess.TimeoutExpired(cmd="dialog", timeout=120)

        fs_mod.subprocess.run = timeout_run  # type: ignore[assignment]
        try:
            resp = client.post(
                "/api/filesystem/native-dialog",
                json={"mode": "file"},
            )
            assert resp.status_code == 504
        finally:
            fs_mod.subprocess.run = original_run  # type: ignore[assignment]

    def test_missing_command_returns_500(self, client: TestClient, monkeypatch: object) -> None:
        """Missing native command returns 500."""
        import subprocess

        import scieasy.api.routes.filesystem as fs_mod

        original_run = subprocess.run

        def not_found_run(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError("zenity not found")

        fs_mod.subprocess.run = not_found_run  # type: ignore[assignment]
        try:
            resp = client.post(
                "/api/filesystem/native-dialog",
                json={"mode": "directory"},
            )
            assert resp.status_code == 500
        finally:
            fs_mod.subprocess.run = original_run  # type: ignore[assignment]


class TestRevealInExplorer:
    """Tests for POST /api/filesystem/reveal."""

    def test_nonexistent_path_under_temp(self, client: TestClient, tmp_path: Path) -> None:
        """Reveal with a path under temp that does not exist returns 404."""
        resp = client.post(
            "/api/filesystem/reveal",
            json={"path": str(tmp_path / "definitely-does-not-exist-xyz")},
        )
        assert resp.status_code == 404

    def test_reveal_existing_path(self, client: TestClient, opened_project: Path, monkeypatch: object) -> None:
        """Reveal with a valid path returns 200 (mocked subprocess)."""
        import subprocess

        calls: list[list[str]] = []

        class FakePopen:
            def __init__(self, args: list[str], **_kwargs: object) -> None:
                calls.append(args)

        import scieasy.api.routes.filesystem as fs_mod

        # Monkeypatch subprocess.Popen in the filesystem module
        original_popen = subprocess.Popen
        fs_mod.subprocess.Popen = FakePopen  # type: ignore[assignment]
        try:
            resp = client.post(
                "/api/filesystem/reveal",
                json={"path": str(opened_project)},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
            assert len(calls) == 1
        finally:
            fs_mod.subprocess.Popen = original_popen  # type: ignore[assignment]


class TestRevealPathSanitiser:
    """Regression tests for the reveal path sanitiser (CodeQL py/path-injection, #721)."""

    def test_reject_path_outside_allowed_roots(self, client: TestClient) -> None:
        """Reveal with a path outside home/temp returns 400.

        Uses an OS-appropriate path that cannot fall under the user's
        home or system temp on any platform — Windows ``C:\\Windows\\System32``
        or POSIX ``/etc``.
        """
        import platform

        bad_path = "C:\\Windows\\System32" if platform.system() == "Windows" else "/etc"
        resp = client.post(
            "/api/filesystem/reveal",
            json={"path": bad_path},
        )
        assert resp.status_code == 400
        assert "user home" in resp.json()["detail"]

    def test_reject_traversal_escape(self, client: TestClient, tmp_path: Path) -> None:
        """Reveal with a traversal-escape path that resolves outside allowed roots returns 400."""
        import platform

        # Construct a path that looks like it is under tmp_path but escapes via ``..``.
        # On POSIX ``/tmp/../etc`` resolves to ``/etc``; on Windows we go to the drive root.
        escape_target = "C:\\Windows" if platform.system() == "Windows" else "/etc"
        traversal = str(tmp_path) + "/../" + escape_target.lstrip("/\\")
        resp = client.post(
            "/api/filesystem/reveal",
            json={"path": traversal},
        )
        # Either 400 (sanitiser rejects) or 404 (sanitiser allows but target missing).
        # The key is: subprocess MUST NOT be invoked on an out-of-bounds path.
        assert resp.status_code in (400, 404)

    def test_accept_path_under_home(self, client: TestClient, opened_project: Path, monkeypatch: object) -> None:
        """Reveal with a valid path under the user home returns 200 (mocked subprocess)."""
        import subprocess

        import scieasy.api.routes.filesystem as fs_mod

        calls: list[list[str]] = []

        class FakePopen:
            def __init__(self, args: list[str], **_kwargs: object) -> None:
                calls.append(args)

        original_popen = subprocess.Popen
        fs_mod.subprocess.Popen = FakePopen  # type: ignore[assignment]
        try:
            resp = client.post(
                "/api/filesystem/reveal",
                json={"path": str(opened_project)},
            )
            assert resp.status_code == 200
            assert len(calls) == 1
        finally:
            fs_mod.subprocess.Popen = original_popen  # type: ignore[assignment]

    def test_accept_path_under_tmp(self, client: TestClient, tmp_path: Path, monkeypatch: object) -> None:
        """Reveal with a valid path under tempdir returns 200 (mocked subprocess)."""
        import subprocess

        import scieasy.api.routes.filesystem as fs_mod

        # Create a real file under tmp_path so the existence check passes.
        target = tmp_path / "sample.txt"
        target.write_text("hi")

        class FakePopen:
            def __init__(self, args: list[str], **_kwargs: object) -> None:
                pass

        original_popen = subprocess.Popen
        fs_mod.subprocess.Popen = FakePopen  # type: ignore[assignment]
        try:
            resp = client.post(
                "/api/filesystem/reveal",
                json={"path": str(target)},
            )
            assert resp.status_code == 200
        finally:
            fs_mod.subprocess.Popen = original_popen  # type: ignore[assignment]
