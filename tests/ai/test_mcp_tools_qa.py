"""T-ECA-204: unit tests for the 4 Q&A tools (FastMCP async surface).

Restored from module-skip as part of #1539: the S40a skeleton has been
replaced by a fully implemented FastMCP async server (ADR-040 §3.1,
I40a Phase 2a). The original sync invocation pattern is rewritten here to
use ``asyncio.run()`` directly against the async-decorated callables, which
is the same pattern used by ``test_mcp_fastmcp.py``.

Tools under test: ``search_docs``, ``get_doc``, ``list_data``,
``get_project_info``, ``open_gui`` (#1947).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from scistudio.ai.agent.mcp import _context, tools_qa


def _run(coro):
    """Run a coroutine synchronously (mirrors test_mcp_fastmcp.py helper)."""
    return asyncio.run(coro)


@dataclass
class _StubRuntime:
    block_registry: object = field(default_factory=object)
    type_registry: object = field(default_factory=object)
    _project_dir: Path | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """A project workspace with docs/, workflows/, data/ scaffolded."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n\nThis explains workflow design.\n", encoding="utf-8")
    (tmp_path / "docs" / "adr").mkdir()
    (tmp_path / "docs" / "adr" / "ADR-001.md").write_text("# ADR 1\nDesign decision.\n", encoding="utf-8")
    (tmp_path / "workflows").mkdir()
    (tmp_path / "data" / "zarr").mkdir(parents=True)
    (tmp_path / "data" / "parquet").mkdir(parents=True)
    (tmp_path / "data" / "artifacts").mkdir(parents=True)
    (tmp_path / "data" / "parquet" / "table.parquet").write_bytes(b"placeholder")
    (tmp_path / "project.yaml").write_text(
        "project:\n  id: test\n  name: Test Project\n  version: 0.1.0\n", encoding="utf-8"
    )
    (tmp_path / "workflows" / "wf1.yaml").write_text("workflow: {}\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def ctx(project_dir: Path) -> _StubRuntime:
    runtime = _StubRuntime(_project_dir=project_dir)
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


# --- search_docs -----------------------------------------------------------


def test_search_docs_happy(ctx: _StubRuntime) -> None:
    results = _run(tools_qa.search_docs(query="workflow", scope=None))
    assert results, "expected at least one match"
    # Results are SearchDocsHit Pydantic models with a .snippet attribute.
    assert all(r.snippet for r in results)


def test_search_docs_empty_query(ctx: _StubRuntime) -> None:
    assert _run(tools_qa.search_docs(query="", scope=None)) == []


def test_search_docs_scope(ctx: _StubRuntime) -> None:
    results = _run(tools_qa.search_docs(query="design", scope="adr"))
    assert results
    # All results should be from the adr/ scope — .path is the relative path str.
    assert all("adr" in r.path.lower() or r.path.endswith(".md") for r in results)


def test_search_docs_scope_rejects_traversal(ctx: _StubRuntime) -> None:
    """Codex P1 regression — ``scope`` containing ``..`` must not escape docs/.

    Previously a value like ``../../`` would silently resolve to a
    path outside the docs tree and scan it. The guard now mirrors
    ``get_doc``'s relative_to(root) check.
    PR #744 discussion_r3231046696.
    """
    assert _run(tools_qa.search_docs(query="anything", scope="../")) == []
    assert _run(tools_qa.search_docs(query="anything", scope="../../")) == []


def test_search_docs_scope_rejects_absolute_path(ctx: _StubRuntime, tmp_path: Path) -> None:
    """An absolute path that points outside the docs/ tree is rejected."""
    outsider = tmp_path / "outsider"
    outsider.mkdir()
    (outsider / "f.md").write_text("workflow", encoding="utf-8")
    assert _run(tools_qa.search_docs(query="workflow", scope=str(outsider))) == []


# --- get_doc ---------------------------------------------------------------


def test_get_doc_happy(ctx: _StubRuntime) -> None:
    out = _run(tools_qa.get_doc(path="guide.md"))
    # out is a GetDocResult Pydantic model.
    assert "Guide" in out.content
    assert out.bytes > 0


def test_get_doc_escape_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    # Walk out of docs/ — should fail closed.
    with pytest.raises((PermissionError, FileNotFoundError)):
        _run(tools_qa.get_doc(path="../../../etc/passwd"))


# --- list_data -------------------------------------------------------------


def test_list_data_happy(ctx: _StubRuntime, project_dir: Path) -> None:
    out = _run(tools_qa.list_data(project_dir=str(project_dir)))
    # out is a ListDataResult Pydantic model with .zarr, .parquet, .artifacts lists.
    assert isinstance(out.zarr, list)
    assert any(e.name == "table.parquet" for e in out.parquet)


def test_list_data_missing_dir_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _run(tools_qa.list_data(project_dir=str(tmp_path / "does_not_exist")))


# --- get_project_info ------------------------------------------------------


def test_get_project_info_happy(ctx: _StubRuntime) -> None:
    out = _run(tools_qa.get_project_info())
    # out is a GetProjectInfoResult Pydantic model.
    assert out.project["name"] == "Test Project"
    assert "wf1" in out.workflows


def test_get_project_info_no_project_raises(tmp_path: Path) -> None:
    runtime = _StubRuntime(_project_dir=tmp_path)  # no project.yaml
    _context.set_context(runtime)
    try:
        with pytest.raises(FileNotFoundError):
            _run(tools_qa.get_project_info())
    finally:
        _context.set_context(None)


# --- open_gui (#1947) ------------------------------------------------------


def test_open_gui_happy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Returns the running GUI URL published by the backend on startup.

    open_gui reads the canonical ``SCISTUDIO_ENGINE_API_URL`` (ADR-035 §3.10);
    it needs no project context. A trailing slash is stripped so the agent
    gets a clean base URL to open in a browser.
    """
    monkeypatch.setenv("SCISTUDIO_ENGINE_API_URL", "http://127.0.0.1:54321/")
    out = _run(tools_qa.open_gui())
    assert out.url == "http://127.0.0.1:54321"
    assert out.hint  # non-empty usage guidance


def test_open_gui_no_server_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raises when no GUI server is running (e.g. MCP bridge standalone mode).

    With ``SCISTUDIO_ENGINE_API_URL`` unset there is no live frontend URL to
    hand back, so the tool must fail loudly rather than return a bogus URL.
    """
    monkeypatch.delenv("SCISTUDIO_ENGINE_API_URL", raising=False)
    with pytest.raises(RuntimeError, match="No running SciStudio GUI"):
        _run(tools_qa.open_gui())
