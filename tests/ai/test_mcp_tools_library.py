"""Agent promotion into the personal tool library (ADR-053 FR-011, FR-065).

``docs/specs/adr-053-personal-tool-library.md`` §4 and §6.2 E3, issue #1996.
Promotion is reachable from five entry points; this is the agent's, and
without it the agent cannot act on the promotion opportunities ADR-053 §3
expects it to offer.

Two things are pinned here.

**The tool's semantics** (FR-017, FR-018, FR-019): it copies rather than moves,
it refuses a block that is built-in, packaged, or already in the library, and a
name collision is reported rather than silently overwritten.

**FR-065's cross-process half.** Under FastAPI the MCP context is a read-through
adapter over the live ``ApiRuntime``, so a refresh in the agent is a refresh in
the process that serves the palette — that half is asserted in
``tests/api/test_user_library_write.py``. The standalone ``scistudio
mcp-bridge`` had no equivalent: it built its two registries once in
``make_mcp_runtime`` and held them for the whole session, so a block or type
written by *any* other process stayed invisible until the bridge restarted.
:meth:`StandaloneMCPRuntime.sync_dropins` is that missing channel, and the
tests at the bottom of this file are what make "without a restart" true there
too.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import pytest

from scistudio.ai.agent.mcp import _context, tools_library
from scistudio.ai.agent.mcp.runtime import make_mcp_runtime
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.dropins import register_block_scan_dirs, user_blocks_dir
from scistudio.core.types.registry import TypeRegistry

_T = TypeVar("_T")

BLOCK_TEMPLATE = '''\
from typing import Any, ClassVar

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig


class {class_name}(Block):
    """Drop-in block used to pin ADR-053 promotion."""

    type_name: ClassVar[str] = "test.{stem}"
    name: ClassVar[str] = "{stem}"
    base_category: ClassVar[str] = "process"
    subcategory: ClassVar[str] = "test"
    input_ports: ClassVar = []
    output_ports: ClassVar = []

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {{}}
'''


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(coro)


def _write_block(directory: Path, stem: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{stem}.py"
    target.write_text(
        BLOCK_TEMPLATE.format(class_name=stem.title().replace("_", ""), stem=stem),
        encoding="utf-8",
    )
    return target


@dataclass
class _StubRuntime:
    """The MCPContext surface the promotion tool reaches for, and no more."""

    block_registry: BlockRegistry = field(default_factory=BlockRegistry)
    type_registry: TypeRegistry = field(default_factory=TypeRegistry)
    _project_dir: Path | None = None
    active_workflow_id: str | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``Path.home()`` at an isolated user library."""
    fake_home = tmp_path / "home"
    (fake_home / ".scistudio" / "blocks").mkdir(parents=True)
    (fake_home / ".scistudio" / "types").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return fake_home


@pytest.fixture
def project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "proj"
    (project_dir / "blocks").mkdir(parents=True)
    (project_dir / "types").mkdir(parents=True)
    return project_dir


@pytest.fixture
def ctx(home: Path, project: Path) -> Iterator[_StubRuntime]:
    _write_block(project / "blocks", "promotable")
    runtime = _StubRuntime(_project_dir=project)
    register_block_scan_dirs(runtime.block_registry, project)
    runtime.block_registry.scan()
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


# ---------------------------------------------------------------------------
# FR-017 / FR-011 — promotion copies
# ---------------------------------------------------------------------------


def test_promotion_copies_the_block_into_the_user_library(ctx: _StubRuntime, project: Path) -> None:
    original = (project / "blocks" / "promotable.py").read_text(encoding="utf-8")
    result = _run(tools_library.promote_to_user_library(block_type="test.promotable"))

    promoted = user_blocks_dir() / "promotable.py"
    assert Path(result.path) == promoted
    assert result.filename == "promotable.py"
    assert result.overwritten is False
    assert promoted.read_text(encoding="utf-8") == original
    # FR-017: copy, never move — the originating project keeps working.
    assert (project / "blocks" / "promotable.py").read_text(encoding="utf-8") == original


def test_promotion_refreshes_the_registries_it_invalidated(ctx: _StubRuntime, project: Path) -> None:
    """FR-010: the tool names the event, so both registries are rebuilt.

    Asserted through a *second* file that the promotion did not write: it was
    dropped into the user library just before the call and is registered
    afterwards, which can only be true if the tool rebuilt the registry rather
    than leaving it as it found it.
    """
    _write_block(user_blocks_dir(), "arrived_meanwhile")
    assert ctx.block_registry.get_spec("test.arrived_meanwhile") is None

    _run(tools_library.promote_to_user_library(block_type="test.promotable"))

    assert ctx.block_registry.get_spec("test.arrived_meanwhile") is not None


def test_a_promoted_block_is_registered_in_a_project_that_never_had_it(
    ctx: _StubRuntime, project: Path, tmp_path: Path
) -> None:
    """The point of promotion: the block resolves from the user tier elsewhere."""
    _run(tools_library.promote_to_user_library(block_type="test.promotable"))

    other_project = tmp_path / "other"
    (other_project / "blocks").mkdir(parents=True)
    elsewhere = BlockRegistry()
    register_block_scan_dirs(elsewhere, other_project)
    elsewhere.scan()
    assert elsewhere.get_spec("test.promotable") is not None


def test_a_new_name_renames_the_destination(ctx: _StubRuntime) -> None:
    """FR-018's save-as-new-name half."""
    result = _run(tools_library.promote_to_user_library(block_type="test.promotable", new_name="promotable_v2.py"))
    assert result.filename == "promotable_v2.py"
    assert (user_blocks_dir() / "promotable_v2.py").exists()
    assert not (user_blocks_dir() / "promotable.py").exists()


# ---------------------------------------------------------------------------
# FR-018 / FR-019 — the refusals
# ---------------------------------------------------------------------------


def test_an_existing_library_file_is_reported_not_overwritten(ctx: _StubRuntime) -> None:
    existing = user_blocks_dir() / "promotable.py"
    existing.write_text("# hand-written library block\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        _run(tools_library.promote_to_user_library(block_type="test.promotable"))
    assert existing.read_text(encoding="utf-8") == "# hand-written library block\n"


def test_overwrite_requires_an_explicit_opt_in(ctx: _StubRuntime, project: Path) -> None:
    existing = user_blocks_dir() / "promotable.py"
    existing.write_text("# hand-written library block\n", encoding="utf-8")

    result = _run(tools_library.promote_to_user_library(block_type="test.promotable", overwrite=True))
    assert result.overwritten is True
    assert existing.read_text(encoding="utf-8") == (project / "blocks" / "promotable.py").read_text(encoding="utf-8")


def test_a_builtin_block_cannot_be_promoted(ctx: _StubRuntime) -> None:
    """FR-019: built-in and packaged blocks already live in a library."""
    ctx.block_registry.scan()
    with pytest.raises(RuntimeError, match="already lives in a library"):
        _run(tools_library.promote_to_user_library(block_type="load_data"))


def test_a_block_already_in_the_library_cannot_be_promoted(home: Path, project: Path) -> None:
    """FR-019: promoting it would copy a file onto itself."""
    _write_block(user_blocks_dir(), "already_here")
    runtime = _StubRuntime(_project_dir=project)
    register_block_scan_dirs(runtime.block_registry, project)
    runtime.block_registry.scan()
    _context.set_context(runtime)
    try:
        with pytest.raises(RuntimeError, match="already in the user library"):
            _run(tools_library.promote_to_user_library(block_type="test.already_here"))
    finally:
        _context.set_context(None)


def test_an_unregistered_block_type_raises(ctx: _StubRuntime) -> None:
    with pytest.raises(KeyError):
        _run(tools_library.promote_to_user_library(block_type="test.does_not_exist"))


@pytest.mark.parametrize(
    "new_name",
    ["../escaped.py", "sub/nested.py", "sub\\nested.py", "C:evil.py", "/etc/passwd.py", "notes.txt", "   "],
)
def test_a_hostile_new_name_is_refused(ctx: _StubRuntime, new_name: str) -> None:
    """The destination name is caller-supplied, so it gets the same scrutiny."""
    with pytest.raises((ValueError, PermissionError)):
        _run(tools_library.promote_to_user_library(block_type="test.promotable", new_name=new_name))
    assert list(user_blocks_dir().glob("*.py")) == []


# ---------------------------------------------------------------------------
# FR-065 — the standalone bridge's invalidation channel
# ---------------------------------------------------------------------------


def test_the_standalone_bridge_sees_a_write_from_another_process(home: Path, project: Path) -> None:
    """The bridge used to hold its first scan forever (FR-065).

    Nothing tells it that the API process — or a second bridge, or the user's
    editor — put a file in the shared user library. The drop-in directories are
    the channel, and the runtime re-reads them before handing a registry out.
    """
    runtime = make_mcp_runtime(project)
    assert runtime.block_registry.get_spec("test.written_elsewhere") is None

    _write_block(user_blocks_dir(), "written_elsewhere")

    assert runtime.block_registry.get_spec("test.written_elsewhere") is not None


def test_the_standalone_bridge_sees_a_project_tier_write_too(home: Path, project: Path) -> None:
    """Both tiers are watched, not only the user library."""
    runtime = make_mcp_runtime(project)
    _write_block(project / "blocks", "project_side")
    assert runtime.block_registry.get_spec("test.project_side") is not None


def test_an_unchanged_library_does_not_trigger_a_rescan(home: Path, project: Path) -> None:
    """The check must be cheap enough to run before every registry read."""
    runtime = make_mcp_runtime(project)
    assert runtime.sync_dropins() is False
    assert runtime.sync_dropins() is False

    _write_block(user_blocks_dir(), "now_it_changed")
    assert runtime.sync_dropins() is True
    assert runtime.sync_dropins() is False


def test_the_standalone_bridge_sees_a_deleted_drop_in(home: Path, project: Path) -> None:
    """A removal is a change too — a stale entry is as wrong as a missing one."""
    dropped = _write_block(user_blocks_dir(), "temporary_block")
    runtime = make_mcp_runtime(project)
    assert runtime.block_registry.get_spec("test.temporary_block") is not None

    dropped.unlink()
    assert runtime.block_registry.get_spec("test.temporary_block") is None


def test_promotion_through_a_standalone_bridge_is_immediately_visible(home: Path, project: Path) -> None:
    """FR-011 + FR-065 in the bridge: the tool's own write lands in its view."""
    _write_block(project / "blocks", "bridge_promotable")
    runtime = make_mcp_runtime(project)
    # FR-065 made the two registries read-through properties; the Protocol
    # declares them as plain variables, which mypy reads as read-only.
    _context.set_context(runtime)  # type: ignore[arg-type]
    try:
        result = _run(tools_library.promote_to_user_library(block_type="test.bridge_promotable"))
        assert Path(result.path) == user_blocks_dir() / "bridge_promotable.py"

        elsewhere = BlockRegistry()
        register_block_scan_dirs(elsewhere, None)
        elsewhere.scan()
        assert elsewhere.get_spec("test.bridge_promotable") is not None
    finally:
        _context.set_context(None)
