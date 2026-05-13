"""T-ECA-203: unit tests for the 5 authoring tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from scieasy.ai.agent.mcp import _context, tools_authoring
from scieasy.blocks.registry import BlockRegistry


@dataclass
class _StubRuntime:
    block_registry: BlockRegistry = field(default_factory=BlockRegistry)
    type_registry: object = field(default_factory=object)
    _project_dir: Path | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@pytest.fixture
def ctx(tmp_path: Path) -> _StubRuntime:
    runtime = _StubRuntime(_project_dir=tmp_path)
    runtime.block_registry.scan()
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


# --- read_block_source -----------------------------------------------------


def test_read_block_source_happy(ctx: _StubRuntime) -> None:
    specs = ctx.block_registry.all_specs()
    name = next(iter(specs))
    result = tools_authoring.read_block_source(name)
    assert result["language"] == "python"
    assert "class" in result["source"]
    assert Path(result["path"]).exists()


def test_read_block_source_unknown_raises(ctx: _StubRuntime) -> None:
    with pytest.raises(KeyError):
        tools_authoring.read_block_source("DoesNotExist_X")


# --- list_block_examples ---------------------------------------------------


def test_list_block_examples_happy(ctx: _StubRuntime) -> None:
    examples = tools_authoring.list_block_examples("io")
    assert isinstance(examples, list)
    # Compare structural module-path prefix as a tuple to avoid CodeQL
    # py/incomplete-url-substring-sanitization (rule confuses .io suffix with TLD).
    assert any(tuple(e["name"].split(".")[:3]) == ("scieasy", "blocks", "io") for e in examples)


def test_list_block_examples_unknown_category_raises(ctx: _StubRuntime) -> None:
    with pytest.raises(KeyError):
        tools_authoring.list_block_examples("not_a_category")


# --- scaffold_block --------------------------------------------------------


def test_scaffold_block_creates_file(ctx: _StubRuntime, tmp_path: Path) -> None:
    result = tools_authoring.scaffold_block("my_smoother", "process")
    target = tmp_path / "blocks" / "my_smoother.py"
    assert target.exists()
    assert result["created"] is True
    text = target.read_text(encoding="utf-8")
    assert "class MySmoother" in text


def test_scaffold_block_exists_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    (tmp_path / "blocks").mkdir()
    (tmp_path / "blocks" / "dup.py").write_text("# already here\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        tools_authoring.scaffold_block("dup", "process")


# --- reload_blocks ---------------------------------------------------------


def test_reload_blocks_returns_summary(ctx: _StubRuntime) -> None:
    result = tools_authoring.reload_blocks()
    assert "reloaded" in result and "added" in result and "removed" in result


def test_reload_blocks_no_context_raises() -> None:
    _context.set_context(None)
    with pytest.raises(RuntimeError):
        tools_authoring.reload_blocks()


# --- run_block_tests -------------------------------------------------------


def test_run_block_tests_not_found(ctx: _StubRuntime, tmp_path: Path) -> None:
    result = tools_authoring.run_block_tests("DoesNotExist_X")
    assert result["found"] is False
    assert result["returncode"] == -1


def test_run_block_tests_happy(ctx: _StubRuntime, tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests" / "blocks"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_smoke.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    result = tools_authoring.run_block_tests("smoke")
    assert result["found"] is True
    # pytest may not be importable in some sandboxes; we just check the
    # path was located. The returncode is whatever pytest produced.
    assert result["test_path"].endswith("test_smoke.py")
