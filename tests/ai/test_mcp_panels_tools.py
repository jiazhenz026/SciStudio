"""The agent's MiniApp tools (ADR-054 MiniApp FR-029, FR-030).

``docs/specs/adr-054-miniapp.md`` User Story 4: a user who has never opened the
MiniApps tab asks in chat, and the agent writes a MiniApp, checks it, and opens
it. Its three acceptance scenarios are the three things pinned here.

1. A valid MiniApp directory returns no error diagnostics.
2. With a workspace connected, ``open_miniapp`` broadcasts
   ``panel.open_miniapp`` carrying the panel id and the target.
3. With no workspace connected, the tool reports that no workspace is open —
   the one case where reporting success would send the user to look at a tab
   that does not exist.

Workspace presence is read from :mod:`scistudio.engine.gui_presence` (the Phase
D contract §2.1 surface), stubbed here through ``sys.modules`` so these tests
exercise the real import path and the real attribute name rather than a seam of
the tool's own.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types as pytypes
from collections.abc import Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import pytest

from scistudio.ai.agent.mcp import _context, tools_panels

_T = TypeVar("_T")

PANEL_PAGE = """<!doctype html>
<html lang="en">
  <head><meta charset="utf-8" /><title>Threshold explorer</title></head>
  <body>
    <div id="root"></div>
    <script src="../../sdk/1/scistudio-panel.js"></script>
  </body>
</html>
"""

PANEL_PY = '''"""Fixture MiniApp python."""


def setup(data):
    return None


def threshold(level):
    return {"level": level}
'''


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(coro)


class _StubTypeRegistry:
    """The two methods the panel tools ask of a type registry.

    ``bases`` maps a type name to its parent, the ancestry ``list_panels``
    follows (through ``scistudio.panels.targets.type_chain``) to match a
    MiniApp declaring a parent type.
    """

    def __init__(self, names: tuple[str, ...], bases: dict[str, str] | None = None) -> None:
        self._names = {name: object() for name in names}
        self._bases = dict(bases or {})

    def all_types(self) -> dict[str, Any]:
        return dict(self._names)

    def resolve(self, name: str) -> Any:
        if name not in self._names:
            raise KeyError(name)
        return pytypes.SimpleNamespace(name=name, base_type=self._bases.get(name, ""))


class _RecordingEventBus:
    """Captures what the tool broadcast, in emit order."""

    def __init__(self) -> None:
        self.emitted: list[Any] = []

    async def emit(self, event: Any) -> None:
        self.emitted.append(event)


@dataclass
class _StubRuntime:
    """The MCPContext surface the panel tools reach for, and no more."""

    type_registry: _StubTypeRegistry = field(default_factory=lambda: _StubTypeRegistry(("Image",)))
    block_registry: Any = None
    _project_dir: Path | None = None
    active_workflow_id: str | None = None
    event_bus: Any = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


def _write_miniapp(
    project: Path,
    panel_id: str = "demo.threshold",
    *,
    descriptor: dict[str, Any] | None = None,
    page: str = PANEL_PAGE,
    python: str | None = PANEL_PY,
) -> Path:
    directory = project / "panels" / panel_id
    directory.mkdir(parents=True)
    body = (
        descriptor
        if descriptor is not None
        else {
            "id": panel_id,
            "api_version": "1.0",
            "contexts": ["miniapp"],
            "types": ["Image"],
            "name": "Threshold explorer",
            "description": "Drag a threshold across the stack and see the mask.",
            "entry": "index.html",
        }
    )
    (directory / "panel.json").write_text(json.dumps(body), encoding="utf-8")
    (directory / "index.html").write_text(page, encoding="utf-8")
    if python is not None:
        (directory / "panel.py").write_text(python, encoding="utf-8")
    return directory


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated project whose user tier is empty.

    ``Path.home`` is redirected because panel discovery scans the user library
    tier unconditionally; without this the developer's own installed MiniApps
    would join the registry these tests assert over.
    """
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    fake_home = tmp_path / "home"
    (fake_home / ".scistudio").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return project_dir


@pytest.fixture
def runtime(project: Path) -> Any:
    """Install a stub MCP context for the duration of one test."""
    ctx = _StubRuntime(_project_dir=project, event_bus=_RecordingEventBus())
    _context.set_context(ctx)
    try:
        yield ctx
    finally:
        _context.set_context(None)


@pytest.fixture
def workspace(monkeypatch: pytest.MonkeyPatch):
    """Control what ``scistudio.engine.gui_presence`` reports, via the real import.

    Returns a setter; the default is "no workspace", so a test that forgets to
    say otherwise gets the honest answer rather than a silent success.
    """
    import scistudio.engine as engine_package

    state = {"connected": False}
    module = pytypes.ModuleType("scistudio.engine.gui_presence")
    module.any_connected = lambda: state["connected"]  # type: ignore[attr-defined]
    module.connected = lambda: ("ws-test",) if state["connected"] else ()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scistudio.engine.gui_presence", module)
    # Both halves: ``from package import submodule`` prefers an attribute already
    # bound on the package and only falls back to sys.modules, so stubbing one
    # alone works before the real module exists and stops working after it does.
    monkeypatch.setattr(engine_package, "gui_presence", module, raising=False)

    def _set(connected: bool) -> None:
        state["connected"] = connected

    return _set


# ---------------------------------------------------------------------------
# US4 scenario 1 — a valid MiniApp directory returns no error diagnostics.
# ---------------------------------------------------------------------------


def test_validate_panel_reports_no_errors_for_a_valid_miniapp(project: Path, runtime: Any) -> None:
    _write_miniapp(project)

    result = _run(tools_panels.validate_panel(path="panels/demo.threshold"))

    assert result.errors == []
    assert result.valid is True
    assert result.panel_id == "demo.threshold"
    assert result.contexts == ["miniapp"]
    assert result.types == ["Image"]
    assert result.has_python is True


def test_validate_panel_accepts_a_project_relative_or_absolute_path(project: Path, runtime: Any) -> None:
    directory = _write_miniapp(project)

    relative = _run(tools_panels.validate_panel(path="panels/demo.threshold"))
    absolute = _run(tools_panels.validate_panel(path=str(directory)))

    assert relative.path == absolute.path


def test_validate_panel_names_the_rule_a_bad_descriptor_fails(project: Path, runtime: Any) -> None:
    """A MiniApp declaring two types fails MiniApp FR-001, and the text says so."""
    _write_miniapp(
        project,
        descriptor={
            "id": "demo.threshold",
            "api_version": "1.0",
            "contexts": ["miniapp"],
            "types": ["Image", "DataFrame"],
            "name": "Threshold explorer",
        },
    )

    result = _run(tools_panels.validate_panel(path="panels/demo.threshold"))

    assert result.valid is False
    assert len(result.errors) == 1
    assert "miniapp requires exactly one type" in result.errors[0]
    assert result.panel_id is None


def test_validate_panel_refuses_an_off_allowlist_script(project: Path, runtime: Any) -> None:
    """FR-038: a page pulling a script from anywhere but the CDN allowlist is an error."""
    _write_miniapp(
        project,
        page=PANEL_PAGE.replace(
            '<div id="root"></div>',
            '<script src="https://example.com/evil.js"></script>',
        ),
    )

    result = _run(tools_panels.validate_panel(path="panels/demo.threshold"))

    assert result.valid is False
    assert "outside CDN allowlist" in result.errors[0]


def test_validate_panel_reports_an_unpinned_cdn_as_a_warning(project: Path, runtime: Any) -> None:
    """An unpinned allowlisted reference does not stop discovery but is still reported."""
    _write_miniapp(
        project,
        page=PANEL_PAGE.replace(
            '<div id="root"></div>',
            '<script src="https://cdn.jsdelivr.net/npm/d3/dist/d3.min.js"></script>',
        ),
    )

    result = _run(tools_panels.validate_panel(path="panels/demo.threshold"))

    assert result.valid is True
    assert result.errors == []
    assert any("unpinned CDN reference" in note for note in result.warnings)


def test_validate_panel_refuses_a_path_outside_the_project(project: Path, runtime: Any) -> None:
    with pytest.raises(PermissionError):
        _run(tools_panels.validate_panel(path="../escape"))


def test_validate_panel_refuses_a_path_that_is_not_a_directory(project: Path, runtime: Any) -> None:
    _write_miniapp(project)
    with pytest.raises(NotADirectoryError):
        _run(tools_panels.validate_panel(path="panels/demo.threshold/panel.json"))


# ---------------------------------------------------------------------------
# US4 scenario 2 — with a workspace connected, the event is broadcast.
# ---------------------------------------------------------------------------


def test_open_miniapp_broadcasts_the_event_when_a_workspace_is_connected(
    project: Path, runtime: Any, workspace: Any
) -> None:
    _write_miniapp(project)
    workspace(True)

    result = _run(
        tools_panels.open_miniapp(
            panel_id="demo.threshold",
            workflow_id="wf-1",
            block_id="segment",
            port="mask",
        )
    )

    assert result.opened is True
    assert result.reason is None
    (event,) = runtime.event_bus.emitted
    assert event.event_type == "panel.open_miniapp"
    assert event.data == {
        "panel_id": "demo.threshold",
        "workflow_id": "wf-1",
        "block_id": "segment",
        "port": "mask",
    }


def test_open_miniapp_event_type_matches_the_realtime_contract() -> None:
    """The outbound event name is a bare string shared with api/ws.py (ADR-035/036)."""
    assert tools_panels.PANEL_OPEN_MINIAPP_EVENT_TYPE == "panel.open_miniapp"


def test_open_miniapp_reports_a_failed_broadcast_rather_than_success(
    project: Path, runtime: Any, workspace: Any
) -> None:
    _write_miniapp(project)
    workspace(True)

    class _BrokenBus:
        async def emit(self, event: Any) -> None:
            raise RuntimeError("bus closed")

    runtime.event_bus = _BrokenBus()

    result = _run(
        tools_panels.open_miniapp(panel_id="demo.threshold", workflow_id="wf-1", block_id="segment", port="mask")
    )

    assert result.opened is False
    assert result.reason == tools_panels.BROADCAST_FAILED


def test_open_miniapp_refuses_an_unknown_panel(project: Path, runtime: Any, workspace: Any) -> None:
    _write_miniapp(project)
    workspace(True)

    with pytest.raises(KeyError) as excinfo:
        _run(tools_panels.open_miniapp(panel_id="demo.absent", workflow_id="wf-1", block_id="segment", port="mask"))

    # The refusal names what IS available so the agent can retry without guessing.
    assert "demo.threshold" in str(excinfo.value)
    assert runtime.event_bus.emitted == []


def test_open_miniapp_refuses_a_panel_that_is_not_a_miniapp(project: Path, runtime: Any, workspace: Any) -> None:
    _write_miniapp(
        project,
        panel_id="demo.preview",
        descriptor={
            "id": "demo.preview",
            "api_version": "1.0",
            "contexts": ["preview"],
            "types": ["Image"],
            "name": "A preview panel",
        },
        python=None,
    )
    workspace(True)

    with pytest.raises(ValueError, match="cannot be opened as a MiniApp"):
        _run(tools_panels.open_miniapp(panel_id="demo.preview", workflow_id="wf-1", block_id="segment", port="mask"))

    assert runtime.event_bus.emitted == []


# ---------------------------------------------------------------------------
# US4 scenario 3 — with no workspace connected, the tool says so.
# ---------------------------------------------------------------------------


def test_open_miniapp_reports_no_workspace_when_none_is_connected(project: Path, runtime: Any, workspace: Any) -> None:
    _write_miniapp(project)
    workspace(False)

    result = _run(
        tools_panels.open_miniapp(panel_id="demo.threshold", workflow_id="wf-1", block_id="segment", port="mask")
    )

    assert result.opened is False
    assert result.reason == tools_panels.NO_WORKSPACE
    assert "No SciStudio workspace is open" in result.detail
    # Nothing was broadcast: an event nobody receives is worse than a refusal,
    # because the agent would read it as success.
    assert runtime.event_bus.emitted == []


def test_open_miniapp_reports_a_runtime_with_no_event_bus(project: Path, runtime: Any, workspace: Any) -> None:
    """A standalone bridge session has no realtime channel at all."""
    _write_miniapp(project)
    workspace(True)
    runtime.event_bus = None

    result = _run(
        tools_panels.open_miniapp(panel_id="demo.threshold", workflow_id="wf-1", block_id="segment", port="mask")
    )

    assert result.opened is False
    assert result.reason == tools_panels.NO_EVENT_BUS


def test_open_miniapp_in_a_standalone_session_reports_no_event_bus(project: Path, runtime: Any, workspace: Any) -> None:
    """#2422: a standalone bridge has no channel and no window, and says ``no_event_bus``."""
    _write_miniapp(project)
    workspace(False)
    runtime.event_bus = None

    result = _run(
        tools_panels.open_miniapp(panel_id="demo.threshold", workflow_id="wf-1", block_id="segment", port="mask")
    )

    assert result.opened is False
    assert result.reason == tools_panels.NO_EVENT_BUS
    assert "no realtime channel" in result.detail


# ---------------------------------------------------------------------------
# list_panels (#2441, #2445) — the panels that exist, their kinds, and why a
# directory is not one.
# ---------------------------------------------------------------------------


def _descriptor(panel_id: str, type_name: str, *, contexts: tuple[str, ...] = ("miniapp",)) -> dict[str, Any]:
    return {
        "id": panel_id,
        "api_version": "1.0",
        "contexts": list(contexts),
        "types": [type_name],
        "name": panel_id.replace("_", " ").title(),
        "entry": "index.html",
    }


def _user_panels() -> Path:
    return Path.home() / ".scistudio" / "panels"


def _local(panels: list[Any]) -> list[Any]:
    """The panels the test wrote: the project and user tiers, not the built-ins."""
    return [panel for panel in panels if panel.tier in ("project", "user")]


def test_list_panels_lists_every_kind_across_tiers(project: Path, runtime: Any) -> None:
    _write_miniapp(project)
    preview = _descriptor("plate_preview", "Image", contexts=("preview",)) | {"priority": 7, "description": "Plates."}
    _write_miniapp(project, "plate_preview", descriptor=preview)
    _write_miniapp(
        project, "both", descriptor=_descriptor("both", "Image", contexts=("miniapp", "preview")), python=None
    )
    user_dir = _write_miniapp(_user_panels().parent, "mine", descriptor=_descriptor("mine", "Image"), python=None)

    result = _run(tools_panels.list_panels())

    by_id = {panel.panel_id: panel for panel in result.panels}
    assert {panel.panel_id for panel in _local(result.panels)} == {"demo.threshold", "plate_preview", "both", "mine"}
    project_app = by_id["demo.threshold"]
    assert project_app.kinds == ["miniapp"]
    assert project_app.tier == "project"
    assert project_app.package is None
    assert project_app.name == "Threshold explorer"
    assert project_app.types == ["Image"]
    assert project_app.entry == "index.html"
    assert project_app.has_python is True
    assert project_app.path == "panels/demo.threshold"
    assert project_app.priority is None
    plate = by_id["plate_preview"]
    assert plate.kinds == ["preview"]
    assert plate.priority == 7
    assert plate.description == "Plates."
    # Kinds follow the descriptor's own context order, whatever order panel.json used.
    assert by_id["both"].kinds == ["preview", "miniapp"]
    user_app = by_id["mine"]
    assert user_app.tier == "user"
    assert user_app.has_python is False
    # Outside the project, the path stays absolute.
    assert user_app.path == str(user_dir.resolve())
    # The core tier ships preview and interactive panels; they are listed too.
    core = [panel for panel in result.panels if panel.tier == "core"]
    assert any("preview" in panel.kinds for panel in core)
    assert any("interactive" in panel.kinds for panel in core)
    assert all(not panel.path.startswith("panels/") for panel in core)
    assert result.kind is None
    assert result.data_type is None
    assert result.invalid == []
    names = [(panel.name.lower(), panel.panel_id) for panel in result.panels]
    assert names == sorted(names)


def test_list_panels_filters_by_kind(project: Path, runtime: Any) -> None:
    _write_miniapp(project)
    _write_miniapp(project, "plate_preview", descriptor=_descriptor("plate_preview", "Image", contexts=("preview",)))

    def ids(kind: str | None) -> set[str]:
        return {panel.panel_id for panel in _local(_run(tools_panels.list_panels(kind=kind)).panels)}

    assert ids("miniapp") == {"demo.threshold"}
    assert ids("preview") == {"plate_preview"}
    assert ids("interactive") == set()
    interactive = _run(tools_panels.list_panels(kind="interactive"))
    assert interactive.kind == "interactive"
    assert interactive.panels and all("interactive" in panel.kinds for panel in interactive.panels)
    assert _run(tools_panels.list_panels(kind="  ")).kind is None
    with pytest.raises(ValueError, match="Unknown panel kind"):
        _run(tools_panels.list_panels(kind="previewer"))


def test_list_panels_reports_directories_discovery_skipped(project: Path, runtime: Any) -> None:
    _write_miniapp(project)
    _write_miniapp(
        project,
        "two_types",
        descriptor={"id": "two_types", "api_version": "1.0", "contexts": ["miniapp"], "types": ["Image", "DataFrame"]},
    )
    (project / "panels" / "empty_dir").mkdir()

    result = _run(tools_panels.list_panels())

    assert [panel.panel_id for panel in _local(result.panels)] == ["demo.threshold"]
    invalid = {entry.panel_id: entry for entry in result.invalid}
    assert set(invalid) == {"two_types", "empty_dir"}
    assert invalid["two_types"].tier == "project"
    assert invalid["two_types"].path == "panels/two_types"
    assert any("miniapp requires exactly one type" in note for note in invalid["two_types"].diagnostics)
    assert invalid["empty_dir"].diagnostics
    # The same text validate_panel gives for that directory.
    validated = _run(tools_panels.validate_panel(path="panels/two_types"))
    assert validated.errors[0].endswith(invalid["two_types"].diagnostics[0])
    assert result.invalid_truncated == 0


def test_list_panels_bounds_the_invalid_directories(project: Path, runtime: Any) -> None:
    for index in range(tools_panels._MAX_INVALID_DIRECTORIES + 5):
        (project / "panels" / f"broken_{index:02d}").mkdir(parents=True)

    result = _run(tools_panels.list_panels())

    assert len(result.invalid) == tools_panels._MAX_INVALID_DIRECTORIES
    assert result.invalid_truncated == 5


def test_list_panels_filters_by_the_type_a_panel_accepts(project: Path, runtime: Any) -> None:
    runtime.type_registry = _StubTypeRegistry(("Image", "Microscopy", "DataFrame"), bases={"Microscopy": "Image"})
    _write_miniapp(project, "image_app", descriptor=_descriptor("image_app", "Image"))
    _write_miniapp(project, "image_set_app", descriptor=_descriptor("image_set_app", "Collection[Image]"))
    _write_miniapp(project, "microscopy_app", descriptor=_descriptor("microscopy_app", "Microscopy"))
    _write_miniapp(project, "table_app", descriptor=_descriptor("table_app", "DataFrame"))
    _write_miniapp(
        project,
        "multi_preview",
        descriptor=_descriptor("multi_preview", "DataFrame", contexts=("preview",))
        | {"types": ["DataFrame", "Collection[Microscopy]"]},
    )

    def ids(data_type: str | None) -> set[str]:
        listed = _run(tools_panels.list_panels(data_type=data_type)).panels
        return {panel.panel_id for panel in _local(listed)}

    assert ids(None) == {"image_app", "image_set_app", "microscopy_app", "table_app", "multi_preview"}
    assert ids("Image") == {"image_app"}
    # A panel declaring a parent type accepts the subtype, not the reverse.
    assert ids("Microscopy") == {"image_app", "microscopy_app"}
    assert ids("Collection[Microscopy]") == {"image_set_app", "multi_preview"}
    assert ids("Collection[Image]") == {"image_set_app"}
    assert ids("Collection") == set()
    # Any one declared type is enough.
    assert ids("DataFrame") == {"table_app", "multi_preview"}
    assert ids("Unregistered") == set()
    assert _run(tools_panels.list_panels(data_type=" Image ")).data_type == "Image"
    assert _run(tools_panels.list_panels(data_type="  ")).data_type is None


def test_list_panels_data_type_filter_leaves_out_panels_declaring_no_types(project: Path, runtime: Any) -> None:
    interactive = _run(tools_panels.list_panels(kind="interactive")).panels
    untyped = [panel for panel in interactive if not panel.types]
    assert untyped, "the core tier ships an interactive panel declaring no types"
    filtered = {panel.panel_id for panel in _run(tools_panels.list_panels(data_type="Image")).panels}
    assert not filtered & {panel.panel_id for panel in untyped}


def test_every_listed_miniapp_is_one_open_miniapp_accepts(project: Path, runtime: Any, workspace: Any) -> None:
    _write_miniapp(project)
    _write_miniapp(project, "second", descriptor=_descriptor("second", "Image"), python=None)
    _write_miniapp(project, "plate_preview", descriptor=_descriptor("plate_preview", "Image", contexts=("preview",)))
    _write_miniapp(
        project,
        "two_types",
        descriptor={"id": "two_types", "api_version": "1.0", "contexts": ["miniapp"], "types": ["Image", "DataFrame"]},
    )
    workspace(False)
    target = {"workflow_id": "wf-1", "block_id": "segment", "port": "mask"}

    result = _run(tools_panels.list_panels())

    miniapps = [panel for panel in result.panels if "miniapp" in panel.kinds]
    assert {panel.panel_id for panel in miniapps} == {"demo.threshold", "second"}
    assert {panel.panel_id for panel in _run(tools_panels.list_panels(kind="miniapp")).panels} == {
        "demo.threshold",
        "second",
    }
    for app in miniapps:
        opened = _run(tools_panels.open_miniapp(panel_id=app.panel_id, **target))
        assert opened.reason == tools_panels.NO_WORKSPACE
    # Listed panels of the other kinds are not opened as MiniApps.
    for panel in result.panels:
        if "miniapp" not in panel.kinds:
            with pytest.raises(ValueError):
                _run(tools_panels.open_miniapp(panel_id=panel.panel_id, **target))
    with pytest.raises(KeyError):
        _run(tools_panels.open_miniapp(panel_id="two_types", **target))


def test_list_panels_refuses_without_an_open_project(project: Path) -> None:
    _context.set_context(_StubRuntime(_project_dir=None))
    try:
        with pytest.raises(RuntimeError, match="No project is currently open"):
            _run(tools_panels.list_panels())
    finally:
        _context.set_context(None)


# ---------------------------------------------------------------------------
# Registration.
# ---------------------------------------------------------------------------


def test_the_panel_tools_are_registered_on_the_local_transport() -> None:
    """The module must be in the eager-import tuple, and neither tool external-only.

    A tool module missing from ``mcp/__init__.py`` registers nothing while every
    count assertion still passes, and an ``audience:external`` tag would hide
    these from the local socket the GUI agent talks on.
    """
    from scistudio.ai.agent.mcp.server import AUDIENCE_EXTERNAL_TAG, mcp

    by_name = {tool.name: tool for tool in _run(mcp.list_tools())}
    for name, mutation in (("validate_panel", "read"), ("open_miniapp", "write"), ("list_panels", "read")):
        tool = by_name[name]
        tags = set(tool.tags or set())
        assert "category:panels" in tags
        assert mutation in tags
        assert AUDIENCE_EXTERNAL_TAG not in tags


def test_the_presence_module_the_tool_reads_has_the_pinned_surface() -> None:
    """ADR-054 Phase D contract §2.1: the realtime layer owns this module.

    Skipped until the realtime slice lands it. Once it does, this is what stops
    ``open_miniapp`` degrading silently if the surface is renamed.
    """
    gui_presence = pytest.importorskip("scistudio.engine.gui_presence")

    assert callable(gui_presence.any_connected)
    assert callable(gui_presence.connected)
    assert isinstance(gui_presence.any_connected(), bool)
