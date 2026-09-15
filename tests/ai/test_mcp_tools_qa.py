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
    """A provisioned-style project: user-guide/, hidden agent docs, workflows/, data/.

    Projects have no ``docs/`` directory (#2375); the docs tools read the whole
    project directory.
    """
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("# Project readme\n\nRoot notes on workflow runs.\n", encoding="utf-8")
    (project / "user-guide").mkdir()
    (project / "user-guide" / "guide.md").write_text("# Guide\n\nThis explains workflow design.\n", encoding="utf-8")
    (project / "user-guide" / "adr").mkdir()
    (project / "user-guide" / "adr" / "ADR-001.md").write_text("# ADR 1\nDesign decision.\n", encoding="utf-8")
    (project / "user-guide" / "notes.rst").write_text("Notes\n=====\n\nrstneedle here.\n", encoding="utf-8")
    (project / "user-guide" / "log.TXT").write_text("txtneedle here.\n", encoding="utf-8")
    (project / ".scistudio" / "agent-reference").mkdir(parents=True)
    (project / ".scistudio" / "agent-reference" / "README.md").write_text(
        "# Agent reference\n\nhiddenneedle contract.\n", encoding="utf-8"
    )
    (project / "blocks").mkdir()
    (project / "blocks" / "block.py").write_text("# codeneedle\n", encoding="utf-8")
    (project / "workflows").mkdir()
    (project / "data" / "zarr").mkdir(parents=True)
    (project / "data" / "parquet").mkdir(parents=True)
    (project / "data" / "artifacts").mkdir(parents=True)
    (project / "data" / "parquet" / "table.parquet").write_bytes(b"not-a-real-parquet")
    (project / "data" / "artifacts" / "report.md").write_text("prunedneedle in data\n", encoding="utf-8")
    (project / ".git").mkdir()
    (project / ".git" / "notes.txt").write_text("prunedneedle in git\n", encoding="utf-8")
    (project / "env").mkdir()
    (project / "env" / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    (project / "env" / "LICENSE.txt").write_text("prunedneedle in venv\n", encoding="utf-8")
    (project / "node_modules" / "pkg").mkdir(parents=True)
    (project / "node_modules" / "pkg" / "README.md").write_text("prunedneedle in node_modules\n", encoding="utf-8")
    (project / "project.yaml").write_text(
        "project:\n  id: test\n  name: Test Project\n  version: 0.1.0\n  note: codeneedle\n", encoding="utf-8"
    )
    (project / "workflows" / "wf1.yaml").write_text("workflow: {}\n", encoding="utf-8")
    return project


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
    assert {r.path for r in results} == {"README.md", "user-guide/guide.md"}


def test_search_docs_empty_query(ctx: _StubRuntime) -> None:
    assert _run(tools_qa.search_docs(query="", scope=None)) == []


def test_search_docs_reads_md_rst_txt_including_hidden_dirs(ctx: _StubRuntime) -> None:
    """#2375: the whole project directory is searched, hidden dirs included."""
    assert [r.path for r in _run(tools_qa.search_docs(query="rstneedle", scope=None))] == ["user-guide/notes.rst"]
    assert [r.path for r in _run(tools_qa.search_docs(query="txtneedle", scope=None))] == ["user-guide/log.TXT"]
    hidden = _run(tools_qa.search_docs(query="hiddenneedle", scope=None))
    assert [r.path for r in hidden] == [".scistudio/agent-reference/README.md"]
    assert hidden[0].line == 3


def test_search_docs_ignores_non_doc_suffixes(ctx: _StubRuntime) -> None:
    assert _run(tools_qa.search_docs(query="codeneedle", scope=None)) == []


def test_search_docs_skips_data_vcs_and_environment_dirs(ctx: _StubRuntime) -> None:
    assert _run(tools_qa.search_docs(query="prunedneedle", scope=None)) == []


def test_search_docs_no_project_returns_empty() -> None:
    _context.set_context(_StubRuntime(_project_dir=None))
    try:
        assert _run(tools_qa.search_docs(query="workflow", scope=None)) == []
    finally:
        _context.set_context(None)


def test_search_docs_scope(ctx: _StubRuntime) -> None:
    results = _run(tools_qa.search_docs(query="design", scope="user-guide/adr"))
    assert [r.path for r in results] == ["user-guide/adr/ADR-001.md"]


def test_search_docs_scope_hidden_dir(ctx: _StubRuntime) -> None:
    results = _run(tools_qa.search_docs(query="contract", scope=".scistudio"))
    assert [r.path for r in results] == [".scistudio/agent-reference/README.md"]


def test_search_docs_scope_rejects_traversal(ctx: _StubRuntime) -> None:
    """Codex P1 regression — ``scope`` containing ``..`` must not escape the project.

    Before the fix, ``scope="../"`` resolved via ``root / scope`` to a
    path outside the searched tree and scanned it. The guard mirrors
    ``get_doc``'s containment check.
    """
    outside = ctx.project_dir.parent / "outside.md"
    outside.write_text("anything outside\n", encoding="utf-8")
    assert _run(tools_qa.search_docs(query="anything", scope="../")) == []
    assert _run(tools_qa.search_docs(query="anything", scope="../../")) == []


def test_search_docs_scope_rejects_absolute_path(ctx: _StubRuntime, tmp_path_factory: pytest.TempPathFactory) -> None:
    """An absolute path that points outside the project directory is rejected."""
    outsider = tmp_path_factory.mktemp("outsider")
    (outsider / "f.md").write_text("workflow", encoding="utf-8")
    assert _run(tools_qa.search_docs(query="workflow", scope=str(outsider))) == []


# --- get_doc ---------------------------------------------------------------


def test_get_doc_happy(ctx: _StubRuntime) -> None:
    out = _run(tools_qa.get_doc(path="user-guide/guide.md"))
    # out is a GetDocResult Pydantic model.
    assert "Guide" in out.content
    assert out.bytes > 0
    assert out.path == "user-guide/guide.md"


def test_get_doc_reads_hidden_dir_doc(ctx: _StubRuntime) -> None:
    out = _run(tools_qa.get_doc(path=".scistudio/agent-reference/README.md"))
    assert "hiddenneedle" in out.content
    assert out.path == ".scistudio/agent-reference/README.md"


def test_get_doc_accepts_absolute_path_inside_project(ctx: _StubRuntime) -> None:
    out = _run(tools_qa.get_doc(path=str(ctx.project_dir / "user-guide" / "notes.rst")))
    assert out.path == "user-guide/notes.rst"


def test_get_doc_escape_raises(ctx: _StubRuntime) -> None:
    # Walk out of the project directory — should fail closed.
    with pytest.raises(PermissionError):
        _run(tools_qa.get_doc(path="../../../etc/passwd"))


def test_get_doc_absolute_path_outside_project_raises(
    ctx: _StubRuntime, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outsider = tmp_path_factory.mktemp("outsider") / "secret.md"
    outsider.write_text("secret", encoding="utf-8")
    with pytest.raises(PermissionError):
        _run(tools_qa.get_doc(path=str(outsider)))


def test_get_doc_refuses_non_doc_suffix(ctx: _StubRuntime) -> None:
    with pytest.raises(ValueError, match=r"\.md, \.rst, and \.txt"):
        _run(tools_qa.get_doc(path="blocks/block.py"))


def test_get_doc_missing_file_raises(ctx: _StubRuntime) -> None:
    with pytest.raises(FileNotFoundError):
        _run(tools_qa.get_doc(path="user-guide/missing.md"))


def test_get_doc_no_project_raises() -> None:
    _context.set_context(_StubRuntime(_project_dir=None))
    try:
        with pytest.raises(RuntimeError, match="No project"):
            _run(tools_qa.get_doc(path="README.md"))
    finally:
        _context.set_context(None)


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


@pytest.mark.parametrize(
    ("published", "expected"),
    [
        ("http://127.0.0.1:54321/", "http://127.0.0.1:54321"),
        ("  https://studio.example/lab/session/  ", "https://studio.example/lab/session"),
    ],
)
def test_open_gui_happy(monkeypatch: pytest.MonkeyPatch, published: str, expected: str) -> None:
    """Returns the running GUI URL published by the backend on startup.

    open_gui reads the canonical ``SCISTUDIO_ENGINE_API_URL`` (ADR-035 §3.10);
    it needs no project context. A trailing slash is stripped so the agent
    gets a clean base URL to open in a browser.
    """
    monkeypatch.setenv("SCISTUDIO_ENGINE_API_URL", published)
    out = _run(tools_qa.open_gui())
    assert out.url == expected
    assert out.hint  # non-empty usage guidance


def test_open_gui_no_server_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raises when no GUI server is running (e.g. MCP bridge standalone mode).

    With ``SCISTUDIO_ENGINE_API_URL`` unset there is no live frontend URL to
    hand back, so the tool must fail loudly rather than return a bogus URL.
    """
    monkeypatch.delenv("SCISTUDIO_ENGINE_API_URL", raising=False)
    with pytest.raises(RuntimeError, match="No running SciStudio GUI"):
        _run(tools_qa.open_gui())
