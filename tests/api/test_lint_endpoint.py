"""ADR-036 §3.3 — Python lint endpoint tests (Phase 2A I36a)."""

from __future__ import annotations

import subprocess

import pytest
from fastapi.testclient import TestClient


def test_lint_clean_returns_empty(client: TestClient) -> None:
    r = client.post(
        "/api/lint/python",
        json={"content": "print('ok')\n", "filename": "ok.py"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["diagnostics"] == []
    # No "note" on a successful lint.
    assert body.get("note") in (None,)


def test_lint_unused_import(client: TestClient) -> None:
    r = client.post(
        "/api/lint/python",
        json={"content": "import os\n", "filename": "u.py"},
    )
    assert r.status_code == 200
    diags = r.json()["diagnostics"]
    assert any(d["code"].startswith("F401") for d in diags), diags


def test_lint_syntax_error(client: TestClient) -> None:
    """ruff returns a single diagnostic for a parser error.

    Code is ``E999`` on pre-0.4 ruff and ``invalid-syntax`` on modern
    ruff. Accept either.
    """
    r = client.post(
        "/api/lint/python",
        json={"content": "def foo(\n", "filename": "syn.py"},
    )
    assert r.status_code == 200
    diags = r.json()["diagnostics"]
    assert len(diags) >= 1
    assert any(d["code"] == "E999" or d["code"] == "invalid-syntax" for d in diags), diags


def test_lint_diagnostic_shape(client: TestClient) -> None:
    """Every returned diagnostic has the contract fields."""
    r = client.post(
        "/api/lint/python",
        json={"content": "import os\n", "filename": "shape.py"},
    )
    assert r.status_code == 200
    diags = r.json()["diagnostics"]
    assert diags, "expected at least one diagnostic for unused-import"
    for d in diags:
        for field in ("line", "column", "end_line", "end_column", "code", "severity", "message"):
            assert field in d, f"missing field {field!r} in {d}"
        assert isinstance(d["line"], int)
        assert isinstance(d["column"], int)


def test_lint_ruff_missing(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> object:
        raise FileNotFoundError("ruff not on PATH")

    monkeypatch.setattr("scistudio.api.routes.lint.subprocess.run", fake_run)
    # Reset the once-per-process warned flag so the WARN log path runs.
    monkeypatch.setattr("scistudio.api.routes.lint._ruff_missing_warned", False)
    r = client.post(
        "/api/lint/python",
        json={"content": "x = 1\n", "filename": "x.py"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["diagnostics"] == []
    assert body["note"] == "ruff unavailable on server"


def test_lint_ruff_timeout(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="ruff", timeout=10.0)

    monkeypatch.setattr("scistudio.api.routes.lint.subprocess.run", fake_run)
    r = client.post(
        "/api/lint/python",
        json={"content": "x = 1\n", "filename": "x.py"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["diagnostics"] == []
    assert body["note"] == "ruff timed out"


def test_lint_ruff_non_json(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Soft-fail when ruff stdout is not valid JSON."""

    class FakeCompleted:
        returncode = 0
        stdout = "not actually json"
        stderr = ""

    def fake_run(*args: object, **kwargs: object) -> FakeCompleted:
        return FakeCompleted()

    monkeypatch.setattr("scistudio.api.routes.lint.subprocess.run", fake_run)
    r = client.post(
        "/api/lint/python",
        json={"content": "x = 1\n", "filename": "x.py"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["diagnostics"] == []
    assert body["note"] == "ruff returned non-JSON"
