"""Tests for SPA fallback static file serving."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from scistudio.api.spa import SPAStaticFiles


def _make_spa_app(static_dir: Path) -> FastAPI:
    """Create a minimal FastAPI app with SPA mount for testing."""
    app = FastAPI()

    @app.get("/api/test")
    async def api_test() -> dict[str, str]:
        return {"status": "ok"}

    app.mount("/", SPAStaticFiles(directory=str(static_dir), html=True), name="spa")
    return app


def _setup_static_dir(tmp_path: Path) -> Path:
    """Create a fake static directory with index.html and an asset."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html><body>SPA</body></html>", encoding="utf-8")
    assets_dir = static_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "main.js").write_text("console.log('app');", encoding="utf-8")
    return static_dir


class TestSPAStaticFiles:
    """Tests for SPAStaticFiles middleware."""

    def test_root_serves_index_html(self, tmp_path: Path) -> None:
        static_dir = _setup_static_dir(tmp_path)
        client = TestClient(_make_spa_app(static_dir))
        response = client.get("/")
        assert response.status_code == 200
        assert "SPA" in response.text

    def test_unknown_path_returns_index_html(self, tmp_path: Path) -> None:
        static_dir = _setup_static_dir(tmp_path)
        client = TestClient(_make_spa_app(static_dir))
        response = client.get("/projects/foo")
        assert response.status_code == 200
        assert "SPA" in response.text

    def test_deep_spa_route_returns_index(self, tmp_path: Path) -> None:
        static_dir = _setup_static_dir(tmp_path)
        client = TestClient(_make_spa_app(static_dir))
        response = client.get("/projects/123/workflows")
        assert response.status_code == 200
        assert "SPA" in response.text

    def test_real_static_file_served_directly(self, tmp_path: Path) -> None:
        static_dir = _setup_static_dir(tmp_path)
        client = TestClient(_make_spa_app(static_dir))
        response = client.get("/assets/main.js")
        assert response.status_code == 200
        assert "console.log" in response.text

    def test_api_route_not_intercepted(self, tmp_path: Path) -> None:
        """API routes registered before the SPA mount take priority."""
        static_dir = _setup_static_dir(tmp_path)
        client = TestClient(_make_spa_app(static_dir))
        response = client.get("/api/test")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_unknown_api_path_not_rewritten_to_spa_index(self, tmp_path: Path) -> None:
        """Deleted legacy API routes must stay 404s, not return index.html."""
        static_dir = _setup_static_dir(tmp_path)
        client = TestClient(_make_spa_app(static_dir))
        response = client.get("/api/data/obj-1/preview")
        assert response.status_code == 404
        assert "SPA" not in response.text
