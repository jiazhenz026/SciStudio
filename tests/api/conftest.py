"""Shared fixtures for API integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scistudio.api.app import create_app
from scistudio.api.runtime import ApiRuntime


@pytest.fixture()
def project_parent(tmp_path: Path) -> Path:
    """Return a writable directory for project workspace creation."""
    parent = tmp_path / "projects"
    parent.mkdir()
    return parent


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Create a TestClient with an isolated SciStudio home directory."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    from scistudio.api import runtime as runtime_module

    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake_home))

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def runtime(client: TestClient) -> ApiRuntime:
    """Expose the shared ApiRuntime for direct inspection in tests."""
    return client.app.state.runtime


@pytest.fixture()
def opened_project(client: TestClient, project_parent: Path) -> Path:
    """Create and open a project through the public API."""
    response = client.post(
        "/api/projects/",
        json={
            "name": "Demo Project",
            "description": "integration test workspace",
            "path": str(project_parent),
        },
    )
    assert response.status_code == 200
    return Path(response.json()["path"])
