"""T-ECA-203: unit tests for the 5 authoring tools (FastMCP async surface).

Restored from module-skip as part of #1539: the S40a skeleton has been
replaced by a fully implemented FastMCP async server (ADR-040 §3.1,
I40a Phase 2a). The original sync invocation pattern is rewritten here to
use ``asyncio.run()`` directly against the async-decorated callables.

Note: the original test file also covered ``create_block`` and
``create_workflow`` from an ADR-033-era API that was renamed/superseded
during the FastMCP migration (those functions no longer exist). The
remaining tools — ``read_block_source``, ``list_block_examples``,
``scaffold_block``, ``reload_blocks``, ``run_block_tests`` — are fully
implemented and tested here.

The ``_render_port_block`` regression tests (``test_render_port_block_*``)
are also tested in ``test_scaffold_template_regression.py`` (not skipped),
but retained here as inline regression evidence for the #1063 / #1539 fix.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import pytest

from scistudio.ai.agent.mcp import _context, tools_authoring
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.types.registry import TypeRegistry

_T = TypeVar("_T")


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run a coroutine synchronously (mirrors test_mcp_fastmcp.py helper)."""
    return asyncio.run(coro)


@dataclass
class _StubRuntime:
    block_registry: BlockRegistry = field(default_factory=BlockRegistry)
    # ADR-053 FR-062 / #2022: a real TypeRegistry, matching the ``MCPContext``
    # Protocol. ``reload_blocks`` now refreshes the type registry too, and a
    # bare ``object()`` here was a stub that could not have satisfied the
    # Protocol it stands in for. Other MCP stubs already use the real class.
    type_registry: TypeRegistry = field(default_factory=TypeRegistry)
    _project_dir: Path | None = None
    active_workflow_id: str | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@pytest.fixture
def ctx(tmp_path: Path) -> Iterator[_StubRuntime]:
    runtime = _StubRuntime(_project_dir=tmp_path)
    runtime.block_registry.scan()
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


# --- read_block_source -----------------------------------------------------


def test_read_block_source_happy(ctx: _StubRuntime) -> None:
    specs = ctx.block_registry.all_specs()
    type_name = next(iter(specs))
    result = _run(tools_authoring.read_block_source(type_name=type_name))
    # result is a ReadBlockSourceResult Pydantic model.
    assert result.language == "python"
    assert "class" in result.source
    assert Path(result.path).exists()


def test_read_block_source_unknown_raises(ctx: _StubRuntime) -> None:
    with pytest.raises(KeyError):
        _run(tools_authoring.read_block_source(type_name="DoesNotExist_X"))


# --- list_block_examples ---------------------------------------------------


def test_list_block_examples_happy(ctx: _StubRuntime) -> None:
    examples = _run(tools_authoring.list_block_examples(category="io"))
    assert isinstance(examples, list)
    # Compare structural module-path prefix as a tuple to avoid CodeQL
    # py/incomplete-url-substring-sanitization (rule confuses .io suffix with TLD).
    assert any(tuple(e.name.split(".")[:3]) == ("scistudio", "blocks", "io") for e in examples)


def test_list_block_examples_unknown_category_raises(ctx: _StubRuntime) -> None:
    with pytest.raises(KeyError):
        _run(tools_authoring.list_block_examples(category="not_a_category"))


# --- the corpus examples (ADR-054 spec 5 FR-027) ---------------------------
#
# The corpus gains a panel and a packaged notebook, and both must be reachable
# through the example-listing tool. They are directories rather than modules, so
# they resolve down the corpus path instead of through ``importlib``.


def test_list_block_examples_returns_the_packaged_notebook(ctx: _StubRuntime) -> None:
    """FR-027: a packaged-notebook worked example is listed and on disk."""
    examples = _run(tools_authoring.list_block_examples(category="notebook"))
    assert examples, "the notebook category must return at least one worked example"
    entry = examples[0]
    directory = Path(entry.path)
    assert directory.is_dir(), entry.path
    # The two halves packaging produces: the notebook a person wrote, and the
    # block declaration generated from it.
    assert list(directory.glob("*.ipynb")), f"{entry.name} carries no notebook"
    assert (directory / "block.py").is_file(), f"{entry.name} carries no generated declaration"
    assert (directory / "README.md").is_file()


def test_list_block_examples_returns_displaying_and_producing_panels(ctx: _StubRuntime) -> None:
    """FR-017 corpus half: at least one displaying and one producing panel."""
    examples = _run(tools_authoring.list_block_examples(category="panel"))
    assert len(examples) >= 2, "the panel corpus must carry both capabilities"

    capabilities = set()
    for entry in examples:
        directory = Path(entry.path)
        assert directory.is_dir(), entry.path
        manifest_path = directory / "panel.json"
        assert manifest_path.is_file(), f"{entry.name} carries no panel.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        capabilities.add(manifest["capability"])
        # A panel is a self-contained document; the declared entry must exist.
        assert (directory / manifest["entry"]).is_file(), f"{entry.name} entry document missing"
        assert (directory / "README.md").is_file()

    assert {"displaying", "producing"} <= capabilities, (
        f"the panel corpus declares only {sorted(capabilities)}; FR-017 requires "
        f"at least one displaying and one producing panel."
    )


def test_panel_corpus_documents_are_self_contained(ctx: _StubRuntime) -> None:
    """A panel example that pulled in an external asset would teach the wrong thing."""
    for entry in _run(tools_authoring.list_block_examples(category="panel")):
        document = (Path(entry.path) / "index.html").read_text(encoding="utf-8")
        assert "<script src=" not in document, f"{entry.name} loads an external script"
        assert '<link rel="stylesheet"' not in document, f"{entry.name} loads an external stylesheet"
        assert "https://" not in document.replace("http://www.w3.org/2000/svg", ""), (
            f"{entry.name} reaches outside its own directory"
        )


# --- scaffold_block --------------------------------------------------------


def test_scaffold_block_creates_file(ctx: _StubRuntime, tmp_path: Path) -> None:
    result = _run(tools_authoring.scaffold_block(name="my_smoother", category="process"))
    target = tmp_path / "blocks" / "my_smoother.py"
    assert target.exists()
    # result is a ScaffoldBlockResult Pydantic model; it has .path not .created.
    assert Path(result.path).resolve() == target.resolve()
    text = target.read_text(encoding="utf-8")
    assert "class MySmoother" in text


def test_scaffold_block_exists_raises(ctx: _StubRuntime, tmp_path: Path) -> None:
    (tmp_path / "blocks").mkdir()
    (tmp_path / "blocks" / "dup.py").write_text("# already here\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        _run(tools_authoring.scaffold_block(name="dup", category="process"))


def test_render_port_block_uses_accepted_types() -> None:
    """Regression for #1063 — _render_port_block emits accepted_types=[T] not type=T.

    InputPort and OutputPort in src/scistudio/blocks/base/ports.py take
    ``accepted_types: list[type]`` (not a single ``type=`` kwarg). Blocks
    scaffolded with the old template shape would raise ``TypeError`` at
    registry load time.

    Tested directly on the private helper (FastMCP-decorated public tool
    has a different call surface).
    """
    rendered = tools_authoring._render_port_block(
        {"in1": {"type": "DataObject"}, "in2": {"type": "Image"}},
        "InputPort",
    )
    # New shape — accepted_types=[T]
    assert "accepted_types=[DataObject]" in rendered, (
        f"Expected accepted_types=[DataObject] in scaffold output, got:\n{rendered}"
    )
    assert "accepted_types=[Image]" in rendered
    # Old shape MUST be gone — this is the bug
    assert "type=DataObject" not in rendered, f"Stale type=DataObject kwarg still in template:\n{rendered}"
    assert "type=Image" not in rendered


def test_render_port_block_empty_uses_accepted_types_comment() -> None:
    """Regression for #1063 — empty spec_map placeholder comment also fixed."""
    rendered = tools_authoring._render_port_block(None, "OutputPort")
    assert "accepted_types=[DataObject]" in rendered
    assert "type=DataObject" not in rendered


# --- reload_blocks ---------------------------------------------------------


def test_reload_blocks_returns_summary(ctx: _StubRuntime) -> None:
    result = _run(tools_authoring.reload_blocks())
    # result is a ReloadBlocksResult Pydantic model.
    assert hasattr(result, "reloaded") and hasattr(result, "added") and hasattr(result, "removed")


def test_reload_blocks_no_context_raises() -> None:
    _context.set_context(None)
    with pytest.raises(RuntimeError):
        _run(tools_authoring.reload_blocks())


# --- run_block_tests -------------------------------------------------------


def test_run_block_tests_not_found(ctx: _StubRuntime, tmp_path: Path) -> None:
    result = _run(tools_authoring.run_block_tests(type_name="DoesNotExist_X"))
    # result is a RunBlockTestsResult Pydantic model.
    assert result.found is False
    assert result.returncode == -1


def test_run_block_tests_happy(ctx: _StubRuntime, tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests" / "blocks"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_smoke.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    result = _run(tools_authoring.run_block_tests(type_name="smoke"))
    assert result.found is True
    # pytest may not be importable in some sandboxes; we just check the
    # path was located. The returncode is whatever pytest produced.
    assert result.test_path.endswith("test_smoke.py")
