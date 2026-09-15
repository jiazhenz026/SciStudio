"""``scistudio.panels`` is a canonical public root (ADR-052 §3, ADR-054; #2426).

The root publishes the author-facing panel checks -- discovery, descriptor
validation, the interactive compatibility check, and the CDN reference check --
and nothing of the runtime machinery. Its re-exports resolve lazily so the
resident panel process, which imports this package first, stays import-light.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scistudio.panels as panels
from scistudio.stability import get_stability

_PUBLIC = {
    "PANEL_API_VERSION",
    "PanelDescriptor",
    "PanelRegistry",
    "discover_panels",
    "parse_descriptor",
    "validate_external_references",
    "validate_interactive_panel",
}


def test_root_all_is_the_author_surface() -> None:
    assert set(panels.__all__) == _PUBLIC


def test_reexports_are_the_defining_objects() -> None:
    from scistudio.panels import descriptor, files, registry, validation

    assert panels.PanelDescriptor is descriptor.PanelDescriptor
    assert panels.parse_descriptor is descriptor.parse_descriptor
    assert panels.PANEL_API_VERSION == descriptor.PANEL_API_VERSION
    assert panels.PanelRegistry is registry.PanelRegistry
    assert panels.discover_panels is registry.discover_panels
    assert panels.validate_external_references is files.validate_external_references
    assert panels.validate_interactive_panel is validation.validate_interactive_panel


def test_every_marked_symbol_is_provisional_since_0_3_5() -> None:
    for name in sorted(_PUBLIC - {"PANEL_API_VERSION"}):
        info = get_stability(getattr(panels, name))
        assert info is not None and (info.tier, info.since) == ("provisional", "0.3.5"), name


def test_runtime_members_stay_internal() -> None:
    internal_members = [
        panels.PanelDescriptor.candidates,
        panels.PanelRegistry.register,
        panels.PanelRegistry.load,
    ]
    for member in internal_members:
        info = get_stability(member)
        assert info is not None and info.tier == "internal", member


def test_unknown_attribute_raises() -> None:
    with pytest.raises(AttributeError):
        _ = panels.PanelContexts  # runtime machinery is not re-exported from the root


@pytest.mark.serial
def test_importing_the_root_stays_light() -> None:
    """The resident panel process imports the package; discovery must not come with it."""
    code = (
        "import sys, scistudio.panels, scistudio.panels.process_config, scistudio.panels.protocol;"
        "heavy = [m for m in ('scistudio.panels.registry', 'scistudio.core.types.registry') if m in sys.modules];"
        "print(heavy)"
    )
    src = str(Path(panels.__file__).resolve().parents[2])
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONPATH": src, "PATH": ""},
    )
    assert result.stdout.strip() == "[]"


def test_parse_descriptor_through_the_root(tmp_path: Path) -> None:
    from scistudio.previewers.models import OwnerKind

    folder = tmp_path / "demo.text"
    folder.mkdir()
    (folder / "index.html").write_text("<!doctype html><p>demo</p>", encoding="utf-8")
    (folder / "panel.json").write_text(
        json.dumps(
            {"id": "demo.text", "api_version": panels.PANEL_API_VERSION, "contexts": ["preview"], "types": ["Text"]}
        ),
        encoding="utf-8",
    )
    descriptor, notes = panels.parse_descriptor(
        folder, owner_kind=OwnerKind.PROJECT, owner_name="project", registered_types={"Text"}
    )
    assert isinstance(descriptor, panels.PanelDescriptor)
    assert descriptor.types == ("Text",)
    assert notes == []
    assert panels.validate_external_references(folder) == []
