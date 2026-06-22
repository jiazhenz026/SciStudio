"""Tests for the request logging middleware (#1741)."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from scistudio.api._logging_middleware import RequestLoggingMiddleware


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ok")
    def ok() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/boom")
    def boom() -> dict[str, bool]:
        raise RuntimeError("kaboom")

    return app


def test_request_id_assigned_when_absent():
    client = TestClient(_make_app(), raise_server_exceptions=False)
    response = client.get("/ok")
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")


def test_request_id_propagated_when_present():
    client = TestClient(_make_app(), raise_server_exceptions=False)
    response = client.get("/ok", headers={"X-Request-ID": "abc123"})
    assert response.headers.get("X-Request-ID") == "abc123"


def test_request_logged_at_info(caplog):
    client = TestClient(_make_app(), raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger="scistudio.api.request"):
        client.get("/ok")
    assert any("/ok" in r.getMessage() and "200" in r.getMessage() for r in caplog.records)


def test_uncaught_exception_logged_and_500(caplog):
    client = TestClient(_make_app(), raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="scistudio.api.request"):
        response = client.get("/boom")
    assert response.status_code == 500
    assert response.json().get("request_id")
    assert response.headers.get("X-Request-ID")
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors and any(r.exc_info for r in errors)


def test_access_log_carries_request_id():
    # Codex P2: the success-path access log must run while request_id_var is still
    # set, so the on-disk record (via ContextFilter) carries the correlation id.
    from scistudio.utils.log_setup import ContextFilter

    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = _Capture()
    handler.addFilter(ContextFilter())
    request_logger = logging.getLogger("scistudio.api.request")
    request_logger.addHandler(handler)
    request_logger.setLevel(logging.DEBUG)
    try:
        client = TestClient(_make_app(), raise_server_exceptions=False)
        client.get("/ok", headers={"X-Request-ID": "rid-success"})
    finally:
        request_logger.removeHandler(handler)

    access = [r for r in captured if "200" in r.getMessage()]
    assert access, "access log record was not captured"
    assert getattr(access[0], "request_id", None) == "rid-success"
