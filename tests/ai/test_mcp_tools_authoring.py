"""T-ECA-203: unit tests for the 5 authoring tools (post-ADR-040)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from scieasy.ai.agent.mcp import _context, tools_authoring
from scieasy.blocks.registry import BlockRegistry
from scieasy.core.types.registry import TypeRegistry


def _run(coro):
    return asyncio.run(coro)


@dataclass
class _StubRuntime:
    block_registry: BlockRegistry = field(default_factory=BlockRegistry)
    type_registry: TypeRegistry = field(default_factory=TypeRegistry)
    _project_dir: Path | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@pytest.fixture
def ctx(tmp_path: Path) -> Iterator[_StubRuntime]:
    runtime = _StubRuntime(_project_dir=tmp_path)
    runtime.block_registry.scan()
    runtime.type_registry.scan_builtins()
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


# --- read_block_source -----------------------------------------------------


def test_read_block_source_happy(ctx: _StubRuntime) -> None:
    specs = ctx.block_registry.all_specs()
    name = next(iter(specs))
    result = _run(tools_authoring.read_block_source(name))
    assert result.language == "python"
    assert "class" in result.source
    assert Path(result.path).exists()


def test_read_block_source_unknown_raises(ctx: _StubRuntime) -> None:
    with pytest.raises(KeyError):
        _run(tools_authoring.read_block_source("DoesNotExist_X"))


# --- list_block_examples ---------------------------------------------------


def test_list_block_examples_happy(ctx: _StubRuntime) -> None:
    examples = _run(tools_authoring.list_block_examples("io"))
    assert isinstance(examples, list)
    # Per CodeQL guidance use tuple comparison to avoid TLD substring false positives.
    assert any(tuple(e.name.split(".")[:3]) == ("scieasy", "blocks", "io") for e in examples)


def test_list_block_examples_unknown_category_raises(ctx: _StubRuntime) -> None:
    with pytest.raises(KeyError):
        _run(tools_authoring.list_block_examples("not_a_category"))


# --- scaffold_block --------------------------------------------------------


def test_scaffold_block_creates_file(ctx: _StubRuntime, tmp_path: Path) -> None:
    result = _run(tools_authoring.scaffold_block(name="my_smoother", category="process"))
    target = tmp_path / "blocks" / "my_smoother.py"
    assert target.exists()
    assert result.created is True
    text = target.read_text(encoding="utf-8")
    assert "class MySmoother" in text


def test_scaffold_block_exists_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    (tmp_path / "blocks").mkdir()
    (tmp_path / "blocks" / "dup.py").write_text("# already here\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        _run(tools_authoring.scaffold_block(name="dup", category="process"))


# --- reload_blocks ---------------------------------------------------------


def test_reload_blocks_returns_summary(ctx: _StubRuntime) -> None:
    result = _run(tools_authoring.reload_blocks())
    assert result.reloaded >= 0
    assert isinstance(result.added, list)
    assert isinstance(result.removed, list)


def test_reload_blocks_no_context_raises() -> None:
    _context.set_context(None)
    with pytest.raises(RuntimeError):
        _run(tools_authoring.reload_blocks())


# --- run_block_tests -------------------------------------------------------


def test_run_block_tests_not_found(ctx: _StubRuntime, tmp_path: Path) -> None:
    result = _run(tools_authoring.run_block_tests("DoesNotExist_X"))
    assert result.found is False
    assert result.returncode == -1


def test_run_block_tests_happy(ctx: _StubRuntime, tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests" / "blocks"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_smoke.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    result = _run(tools_authoring.run_block_tests("smoke"))
    assert result.found is True
    assert result.test_path.endswith("test_smoke.py")
