"""Isolated real panel/preview runtime fixture without external package discovery."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import scistudio.panels
from scistudio.api.runtime.models import DataRecord
from scistudio.core.storage.ref import StorageReference
from scistudio.engine.events import EventBus
from scistudio.panels.descriptor import parse_descriptor
from scistudio.panels.models import OwnerKind, PreviewTarget
from scistudio.panels.registry import PanelRegistry
from scistudio.panels.service import PanelService, get_panel_contexts

#: The registered types the built-in core panels claim.
CORE_PANEL_TYPES = frozenset({"Array", "Artifact", "CompositeData", "DataFrame", "Series", "Text"})
BUILTIN_PANELS = Path(scistudio.panels.__file__).parent / "builtin"


def core_panels() -> PanelRegistry:
    """The built-in core panels, as discovery loads them (``panels/builtin``)."""
    registry = PanelRegistry()
    for child in sorted(BUILTIN_PANELS.iterdir()):
        if child.is_dir() and not child.name.startswith("."):
            registry.load(child, OwnerKind.CORE, CORE_PANEL_TYPES)
    assert not registry.diagnostics, registry.diagnostics
    return registry


def with_core_panels(panels: PanelRegistry) -> PanelRegistry:
    """*panels* over the built-in core panels, the tiers resolved as discovery does."""
    merged = core_panels()
    for panel in panels.panels.values():
        merged.register(panel)
    merged.shadowed.extend(panels.shadowed)
    merged.diagnostics.extend(panels.diagnostics)
    return merged


def install_panel_service(runtime, panels, *, choices=None, core=True):
    """Give a runtime double a real panel service over a fixed catalog.

    ``panels`` is a :class:`PanelRegistry` or a zero-argument callable returning
    the registry the next discovery finds, so a test can change the catalog. The
    built-in core panels are added under it unless ``core`` is false.
    """
    discover = panels if callable(panels) else (lambda: panels)
    service = PanelService(
        runtime,
        discover=lambda _project, _types: with_core_panels(discover()) if core else discover(),
        choices_loader=lambda _project: dict(choices or {}),
    )
    runtime._panel_service = service
    runtime.get_panel_service = lambda: service
    return service


def use_panels(runtime, panels):
    """Make *panels* the catalog the next discovery finds, and rescan now."""
    runtime.test_panels[0] = panels
    return runtime.get_panel_service().rescan(force=True)


def make_runtime(tmp_path):
    directory = tmp_path / "lab.text"
    directory.mkdir()
    (directory / "panel.json").write_text(
        '{"id":"lab.text","api_version":"1.0","contexts":["preview","interactive"],"types":["Text"]}'
    )
    (directory / "index.html").write_text('<script src="script.js"></script>')
    (directory / "script.js").write_text("window.loaded=true")
    (directory / "panel.py").write_text('raise RuntimeError("must never execute")')
    data = tmp_path / "data.txt"
    data.write_text("hello panel")
    panels = PanelRegistry()
    panels.register(
        parse_descriptor(directory, owner_kind=OwnerKind.PROJECT, owner_name="project", registered_types={"Text"})[0]
    )
    record = DataRecord(
        "data-a", StorageReference(backend="filesystem", path=str(data)), "Text", {"chars": 11}, ["DataObject", "Text"]
    )
    runtime = SimpleNamespace(
        active_project=SimpleNamespace(id="p", path=str(tmp_path)),
        data_catalog={"data-a": record},
        workflow_runs={},
        event_bus=EventBus(),
    )
    runtime.event_bus.runtime = runtime
    runtime.get_data_record = lambda ref: runtime.data_catalog[ref]
    runtime.resolve_session_target = lambda target: PreviewTarget(
        kind=target.kind,
        ref=target.ref,
        recorded_type=runtime.data_catalog[target.ref].type_name,
        type_chain=tuple(runtime.data_catalog[target.ref].type_chain),
    )
    runtime.type_registry = SimpleNamespace(
        resolve=lambda name: SimpleNamespace(base_type={"Image": "Array", "Array": "DataObject"}.get(name, ""))
    )
    # A test swaps ``runtime.test_panels[0]`` and rescans to change the catalog.
    runtime.test_panels = [panels]
    install_panel_service(runtime, lambda: runtime.test_panels[0])
    return runtime, get_panel_contexts(runtime)


@pytest.fixture
def panel_runtime(tmp_path):
    return make_runtime(tmp_path)
