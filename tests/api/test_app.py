"""Tests for FastAPI app factory and lifespan."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from scieasy.api.app import _resolve_spa_static_dir, create_app, lifespan
from scieasy.engine.runners.process_handle import ProcessRegistry


class TestCreateApp:
    """Tests for the create_app() factory function."""

    def test_returns_fastapi_instance(self) -> None:
        """create_app() returns a FastAPI app."""
        app = create_app()
        assert isinstance(app, FastAPI)

    def test_app_title(self) -> None:
        """App has correct title metadata."""
        app = create_app()
        assert app.title == "SciEasy API"

    def test_app_version(self) -> None:
        """App has the expected version string."""
        app = create_app()
        assert app.version == "0.1.0"


class TestLifespan:
    """Tests for the lifespan async context manager."""

    def test_lifespan_creates_registry(self) -> None:
        """Lifespan startup creates a ProcessRegistry on app.state."""

        async def _run() -> None:
            app = FastAPI()
            async with lifespan(app):
                assert hasattr(app.state, "registry")
                assert isinstance(app.state.registry, ProcessRegistry)

        asyncio.run(_run())

    def test_lifespan_creates_runtime(self) -> None:
        """Lifespan startup creates an ApiRuntime on app.state."""
        from scieasy.api.runtime import ApiRuntime

        async def _run() -> None:
            app = FastAPI()
            async with lifespan(app):
                assert hasattr(app.state, "runtime")
                assert isinstance(app.state.runtime, ApiRuntime)

        asyncio.run(_run())

    def test_lifespan_no_separate_git_watcher_state(self) -> None:
        """D39-3.2 (#968) P1-A: the standalone ``GitChangeWatcher`` was deleted.

        The unified ``workflow_watcher`` covers the ``.git/`` surface now,
        so no ``app.state.git_watcher`` slot is expected. This regression
        test pins the collapse so a future re-introduction of a parallel
        watcher trips CI.
        """

        async def _run() -> None:
            app = FastAPI()
            async with lifespan(app):
                assert not hasattr(app.state, "git_watcher"), (
                    "app.state.git_watcher should no longer exist after D39-3.2 "
                    "dual-watcher collapse — the workflow_watcher covers the .git/ surface."
                )
                # The workflow watcher remains the single source of truth.
                assert hasattr(app.state, "workflow_watcher")

        asyncio.run(_run())

    def test_git_change_watcher_no_longer_exported(self) -> None:
        """D39-3.2 (#968) P1-A: ``core.versioning.GitChangeWatcher`` is gone.

        Importing it must raise ImportError now that the polling watcher
        was collapsed into ``workflow_watcher._GitHeadHandler``.
        """
        import scieasy.core.versioning as versioning_pkg

        assert "GitChangeWatcher" not in versioning_pkg.__all__
        with pytest.raises(ImportError):
            from scieasy.core.versioning import GitChangeWatcher  # noqa: F401

    def test_lifespan_calls_terminate_all_on_shutdown(self) -> None:
        """Lifespan shutdown calls terminate_all on the registry."""
        called_with: dict[str, float] = {}

        async def _run() -> None:
            app = FastAPI()
            async with lifespan(app):
                registry = app.state.registry

                def mock_terminate_all(grace_period_sec: float = 5.0) -> None:
                    called_with["grace_period_sec"] = grace_period_sec

                registry.terminate_all = mock_terminate_all
            # After exiting context, terminate_all should have been called

        asyncio.run(_run())
        assert "grace_period_sec" in called_with
        assert called_with["grace_period_sec"] == 5.0

    def test_lifespan_integrated_with_create_app(self) -> None:
        """The app from create_app() has the lifespan wired in."""
        app = create_app()
        assert app.router.lifespan_context is not None


class TestCORSOrigins:
    """Tests for CORS origin configuration."""

    def test_default_cors_restricts_to_localhost(self, monkeypatch: object) -> None:
        """Without SCIEASY_CORS_ORIGINS env var, only localhost origins are allowed."""
        monkeypatch.delenv("SCIEASY_CORS_ORIGINS", raising=False)  # type: ignore[union-attr]
        app = create_app()
        cors_mw = next(
            (m for m in app.user_middleware if m.cls is CORSMiddleware),
            None,
        )
        assert cors_mw is not None
        allowed = cors_mw.kwargs.get("allow_origins", [])
        assert "http://localhost:5173" in allowed
        assert "http://localhost:8000" in allowed
        assert "*" not in allowed

    def test_cors_env_var_wildcard(self, monkeypatch: object) -> None:
        """SCIEASY_CORS_ORIGINS=* allows all origins."""
        monkeypatch.setenv("SCIEASY_CORS_ORIGINS", "*")  # type: ignore[union-attr]
        app = create_app()
        cors_mw = next(
            (m for m in app.user_middleware if m.cls is CORSMiddleware),
            None,
        )
        assert cors_mw is not None
        assert cors_mw.kwargs.get("allow_origins") == ["*"]

    def test_cors_env_var_custom(self, monkeypatch: object) -> None:
        """SCIEASY_CORS_ORIGINS with custom comma-separated origins."""
        monkeypatch.setenv("SCIEASY_CORS_ORIGINS", "http://localhost:3000, http://localhost:4000")  # type: ignore[union-attr]
        app = create_app()
        cors_mw = next(
            (m for m in app.user_middleware if m.cls is CORSMiddleware),
            None,
        )
        assert cors_mw is not None
        allowed = cors_mw.kwargs.get("allow_origins", [])
        assert "http://localhost:3000" in allowed
        assert "http://localhost:4000" in allowed


class TestStaticMount:
    """Tests for conditional SPA static file mounting."""

    def test_no_static_mount_when_dir_absent(self, tmp_path: Path, monkeypatch: object) -> None:
        """When no SPA bundle is resolved, root redirects to /docs."""
        import scieasy.api.app as app_mod

        fake_app_py = tmp_path / "src" / "scieasy" / "api" / "app.py"
        fake_app_py.parent.mkdir(parents=True, exist_ok=True)
        fake_app_py.write_text("", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        monkeypatch.setattr(app_mod, "__file__", str(fake_app_py))
        app = create_app()
        client = TestClient(app)
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/docs"

    def test_static_mount_when_dir_exists(self, tmp_path: Path, monkeypatch: object) -> None:
        """When static dir exists, SPA mount serves index.html."""
        import scieasy.api.app as app_mod

        fake_app_py = tmp_path / "src" / "scieasy" / "api" / "app.py"
        fake_app_py.parent.mkdir(parents=True, exist_ok=True)
        fake_app_py.write_text("", encoding="utf-8")
        static_dir = fake_app_py.parent / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<html>SPA</html>", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        monkeypatch.setattr(app_mod, "__file__", str(fake_app_py))

        from starlette.routing import Mount

        app = create_app()
        spa_mounts = [r for r in app.routes if isinstance(r, Mount) and r.name == "spa"]
        assert len(spa_mounts) == 1

    def test_resolve_spa_static_dir_warns_when_frontend_dist_is_stale(
        self,
        tmp_path: Path,
        monkeypatch: object,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Editable-install fallback should warn when frontend/src is newer than dist."""
        import scieasy.api.app as app_mod

        fake_app_py = tmp_path / "src" / "scieasy" / "api" / "app.py"
        fake_app_py.parent.mkdir(parents=True, exist_ok=True)
        fake_app_py.write_text("", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

        dist_dir = tmp_path / "frontend" / "dist"
        dist_dir.mkdir(parents=True)
        dist_index = dist_dir / "index.html"
        dist_index.write_text("<html>old build</html>", encoding="utf-8")

        src_dir = tmp_path / "frontend" / "src"
        src_dir.mkdir(parents=True)
        src_file = src_dir / "BlockNode.tsx"
        src_file.write_text("export const stale = true;", encoding="utf-8")

        os.utime(dist_index, (1, 1))
        os.utime(src_file, (2, 2))

        monkeypatch.setattr(app_mod, "__file__", str(fake_app_py))
        with caplog.at_level(logging.WARNING):
            resolved = _resolve_spa_static_dir()

        assert resolved == dist_dir
        assert "frontend/dist may be stale" in caplog.text


class TestGetProcessRegistry:
    """Tests for the get_process_registry dependency function."""

    def test_returns_registry_from_app_state(self) -> None:
        """Returns the ProcessRegistry when it exists on app.state."""
        from scieasy.api.deps import get_process_registry

        mock_request = MagicMock()
        mock_request.app.state.registry = ProcessRegistry()
        result = get_process_registry(mock_request)
        assert isinstance(result, ProcessRegistry)

    def test_raises_runtime_error_when_not_initialized(self) -> None:
        """Raises RuntimeError when registry is not on app.state."""
        import pytest

        from scieasy.api.deps import get_process_registry

        mock_request = MagicMock()
        # Simulate state without registry attribute
        mock_request.app.state = MagicMock(spec=[])

        with pytest.raises(RuntimeError, match="ProcessRegistry not initialized"):
            get_process_registry(mock_request)
