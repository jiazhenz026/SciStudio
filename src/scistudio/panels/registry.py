"""Four-tier discovery and a single namespace shared with legacy previewers."""

from __future__ import annotations

import os
from collections.abc import Collection
from pathlib import Path

from scistudio.core.dropins import panel_scan_dirs, register_type_scan_dirs
from scistudio.core.entry_points import (
    EntryPointDiagnostic,
    enumerate_group,
    load_entry_point,
    prepared_plugin_import_roots,
)
from scistudio.panels.descriptor import PanelDescriptor, parse_descriptor
from scistudio.previewers.models import OwnerKind

TIER_ORDER = {OwnerKind.PROJECT: 0, OwnerKind.USER: 1, OwnerKind.PACKAGE: 2, OwnerKind.CORE: 3}

#: Files whose content decides whether a directory is a panel and what it declares.
PANEL_DESCRIPTOR_FILES = ("panel.json", "panel.py")
#: Directory names inside a panel directory that never hold the page.
SKIPPED_PANEL_PARTS = frozenset({"__pycache__", "node_modules"})

PanelSourcesFingerprint = tuple[tuple[object, ...], ...]


class PanelRegistry:
    """Descriptor-only registry. Context authority never comes from a manifest."""

    def __init__(self) -> None:
        self.panels: dict[str, PanelDescriptor] = {}
        self.shadowed: list[PanelDescriptor] = []
        self.diagnostics: list[str] = []

    def register(self, panel: PanelDescriptor) -> None:
        previous = self.panels.get(panel.id)
        if previous is not None:
            if TIER_ORDER[panel.owner_kind] >= TIER_ORDER[previous.owner_kind]:
                self.shadowed.append(panel)
                self.diagnostics.append(
                    f"panel {panel.id!r} ({panel.owner_kind.value}) shadowed by {previous.owner_kind.value}"
                )
                return
            self.shadowed.append(previous)
            self.diagnostics.append(
                f"panel {previous.id!r} ({previous.owner_kind.value}) shadowed by {panel.owner_kind.value}"
            )
        self.panels[panel.id] = panel

    def get(self, panel_id: str) -> PanelDescriptor | None:
        return self.panels.get(panel_id)

    def load(self, path: Path, owner: OwnerKind, types: Collection[str], owner_name: str = "") -> None:
        try:
            panel, notes = parse_descriptor(
                path, owner_kind=owner, owner_name=owner_name or owner.value, registered_types=types
            )
            from scistudio.panels.files import validate_external_references

            notes.extend(validate_external_references(panel.root))
            self.register(panel)
            self.diagnostics.extend(f"{path}: {note}" for note in notes)
        except (ValueError, OSError, TypeError) as exc:
            self.diagnostics.append(f"{path}: {exc}")


def discover_panels(
    project_dir: Path | None = None, *, registered_types: Collection[str] | None = None
) -> PanelRegistry:
    """Discover directory and package entry-point panels with contained failures."""
    if registered_types is None:
        from scistudio.core.types.registry import TypeRegistry

        types = TypeRegistry()
        register_type_scan_dirs(types, project_dir)
        types.scan_all()
        registered_types = types.all_types().keys()
    registry = PanelRegistry()
    roots = panel_scan_dirs(project_dir)
    tiers = [(roots[-1], OwnerKind.USER), (Path(__file__).parent / "builtin", OwnerKind.CORE)]
    if project_dir is not None:
        tiers.insert(0, (roots[0], OwnerKind.PROJECT))
    for root, owner in tiers:
        if root.is_dir():
            for child in sorted(root.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    registry.load(child, owner, registered_types)
    diagnostics: list[EntryPointDiagnostic] = []
    with prepared_plugin_import_roots():
        for ep in enumerate_group("scistudio.panels", diagnostics=diagnostics):
            factory = load_entry_point(ep, "scistudio.panels", diagnostics=diagnostics)
            if not callable(factory):
                continue
            try:
                paths = factory()
                if not isinstance(paths, (tuple, list)) or any(not isinstance(p, (str, Path)) for p in paths):
                    raise ValueError("scistudio.panels must return a list of panel directory paths")
                for path in paths:
                    registry.load(Path(path), OwnerKind.PACKAGE, registered_types, ep.name)
            except Exception as exc:
                registry.diagnostics.append(f"scistudio.panels entry point {ep.name!r}: {exc}")
    registry.diagnostics.extend(str(d) for d in diagnostics)
    return registry


def panel_sources_fingerprint(project_dir: Path | None = None) -> PanelSourcesFingerprint:
    """Summarize the directory tiers :func:`discover_panels` scans, cheaply.

    Two scans of unchanged directories give equal fingerprints, so a holder of a
    discovered registry can tell it has gone stale without discovering again
    (#2421). The summary covers what decides the catalog: which panel directories
    exist, the size and modification time of each ``panel.json`` and
    ``panel.py``, and the names of the page files (the asset suffixes the panel
    routes serve). Page file content is left out on purpose. Editing an open
    MiniApp's page is the common case, the open tab reloads through its own
    watch, and rebuilding the preview service on every save would drop the
    preview sessions other tabs hold. An edit that changes only a page file's
    content, such as adding a disallowed external reference, is picked up at
    the next registry rebuild; ``validate_panel`` reports it at once.

    Only stats and directory listings, no file reads.
    """
    from scistudio.panels.files import ASSET_SUFFIXES

    entries: list[tuple[object, ...]] = []
    for root in panel_scan_dirs(project_dir):
        entries.append(("root", str(root), root.is_dir()))
        if not root.is_dir():
            continue
        try:
            children = sorted(root.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir() or child.name.startswith("."):
                continue
            entries.append(("panel", str(child)))
            for dirpath, dirnames, filenames in os.walk(child):
                dirnames[:] = sorted(
                    name for name in dirnames if name not in SKIPPED_PANEL_PARTS and not name.startswith(".")
                )
                for name in sorted(filenames):
                    if name.startswith("."):
                        continue
                    path = Path(dirpath) / name
                    if name in PANEL_DESCRIPTOR_FILES:
                        try:
                            stat = path.stat()
                        except OSError:
                            continue
                        entries.append(("descriptor", str(path), stat.st_mtime_ns, stat.st_size))
                    elif path.suffix.lower() in ASSET_SUFFIXES:
                        entries.append(("page", str(path)))
    return tuple(entries)
