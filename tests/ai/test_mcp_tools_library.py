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
import os
import re
from collections.abc import Coroutine, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import pytest

from scistudio.ai.agent.mcp import _context, tools_library
from scistudio.ai.agent.mcp.runtime import dropin_revision, make_mcp_runtime
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.dropins import register_block_scan_dirs, user_blocks_dir, user_types_dir
from scistudio.core.origins import BLOCK_SURFACE, map_block_origin
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


# ---------------------------------------------------------------------------
# FR-003 / FR-019 / FR-025 — E3 and the frontend entry points refuse the same set
# ---------------------------------------------------------------------------
#
# The FR-025 claim in ``promoteToUserLibrary.ts`` and in CHANGELOG.md is that
# this tool matches E1/E2/E5 "refusal for refusal". It did not: the frontend
# condition is ``origin === "project"``, which refuses five origins, while this
# tool asked two narrower questions of its own and accepted the FR-002
# ``custom`` case (``docs/audit/2026-08-07-adr-053-spec1-track-b.md`` P2-2).
# These tests walk the **whole** origin vocabulary, ``custom`` included, so the
# claim is pinned rather than asserted.


@dataclass(frozen=True)
class _OriginSpec:
    """The three fields ``map_block_origin`` reads off a ``BlockSpec``."""

    file_path: str | None = None
    module_path: str = ""
    source: str = ""


def _spec_for_origin(origin: str, *, project: Path, tmp_path: Path) -> _OriginSpec:
    """Return a spec whose resolved origin is *origin*.

    Every drop-in case points at a file that really exists, so a refusal can
    only be about the tier and never about a missing file.
    """
    if origin == "builtin":
        return _OriginSpec(module_path="scistudio.blocks.io.load_data", source="builtin")
    if origin == "package":
        return _OriginSpec(module_path="scistudio_blocks_imaging.segment", source="entry_point")
    if origin == "user":
        return _OriginSpec(file_path=str(_write_block(user_blocks_dir(), "in_library")), source="tier1")
    if origin == "project":
        return _OriginSpec(file_path=str(project / "blocks" / "promotable.py"), source="tier1")
    if origin == "custom":
        # FR-002: a drop-in whose file resolves under neither tier root. A
        # directory outside both stands in for the symlink-escape and
        # other-drive cases the spec names, neither of which this host can
        # create.
        return _OriginSpec(file_path=str(_write_block(tmp_path / "outside", "stray")), source="tier1")
    raise AssertionError(f"no spec shape for origin {origin!r}")


def _frontend_block_origin_vocabulary() -> tuple[str, ...]:
    """Return the ``BlockOrigin`` union declared in ``frontend/src/types/api.ts``.

    Read from the frontend source rather than restated here, because the whole
    point of this section is that the two sides of the wire must not be able to
    drift. A value added on either side alone fails this.
    """
    api_types = Path(__file__).resolve().parents[2] / "frontend" / "src" / "types" / "api.ts"
    declaration = re.search(r"export type BlockOrigin\s*=\s*([^;]+);", api_types.read_text(encoding="utf-8"))
    assert declaration is not None, "BlockOrigin is no longer declared in frontend/src/types/api.ts"
    return tuple(re.findall(r'"([^"]+)"', declaration.group(1)))


def test_the_two_sides_of_the_wire_agree_on_the_origin_vocabulary() -> None:
    """The parity tests below are only meaningful if neither side has extra values."""
    assert set(_frontend_block_origin_vocabulary()) == set(BLOCK_SURFACE.vocabulary)
    assert "custom" in BLOCK_SURFACE.vocabulary, "the FR-002 fallback is the case E3 used to accept"


@pytest.mark.parametrize("origin", BLOCK_SURFACE.vocabulary)
def test_e3_promotes_exactly_the_origins_the_frontend_offers(
    ctx: _StubRuntime, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, origin: str
) -> None:
    """FR-025: E3's accept set is ``isPromotableOrigin``'s, across the vocabulary.

    ``isPromotableOrigin(origin) => origin === "project"``
    (``frontend/src/components/promotion/promotable.ts``) is the condition E1,
    E2 and E5 apply, so the expected answer here is that one line and nothing
    else. Before the shared resolver moved into ``scistudio.core.origins``,
    ``custom`` was the row that disagreed.
    """
    spec = _spec_for_origin(origin, project=project, tmp_path=tmp_path)
    assert map_block_origin(spec, project_dir=project) == origin, "precondition: the fixture builds this tier"
    monkeypatch.setattr(ctx.block_registry, "get_spec", lambda _name: spec)

    frontend_offers_it = origin == "project"

    if frontend_offers_it:
        result = _run(tools_library.promote_to_user_library(block_type="test.promotable"))
        assert Path(result.path) == user_blocks_dir() / "promotable.py"
    else:
        with pytest.raises(RuntimeError):
            _run(tools_library.promote_to_user_library(block_type="test.promotable"))


def test_a_dropin_outside_both_tiers_is_refused_with_a_reason_the_agent_can_act_on(
    ctx: _StubRuntime, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ``custom`` row, stated once in full rather than only parametrised.

    This is the refusal the tool did not have. The message has to tell the
    agent what to do next, because ``custom`` is not a word the user ever sees.
    """
    spec = _spec_for_origin("custom", project=project, tmp_path=tmp_path)
    monkeypatch.setattr(ctx.block_registry, "get_spec", lambda _name: spec)

    with pytest.raises(RuntimeError, match="resolves outside both"):
        _run(tools_library.promote_to_user_library(block_type="test.stray"))

    assert list(user_blocks_dir().glob("*.py")) == [], "a refused promotion writes nothing"


def test_every_non_project_origin_has_its_own_refusal_message() -> None:
    """A new tier cannot fall through to a vague message — or to acceptance."""
    refused = {origin for origin in BLOCK_SURFACE.vocabulary if origin != "project"}
    assert set(tools_library._REFUSAL_BY_ORIGIN) == refused
    assert len({tools_library._refusal_for(origin) for origin in refused}) == len(refused)


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


# ---------------------------------------------------------------------------
# FR-065 — what the change detector can see (AUDIT-SEC P3-9, P3-2)
# ---------------------------------------------------------------------------


def test_the_change_detector_sees_a_package_shaped_dropin(home: Path, project: Path) -> None:
    """``<name>/__init__.py`` is a drop-in the FR-016 guard already governs.

    It was invisible to ``dropin_revision``, which stats only ``*.py`` entries
    directly under each scan dir — so editing a package-shaped drop-in type
    never moved the signature and the standalone bridge never re-scanned
    (``docs/audit/2026-08-07-adr-053-spec1-write-path.md`` P3-9).
    """
    package = user_types_dir() / "package_shaped"
    package.mkdir(parents=True)
    init = package / "__init__.py"
    init.write_text("VALUE = 1\n", encoding="utf-8")

    before = dropin_revision([user_types_dir()])
    assert before, "the package must contribute to the signature at all"

    init.write_text("VALUE = 2\n", encoding="utf-8")
    os.utime(init, (1_700_000_000, 1_700_000_000))

    assert dropin_revision([user_types_dir()]) != before


def test_the_change_detector_sees_an_uppercase_suffix(home: Path, project: Path) -> None:
    """Windows ``glob("*.py")`` is case-insensitive, so ``.PY`` is a live drop-in.

    The write endpoints refuse to create one, but a user can still place one by
    hand, and a case-sensitive comparison here meant editing it never moved the
    signature (P3-2).
    """
    shouty = user_blocks_dir() / "SHOUT.PY"
    shouty.write_text("VALUE = 1\n", encoding="utf-8")

    before = dropin_revision([user_blocks_dir()])
    assert before

    shouty.write_text("VALUE = 22\n", encoding="utf-8")

    assert dropin_revision([user_blocks_dir()]) != before


def test_a_directory_without_an_init_contributes_nothing(home: Path, project: Path) -> None:
    """A plain subdirectory is not importable, so it is not a drop-in."""
    (user_types_dir() / "not_a_package").mkdir(parents=True)

    assert dropin_revision([user_types_dir()]) == ()
