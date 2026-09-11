"""Panel directory discovery, reload, type contracts and tier namespace."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from scistudio.panels.registry import discover_panels
from scistudio.previewers.models import OwnerKind, PreviewerSpec
from scistudio.previewers.registry import PreviewerRegistry


def folder(root: Path, panel_id: str = "lab.view", **fields):
    import json

    panel = root / panel_id
    panel.mkdir(parents=True)
    (panel / "index.html").write_text("<p>hello</p>")
    (panel / "panel.json").write_text(
        json.dumps({"id": panel_id, "api_version": "1.0", "contexts": ["preview"], "types": ["Text"], **fields})
    )
    return panel


def test_discovery_project_user_package_tiers_and_diagnostics(tmp_path, monkeypatch):
    from scistudio.panels import registry

    user = tmp_path / "user"
    project = tmp_path / "project"
    package = tmp_path / "package"
    folder(user / "panels")
    folder(project / "panels")
    package_panel = folder(package, "pkg.view")
    folder(project / "panels", "bad.view", api_version="2.0")
    monkeypatch.setattr(registry, "panel_scan_dirs", lambda _: (project / "panels", user / "panels"))
    monkeypatch.setattr(registry, "enumerate_group", lambda *_args, **_kw: [SimpleNamespace(name="package")])
    monkeypatch.setattr(registry, "load_entry_point", lambda *_args, **_kw: lambda: [package_panel])
    panels = discover_panels(project, registered_types={"Text"})
    assert panels.get("lab.view").owner_kind is OwnerKind.PROJECT
    assert panels.get("pkg.view").owner_kind is OwnerKind.PACKAGE
    assert len(panels.shadowed) == 1
    assert any("unsupported api_version" in note for note in panels.diagnostics)
    (project / "panels" / "lab.view" / "panel.json").write_text("{broken")
    reloaded = discover_panels(project, registered_types={"Text"})
    assert reloaded.get("lab.view").owner_kind is OwnerKind.USER
    assert any("FR-003" in note for note in reloaded.diagnostics)


def test_nonpreview_panel_reserves_namespace_and_never_routes(panel_runtime):
    runtime, _ = panel_runtime
    from scistudio.panels.registry import PanelRegistry

    panel = replace(runtime.get_preview_service().registry.panels.get("lab.text"), contexts=("interactive",), types=())
    panels = PanelRegistry()
    panels.register(panel)
    registry = PreviewerRegistry()
    registry.register(PreviewerSpec("lab.text", OwnerKind.USER, "user", "Text"))
    registry.install_panels(panels)
    assert registry.get("lab.text").panel is not None
    assert registry.all_specs() == []


def test_panel_roots_share_tutorial_library_substitution(tmp_path, monkeypatch):
    import scistudio.core.dropins as dropins

    library = tmp_path / "tutorial-library"
    monkeypatch.setattr(dropins, "library_root_for_project", lambda _project: library)
    assert dropins.panel_scan_dirs(tmp_path / "project") == (tmp_path / "project" / "panels", library / "panels")
