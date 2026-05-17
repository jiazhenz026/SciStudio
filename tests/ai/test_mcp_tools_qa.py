"""T-ECA-204: unit tests for the 4 Q&A tools.

# TODO(#1012): module-level skip during ADR-040 §3.1 FastMCP skeleton
#   phase. The QA tool bodies are NotImplementedError stubs in S40a;
#   I40a Phase 2a restores behavior. Out of scope per ADR-040 §3.1 /
#   phase: 2a I40a. Followup: #1012.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytestmark = pytest.mark.skip(
    reason="S40a skeleton — tool bodies are NotImplementedError stubs. TODO(#1012): I40a Phase 2a restores."
)

from scieasy.ai.agent.mcp import _context, tools_qa  # noqa: E402


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
    (tmp_path / "workflows" / "wf1.yaml").write_text("workflow: {}\n", encoding="utf-8")
    (tmp_path / "data" / "zarr").mkdir(parents=True)
    (tmp_path / "data" / "parquet").mkdir(parents=True)
    (tmp_path / "data" / "artifacts").mkdir(parents=True)
    (tmp_path / "data" / "parquet" / "table.parquet").write_bytes(b"placeholder")
    (tmp_path / "project.yaml").write_text(
        "project:\n  id: test\n  name: Test Project\n  version: 0.1.0\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def ctx(project_dir: Path) -> _StubRuntime:
    runtime = _StubRuntime(_project_dir=project_dir)
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


# --- search_docs -----------------------------------------------------------


def test_search_docs_happy(ctx: _StubRuntime) -> None:
    results = tools_qa.search_docs("workflow")
    assert results, "expected at least one match"
    assert all("snippet" in r for r in results)


def test_search_docs_empty_query(ctx: _StubRuntime) -> None:
    assert tools_qa.search_docs("") == []


def test_search_docs_scope(ctx: _StubRuntime) -> None:
    results = tools_qa.search_docs("design", scope="adr")
    assert results
    # All results should be from the adr/ scope.
    assert all("adr" in r["path"].lower() or r["path"].endswith(".md") for r in results)


def test_search_docs_scope_rejects_traversal(ctx: _StubRuntime) -> None:
    """Codex P1 regression — `scope` containing `..` must not escape docs/.

    Previously a value like ``../../`` would silently resolve to a
    path outside the docs tree and scan it. The guard now mirrors
    ``get_doc``'s relative_to(root) check.
    PR #744 discussion_r3231046696.
    """
    assert tools_qa.search_docs("anything", scope="../") == []
    assert tools_qa.search_docs("anything", scope="../../") == []


def test_search_docs_scope_rejects_absolute_path(ctx: _StubRuntime, tmp_path: Path) -> None:
    """An absolute path that points outside the docs/ tree is rejected."""
    outsider = tmp_path / "outsider"
    outsider.mkdir()
    (outsider / "f.md").write_text("workflow", encoding="utf-8")
    assert tools_qa.search_docs("workflow", scope=str(outsider)) == []


# --- get_doc ---------------------------------------------------------------


def test_get_doc_happy(ctx: _StubRuntime) -> None:
    out = tools_qa.get_doc("guide.md")
    assert "Guide" in out["content"]
    assert out["bytes"] > 0


def test_get_doc_escape_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    # Walk out of docs/ — should fail closed.
    with pytest.raises((PermissionError, FileNotFoundError)):
        tools_qa.get_doc("../../../etc/passwd")


# --- list_data -------------------------------------------------------------


def test_list_data_happy(ctx: _StubRuntime, project_dir: Path) -> None:
    out = tools_qa.list_data(str(project_dir))
    assert isinstance(out["zarr"], list)
    assert any(e["name"] == "table.parquet" for e in out["parquet"])


def test_list_data_missing_dir_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        tools_qa.list_data(str(tmp_path / "does_not_exist"))


# --- get_project_info ------------------------------------------------------


def test_get_project_info_happy(ctx: _StubRuntime) -> None:
    out = tools_qa.get_project_info()
    assert out["project"]["name"] == "Test Project"
    assert "wf1" in out["workflows"]


def test_get_project_info_no_project_raises(tmp_path: Path) -> None:
    runtime = _StubRuntime(_project_dir=tmp_path)  # no project.yaml
    _context.set_context(runtime)
    try:
        with pytest.raises(FileNotFoundError):
            tools_qa.get_project_info()
    finally:
        _context.set_context(None)
