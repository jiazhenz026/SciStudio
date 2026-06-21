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


# #1723 — the template is copied verbatim into the user's project. It must read
# as user-facing guidance, never as internal agent/phase collaboration notes.
_INTERNAL_MARKERS = (
    "Skeleton",
    "skeleton agent",
    "S36",
    "I36c",
    "dispatch prompt",
    "lockstep",
)


def test_template_basic_has_no_internal_dev_text(client: TestClient) -> None:
    """The user-facing template must not leak internal agent/phase notes (#1723)."""
    content = client.get("/api/blocks/template?kind=basic").json()["content"]
    leaks = [marker for marker in _INTERNAL_MARKERS if marker in content]
    assert not leaks, f"template leaks internal dev text: {leaks}"


def test_template_documents_real_run_contract(client: TestClient) -> None:
    """The template documents the real run() contract + parameter accessor (#1723).

    The old template wrongly told users to "Return a BlockResult" and to read
    parameters via ``self.config["..."]``. The real contract returns
    ``dict[str, Collection]`` and reads parameters with ``config.get(...)``.
    """
    content = client.get("/api/blocks/template?kind=basic").json()["content"]
    assert "dict[str, Collection]" in content
    assert "BlockResult" not in content
    assert "config.get(" in content
    # #1725 — ADR-031 removed ViewProxy/DataObject.view(); the read path is
    # item.to_memory() directly. The template must not teach the removed view().
    assert ".view(" not in content, "template must use item.to_memory(), not the removed view()"
    assert "item.to_memory()" in content
    # A worked, paste-over example is part of the user-friendly rewrite.
    assert "Minimal example" in content
