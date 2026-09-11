"""ADR-054 descriptor, confinement and external-reference contracts."""

import json

import pytest

from scistudio.blocks.base.interactive import PanelManifest
from scistudio.panels.descriptor import parse_descriptor
from scistudio.panels.files import resolve_panel_file
from scistudio.panels.validation import validate_external_references, validate_interactive_panel
from scistudio.previewers.models import OwnerKind


def parse(tmp_path, **fields):
    folder = tmp_path / fields.pop("folder", "lab.test")
    folder.mkdir(exist_ok=True)
    (folder / "index.html").write_text("<p>Panel</p>")
    (folder / "panel.json").write_text(
        json.dumps({"id": folder.name, "contexts": ["preview"], "types": ["Image"], "api_version": "1.0", **fields})
    )
    return parse_descriptor(
        folder, owner_kind=OwnerKind.PROJECT, owner_name="project", registered_types={"Image", "Text"}
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"id": "other.id"},
        {"api_version": "2.0"},
        {"api_version": "1"},
        {"contexts": []},
        {"contexts": ["call"]},
        {"types": []},
        {"types": ["Unknown"]},
        {"types": ["DataObject"]},
        {"types": ["Collection[Unknown]"]},
        {"priority": True},
        {"entry": "../index.html"},
        {"folder": "core.test"},
        {"contexts": ["miniapp"], "types": ["Image", "Text"]},
    ],
)
def test_descriptor_refuses_invalid_contract(tmp_path, fields):
    with pytest.raises(ValueError):
        parse(tmp_path, **fields)


def test_multi_type_preview_and_miniapp_shape_without_python_execution(tmp_path):
    panel, notes = parse(tmp_path, types=["Image", "Collection[Text]"], extra=True)
    assert len(panel.candidates()) == 2
    assert panel.candidates()[1].supports_collection
    assert "unknown key" in notes[0]
    panel, _ = parse(tmp_path, contexts=["miniapp"], types=["Image"])
    assert panel.candidates() == []


def test_entry_dot_segments_are_canonicalized(tmp_path):
    panel, _ = parse(tmp_path, entry="./index.html")
    assert panel.entry == "index.html"


def test_python_and_traversal_and_symlink_escape_refused(panel_runtime, tmp_path):
    runtime, _ = panel_runtime
    panel = runtime.get_preview_service().registry.panels.get("lab.text")
    for path in ("panel.py", "../data.txt", "/etc/passwd", "https://example.com/file.js"):
        with pytest.raises(ValueError):
            resolve_panel_file(panel.root, path)
    (panel.root / "escape.js").symlink_to(tmp_path / "data.txt")
    with pytest.raises(ValueError):
        resolve_panel_file(panel.root, "escape.js")
    assert panel.has_python


def test_resolve_panel_file_confines_nested_assets_and_symlinked_directories(tmp_path):
    root = tmp_path / "panel"
    (root / "assets").mkdir(parents=True)
    nested = root / "assets" / "app.js"
    nested.write_text("export const x = 1;")
    # A legitimate nested asset resolves to the confined file.
    assert resolve_panel_file(root, "assets/app.js") == nested.resolve()
    # A symlinked directory that leaves the root is rejected by containment.
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.js").write_text("export const y = 2;")
    (root / "away").symlink_to(outside)
    with pytest.raises(ValueError):
        resolve_panel_file(root, "away/leak.js")


def test_external_reference_allowlist_and_pin_diagnostic(tmp_path):
    (tmp_path / "index.html").write_text('<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script>')
    assert validate_external_references(tmp_path) == []
    (tmp_path / "index.html").write_text('<script src="https://unpkg.com/d3"></script>')
    assert "unpinned" in validate_external_references(tmp_path)[0]
    (tmp_path / "index.html").write_text('<script src="https://evil.example/x.js"></script>')
    with pytest.raises(ValueError, match="allowlist"):
        validate_external_references(tmp_path)


def test_interactive_validation_preserves_only_known_core_legacy(panel_runtime):
    runtime, _ = panel_runtime
    registry = runtime.get_preview_service().registry.panels
    validate_interactive_panel(PanelManifest(panel_id="lab.text"), registry)
    validate_interactive_panel(PanelManifest(panel_id="core.interactive.data_router"), registry)
    with pytest.raises(ValueError, match="interactive context required"):
        validate_interactive_panel(PanelManifest(panel_id="pkg.missing"), registry)
