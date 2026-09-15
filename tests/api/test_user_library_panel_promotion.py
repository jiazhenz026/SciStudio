"""ADR-054 MiniApp FR-039: promoting a project MiniApp directory to the user library.

User Story 5 acceptance scenario 2: a project MiniApp the user promotes is in
the user library, gone from the project, and still listed and openable.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scistudio.api.deps import get_runtime
from scistudio.api.routes.user_library import router
from scistudio.engine.events import EventBus

_PANEL_JSON = {
    "id": "threshold_explorer",
    "api_version": "1.0",
    "contexts": ["miniapp"],
    "types": ["Text"],
    "name": "Threshold explorer",
    "entry": "index.html",
}


def _write_panel(root: Path, panel_id: str) -> Path:
    directory = root / panel_id
    (directory / "assets").mkdir(parents=True)
    (directory / "panel.json").write_text(json.dumps(_PANEL_JSON | {"id": panel_id}), encoding="utf-8")
    (directory / "index.html").write_text("<p>explorer</p>", encoding="utf-8")
    (directory / "panel.py").write_text("def setup(data):\n    pass\n", encoding="utf-8")
    (directory / "assets" / "panel.css").write_text(".a{color:red}", encoding="utf-8")
    bytecode = directory / "__pycache__"
    bytecode.mkdir()
    (bytecode / "panel.cpython-311.pyc").write_bytes(b"\x00\x01")
    return directory


@pytest.fixture()
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the user library at an isolated home directory."""
    home = tmp_path / "home"
    home.mkdir()
    from scistudio.core import dropins

    monkeypatch.setattr(dropins.Path, "home", classmethod(lambda cls: home))
    return home / ".scistudio" / "panels"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    directory = tmp_path / "project"
    (directory / "panels").mkdir(parents=True)
    return directory


@pytest.fixture()
def client(project: Path) -> TestClient:
    refreshed: list[int] = []
    runtime = SimpleNamespace(
        active_project=SimpleNamespace(id="p", path=str(project)),
        event_bus=EventBus(),
        refresh_all_registries=lambda: refreshed.append(1),
    )
    app = FastAPI()
    app.state.runtime = runtime
    app.dependency_overrides[get_runtime] = lambda: runtime
    app.include_router(router)
    return TestClient(app)


def _promote(client: TestClient, project: Path, name: str, **body: Any) -> Any:
    return client.post(
        f"/api/user-library/directory?target=panels&name={name}",
        json={"project_dir": str(project), **body},
    )


def test_promotion_moves_the_whole_directory(client: TestClient, project: Path, library: Path) -> None:
    """US5 AS2: the directory is in the library and gone from the project."""
    _write_panel(project / "panels", "threshold_explorer")

    response = _promote(client, project, "threshold_explorer")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["target"] == "panels"
    assert body["name"] == "threshold_explorer"
    assert body["moved"] is True
    assert body["move_error"] is None

    landed = Path(body["path"])
    assert landed == library / "threshold_explorer"
    assert (landed / "panel.json").is_file()
    assert (landed / "index.html").read_text(encoding="utf-8") == "<p>explorer</p>"
    assert (landed / "panel.py").is_file()
    assert (landed / "assets" / "panel.css").is_file()
    assert not (project / "panels" / "threshold_explorer").exists()


def test_promotion_drops_bytecode(client: TestClient, project: Path, library: Path) -> None:
    """A ``__pycache__`` copied beside its source is imported in preference to it."""
    _write_panel(project / "panels", "threshold_explorer")
    assert _promote(client, project, "threshold_explorer").status_code == 200
    assert not (library / "threshold_explorer" / "__pycache__").exists()


def test_promotion_refuses_an_existing_library_id(client: TestClient, project: Path, library: Path) -> None:
    """FR-039: an existing library id needs the user's confirmation."""
    _write_panel(project / "panels", "threshold_explorer")
    assert _promote(client, project, "threshold_explorer").status_code == 200

    _write_panel(project / "panels", "threshold_explorer")
    response = _promote(client, project, "threshold_explorer")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "exists"
    # The refused promotion left both copies exactly as they were.
    assert (project / "panels" / "threshold_explorer" / "panel.json").is_file()
    assert (library / "threshold_explorer" / "panel.json").is_file()


def test_promotion_replaces_on_overwrite(client: TestClient, project: Path, library: Path) -> None:
    _write_panel(project / "panels", "threshold_explorer")
    assert _promote(client, project, "threshold_explorer").status_code == 200

    directory = _write_panel(project / "panels", "threshold_explorer")
    (directory / "index.html").write_text("<p>second</p>", encoding="utf-8")
    response = _promote(client, project, "threshold_explorer", overwrite=True)

    assert response.status_code == 200, response.text
    assert (library / "threshold_explorer" / "index.html").read_text(encoding="utf-8") == "<p>second</p>"


def test_promotion_degrades_to_a_copy_when_removal_fails(
    client: TestClient, project: Path, library: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-053 FR-017: the library copy exists, so the request succeeds and says so."""
    _write_panel(project / "panels", "threshold_explorer")
    from scistudio.api.routes import user_library

    def refuse(_path: Any) -> None:
        raise OSError("directory is in use")

    monkeypatch.setattr(user_library.shutil, "rmtree", refuse)
    response = _promote(client, project, "threshold_explorer")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["moved"] is False
    assert "could not remove" in body["move_error"]
    assert (library / "threshold_explorer" / "panel.json").is_file()
    assert (project / "panels" / "threshold_explorer" / "panel.json").is_file()


def test_promotion_refuses_a_name_that_is_a_path(client: TestClient, project: Path) -> None:
    for name in ("..", "a/b", ".hidden", "Threshold"):
        response = _promote(client, project, name)
        assert response.status_code in (400, 403), f"{name}: {response.text}"


def test_promotion_refuses_a_project_dir_that_is_not_the_open_project(
    client: TestClient, project: Path, tmp_path: Path
) -> None:
    """This route removes a tree; the project it removes from is not taken on trust."""
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "panels").mkdir(parents=True)
    _write_panel(elsewhere / "panels", "threshold_explorer")

    response = client.post(
        "/api/user-library/directory?target=panels&name=threshold_explorer",
        json={"project_dir": str(elsewhere)},
    )

    assert response.status_code == 403
    assert (elsewhere / "panels" / "threshold_explorer").is_dir()


def test_promotion_refuses_an_unknown_directory(client: TestClient, project: Path) -> None:
    response = _promote(client, project, "not_there")
    assert response.status_code == 404


def test_promotion_does_not_follow_a_symlink_out_of_the_project(
    client: TestClient, project: Path, library: Path, tmp_path: Path
) -> None:
    """A link inside the panel cannot drag a file in from outside."""
    outside = tmp_path / "secret.txt"
    outside.write_text("private", encoding="utf-8")
    directory = _write_panel(project / "panels", "threshold_explorer")
    (directory / "leak.txt").symlink_to(outside)

    assert _promote(client, project, "threshold_explorer").status_code == 200
    assert not (library / "threshold_explorer" / "leak.txt").exists()


def test_the_file_route_refuses_the_directory_tier(client: TestClient) -> None:
    """FR-039: a panel is a directory, so the single-file door says so."""
    response = client.put(
        "/api/user-library/file?target=panels&filename=panel.py",
        json={"content": "def setup(data):\n    pass\n"},
    )
    assert response.status_code == 400
    assert "directory" in response.json()["detail"]


def test_the_directory_route_refuses_a_file_tier(client: TestClient, project: Path) -> None:
    response = client.post(
        "/api/user-library/directory?target=blocks&name=threshold_explorer",
        json={"project_dir": str(project)},
    )
    assert response.status_code == 400


def _replacement(project: Path, library: Path) -> tuple[Path, Path]:
    source = _write_panel(project / "panels", "threshold_explorer")
    destination = _write_panel(library, "threshold_explorer")
    (source / "index.html").write_text("new panel", encoding="utf-8")
    (destination / "index.html").write_text("old panel", encoding="utf-8")
    return source, destination


@pytest.mark.parametrize("failing_step", ["backup", "landing"])
def test_failed_overwrite_preserves_original_and_project(
    client: TestClient, project: Path, library: Path, monkeypatch: pytest.MonkeyPatch, failing_step: str
) -> None:
    from scistudio.api.routes import user_library

    source, destination = _replacement(project, library)
    rename = user_library.os.rename

    def fail_selected(origin: Any, target: Any) -> None:
        path = Path(origin)
        if (failing_step == "backup" and path == destination) or (
            failing_step == "landing" and path.name.startswith(".__scistudio_promote_")
        ):
            raise PermissionError("injected rename failure")
        rename(origin, target)

    monkeypatch.setattr(user_library.os, "rename", fail_selected)
    response = _promote(client, project, "threshold_explorer", overwrite=True)

    assert response.status_code == 500
    assert (destination / "index.html").read_text() == "old panel"
    assert (source / "index.html").read_text() == "new panel"
    assert not list(library.glob(".__scistudio_backup_*"))
    assert not list(library.glob(".__scistudio_promote_*"))


@pytest.mark.parametrize("collision", [False, True])
def test_failed_rollback_keeps_recoverable_backup(
    client: TestClient, project: Path, library: Path, monkeypatch: pytest.MonkeyPatch, collision: bool
) -> None:
    from scistudio.api.routes import user_library

    source, destination = _replacement(project, library)
    rename = user_library.os.rename

    def fail_landing_and_restore(origin: Any, target: Any) -> None:
        path = Path(origin)
        if path.name.startswith(".__scistudio_promote_"):
            if collision:
                destination.mkdir()
                (destination / "index.html").write_text("concurrent panel")
            raise OSError("injected landing failure")
        if path.name == "previous":
            raise PermissionError("injected rollback failure")
        rename(origin, target)

    monkeypatch.setattr(user_library.os, "rename", fail_landing_and_restore)
    response = _promote(client, project, "threshold_explorer", overwrite=True)

    assert response.status_code == 500
    backups = list(library.glob(".__scistudio_backup_*"))
    assert len(backups) == 1
    assert backups[0].name in response.json()["detail"]
    assert (backups[0] / "previous" / "index.html").read_text() == "old panel"
    assert (source / "index.html").read_text() == "new panel"
    if collision:
        assert (destination / "index.html").read_text() == "concurrent panel"
    else:
        assert not destination.exists()


def test_backup_cleanup_failure_keeps_successful_promotion(
    client: TestClient, project: Path, library: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scistudio.api.routes import user_library

    source, destination = _replacement(project, library)
    rmtree = user_library.shutil.rmtree

    def fail_backup(path: Any, *args: Any, **kwargs: Any) -> None:
        if Path(path).name.startswith(".__scistudio_backup_"):
            raise PermissionError("injected cleanup failure")
        rmtree(path, *args, **kwargs)

    monkeypatch.setattr(user_library.shutil, "rmtree", fail_backup)
    response = _promote(client, project, "threshold_explorer", overwrite=True)

    assert response.status_code == 200, response.text
    assert response.json()["moved"] is True
    assert (destination / "index.html").read_text() == "new panel"
    backups = list(library.glob(".__scistudio_backup_*"))
    assert len(backups) == 1
    assert (backups[0] / "previous" / "index.html").read_text() == "old panel"
    assert not source.exists()


def test_concurrent_promotion_is_refused_without_touching_either_copy(
    client: TestClient, project: Path, library: Path
) -> None:
    from filelock import FileLock

    source, destination = _replacement(project, library)
    with FileLock(library / ".__scistudio_promote.lock"):
        response = _promote(client, project, "threshold_explorer", overwrite=True)

    assert response.status_code == 409
    assert (source / "index.html").read_text() == "new panel"
    assert (destination / "index.html").read_text() == "old panel"
    assert not list(library.glob(".__scistudio_backup_*"))
