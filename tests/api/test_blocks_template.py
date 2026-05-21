"""ADR-036 §3.12 (I36c) — block template endpoint integration tests."""

from __future__ import annotations

import ast

from fastapi.testclient import TestClient


def test_template_basic_returns_python_with_correct_imports(client: TestClient) -> None:
    """GET /api/blocks/template?kind=basic returns Python content with the right imports.

    Asserts the literal ``"from scistudio.blocks.base import"`` import line is
    present and the ``Block`` symbol is referenced. We do not pin the
    exact symbol list because the template tracks whatever
    ``base/__init__.py`` exports — see the long comment at the top of
    ``src/scistudio/blocks/_templates/block_base_template.py``.
    """
    r = client.get("/api/blocks/template?kind=basic")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "basic"
    assert body["suggested_filename"].endswith(".py")
    content = body["content"]
    assert "from scistudio.blocks.base import" in content
    assert "Block" in content
    # Must be syntactically valid Python — otherwise the editor renders it
    # with squiggles immediately on open and the template UX silently breaks.
    ast.parse(content)


def test_template_basic_has_run_marker(client: TestClient) -> None:
    """The template content contains the ``# >>> EDIT THIS <<<`` marker.

    This is the user-visible "start typing here" pointer. If it
    disappears, the new-block UX silently regresses.
    """
    r = client.get("/api/blocks/template?kind=basic")
    assert r.status_code == 200
    assert "# >>> EDIT THIS <<<" in r.json()["content"]


def test_template_default_kind_is_basic(client: TestClient) -> None:
    """Omitting ``kind`` defaults to ``basic`` per the FastAPI signature."""
    r = client.get("/api/blocks/template")
    assert r.status_code == 200
    assert r.json()["kind"] == "basic"


def test_template_unknown_kind_400(client: TestClient) -> None:
    """GET with an unknown kind returns HTTP 400 with a useful message."""
    r = client.get("/api/blocks/template?kind=frobnicator")
    assert r.status_code == 400
    body = r.json()
    assert "frobnicator" in body["detail"]
