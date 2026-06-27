"""Tests for the SPA static-file resolution in ``scistudio.api.app``.

Verifies issue #389 acceptance criteria:

* The runtime locates the SPA in both packaged (``scistudio/api/static/``)
  and editable-install (``<repo>/frontend/dist/``) layouts.
* When no SPA is bundled, ``GET /`` still redirects to the API docs
  instead of 404-ing.
* ``/api/*`` routes remain reachable regardless of which SPA layout is
  mounted (catch-all mount must not shadow them).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scistudio.api import app as app_module


def _make_spa_dir(root: Path) -> Path:
    """Create a minimal SPA tree (index.html + assets/) at ``root``."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text("<!doctype html><html><body>SciStudio SPA</body></html>", encoding="utf-8")
    assets = root / "assets"
    assets.mkdir(exist_ok=True)
    (assets / "main.js").write_text("console.log('hi')", encoding="utf-8")
    return root


def test_resolve_spa_prefers_dev_over_packaged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When both layouts exist, ``frontend/dist/`` wins (fresher dev build)."""
    fake_api_dir = tmp_path / "pkg" / "scistudio" / "api"
    fake_api_dir.mkdir(parents=True)
    fake_app_py = fake_api_dir / "app.py"
    fake_app_py.write_text("", encoding="utf-8")

    packaged = _make_spa_dir(fake_api_dir / "static")
    dev_build = _make_spa_dir(tmp_path / "frontend" / "dist")
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    monkeypatch.setattr(app_module, "__file__", str(fake_app_py))

    resolved = app_module._resolve_spa_static_dir()
    assert resolved == dev_build
    assert resolved != packaged


def test_resolve_spa_falls_back_to_frontend_dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With no packaged static, ``frontend/dist/`` at the repo root is used."""
    fake_api_dir = tmp_path / "src" / "scistudio" / "api"
    fake_api_dir.mkdir(parents=True)
    fake_app_py = fake_api_dir / "app.py"
    fake_app_py.write_text("", encoding="utf-8")

    dev_fallback = _make_spa_dir(tmp_path / "frontend" / "dist")
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    monkeypatch.setattr(app_module, "__file__", str(fake_app_py))

    resolved = app_module._resolve_spa_static_dir()
    assert resolved == dev_fallback


def test_resolve_spa_returns_none_when_nothing_built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither layout present → resolver returns ``None``."""
    fake_api_dir = tmp_path / "src" / "scistudio" / "api"
    fake_api_dir.mkdir(parents=True)
    fake_app_py = fake_api_dir / "app.py"
    fake_app_py.write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    monkeypatch.setattr(app_module, "__file__", str(fake_app_py))

    assert app_module._resolve_spa_static_dir() is None


def test_resolve_spa_ignores_empty_static_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A static/ directory without index.html should not be accepted."""
    fake_api_dir = tmp_path / "src" / "scistudio" / "api"
    fake_api_dir.mkdir(parents=True)
    fake_app_py = fake_api_dir / "app.py"
    fake_app_py.write_text("", encoding="utf-8")
    (fake_api_dir / "static").mkdir()  # empty
    dev_fallback = _make_spa_dir(tmp_path / "frontend" / "dist")
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    monkeypatch.setattr(app_module, "__file__", str(fake_app_py))

    resolved = app_module._resolve_spa_static_dir()
    assert resolved == dev_fallback


def test_resolve_spa_bundled_serves_only_packaged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#1747: ``SCISTUDIO_BUNDLED=1`` serves the embedded static even when a
    stray ``frontend/dist`` sits in a parent dir — the bundled UI must be
    environment-independent (not depend on the .app's filesystem location)."""
    fake_api_dir = tmp_path / "pkg" / "scistudio" / "api"
    fake_api_dir.mkdir(parents=True)
    fake_app_py = fake_api_dir / "app.py"
    fake_app_py.write_text("", encoding="utf-8")

    packaged = _make_spa_dir(fake_api_dir / "static")
    dev_build = _make_spa_dir(tmp_path / "frontend" / "dist")
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    monkeypatch.setattr(app_module, "__file__", str(fake_app_py))
    monkeypatch.setenv("SCISTUDIO_BUNDLED", "1")

    resolved = app_module._resolve_spa_static_dir()
    assert resolved == packaged
    assert resolved != dev_build


def test_resolve_spa_bundled_never_uses_dev_walkup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#1747: in bundled mode with no packaged static, the resolver returns
    ``None`` rather than serving a stray ``frontend/dist`` from a parent dir."""
    fake_api_dir = tmp_path / "pkg" / "scistudio" / "api"
    fake_api_dir.mkdir(parents=True)
    fake_app_py = fake_api_dir / "app.py"
    fake_app_py.write_text("", encoding="utf-8")

    # A dev build exists up the tree, but bundled mode must ignore it.
    _make_spa_dir(tmp_path / "frontend" / "dist")
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    monkeypatch.setattr(app_module, "__file__", str(fake_app_py))
    monkeypatch.setenv("SCISTUDIO_BUNDLED", "1")

    assert app_module._resolve_spa_static_dir() is None


def test_root_redirects_to_docs_without_spa(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no SPA is available, GET / still yields a 307 to /docs."""
    monkeypatch.setattr(app_module, "_resolve_spa_static_dir", lambda: None)
    app = app_module.create_app()
    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)
    assert response.status_code in (307, 308)
    assert response.headers["location"] == "/docs"


def test_root_serves_spa_index_when_static_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When a SPA is bundled, GET / returns its index.html body."""
    spa = _make_spa_dir(tmp_path / "static")
    monkeypatch.setattr(app_module, "_resolve_spa_static_dir", lambda: spa)
    app = app_module.create_app()
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "SciStudio SPA" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_api_routes_not_shadowed_by_spa_mount(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The catch-all SPA mount must not shadow ``/api/*`` routes."""
    spa = _make_spa_dir(tmp_path / "static")
    monkeypatch.setattr(app_module, "_resolve_spa_static_dir", lambda: spa)
    app = app_module.create_app()
    with TestClient(app) as client:
        response = client.get("/api/blocks/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
