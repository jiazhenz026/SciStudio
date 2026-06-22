"""Tests for diagnostics routes: version, client-logs, bundle (#1741/#1742)."""

from __future__ import annotations

import io
import logging
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from scistudio.api.routes import diagnostics


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(diagnostics.router)
    return app


def test_version_endpoint():
    client = TestClient(_make_app())
    response = client.get("/api/version")
    assert response.status_code == 200
    body = response.json()
    assert body["channel"] in ("alpha", "beta", "stable")
    assert "pep440" in body and "display" in body and "build" in body


def test_client_logs_persisted(caplog):
    client = TestClient(_make_app())
    payload = {"records": [{"level": "error", "message": "frontend boom", "url": "/canvas"}]}
    with caplog.at_level(logging.INFO, logger="scistudio.frontend"):
        response = client.post("/api/client-logs", json=payload)
    assert response.status_code == 200
    assert response.json()["accepted"] == 1
    assert any("frontend boom" in r.getMessage() for r in caplog.records)


def test_client_logs_empty_batch():
    client = TestClient(_make_app())
    response = client.post("/api/client-logs", json={"records": []})
    assert response.status_code == 200
    assert response.json()["accepted"] == 0


def test_bundle_returns_zip(tmp_path, monkeypatch):
    monkeypatch.setenv("SCISTUDIO_LOG_DIR", str(tmp_path))
    (tmp_path / "scistudio-1.log").write_text('{"message":"x"}\n', encoding="utf-8")
    client = TestClient(_make_app())
    response = client.get("/api/diagnostics/bundle")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    assert "environment.json" in names
    assert any(name.startswith("logs/") for name in names)


def test_bundle_post_includes_frontend_logs(tmp_path, monkeypatch):
    # Single-download path: the frontend POSTs its ring buffer and it is bundled
    # as frontend-logs.json inside the same zip.
    monkeypatch.setenv("SCISTUDIO_LOG_DIR", str(tmp_path))
    client = TestClient(_make_app())
    payload = {"records": [{"level": "error", "message": "frontend-only crash"}]}
    response = client.post("/api/diagnostics/bundle", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    assert "frontend-logs.log" in names
    assert "environment.json" in names
    frontend = archive.read("frontend-logs.log").decode("utf-8")
    assert "frontend-only crash" in frontend
