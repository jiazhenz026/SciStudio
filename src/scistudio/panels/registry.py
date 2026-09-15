"""Four-tier discovery and a single namespace shared with legacy previewers."""

from __future__ import annotations

import os
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
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
from scistudio.stability import internal, provisional

TIER_ORDER = {OwnerKind.PROJECT: 0, OwnerKind.USER: 1, OwnerKind.PACKAGE: 2, OwnerKind.CORE: 3}

#: Files whose content decides whether a directory is a panel and what it declares.
PANEL_DESCRIPTOR_FILES = ("panel.json", "panel.py")
#: Directory names inside a panel directory that never hold the page.
SKIPPED_PANEL_PARTS = frozenset({"__pycache__", "node_modules"})
#: Files the host or the MiniApp itself writes into a panel directory as data.
#: They are neither page nor descriptor, so they never change a fingerprint
#: (MiniApp FR-051: the questionnaire answers file).
IGNORED_PANEL_FILES = frozenset({"answers.json"})


def is_ignored_panel_file(name: str) -> bool:
    """Whether a file in a panel directory is data the catalog never looks at."""
    return name.startswith(".") or name in IGNORED_PANEL_FILES or name.startswith(".answers-")


PanelSourcesFingerprint = tuple[tuple[object, ...], ...]


@provisional(since="0.3.5")
class PanelRegistry:
    """The panels one discovery pass found, keyed by panel id.

    ``panels`` maps each id to the winning :class:`PanelDescriptor`; when two
    tiers ship the same id, the project wins over the user library, the user
    library over a package, and a package over core. ``shadowed`` lists the
    descriptors that lost, and ``diagnostics`` holds one message per refused
    folder, shadowed panel, or failed entry point. A registry holds descriptors
    only: what a panel may do is decided by the context it opens in, never by
    its descriptor.
    """

    def __init__(self) -> None:
        self.panels: dict[str, PanelDescriptor] = {}
        self.shadowed: list[PanelDescriptor] = []
        self.diagnostics: list[str] = []

    @internal()
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
        """Return the winning descriptor for ``panel_id``, or ``None``."""
        return self.panels.get(panel_id)

    @internal()
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


@provisional(since="0.3.5")
def discover_panels(
    project_dir: Path | None = None, *, registered_types: Collection[str] | None = None
) -> PanelRegistry:
    """Discover every panel the application would see and return the registry.

    Scans the project's panel folder when ``project_dir`` is given, the user
    library, every package's ``scistudio.panels`` entry point, and the built-in
    panels. A package entry point is a callable returning a list of panel folder
    paths. ``registered_types`` defaults to the types registered for the project.
    A failure in one folder or entry point becomes a diagnostic on the returned
    :class:`PanelRegistry` and never stops discovery.
    """
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
    discovered registry can tell it has gone stale without discovering again.
    The summary covers what decides the catalog: which panel directories
    exist, the size and modification time of each ``panel.json`` and
    ``panel.py``, and the names of the page files (the asset suffixes the panel
    routes serve). Page file content is left out on purpose. Editing an open
    MiniApp's page is the common case, the open tab reloads through its own
    watch, and rebuilding the preview service on every save would drop the
    preview sessions other tabs hold. An edit that changes only a page file's
    content, such as adding a disallowed external reference, is picked up at
    the next registry rebuild; ``validate_panel`` reports it at once. Files the
    host writes as data (``answers.json``) are left out as well.

    Only stats and directory listings, no file reads.
    """
    # Development references: #2421.
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
                    if is_ignored_panel_file(name):
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


def panel_fingerprint(panel: PanelDescriptor) -> tuple[object, ...]:
    """What a context depends on in a panel's descriptor.

    Two descriptors with equal fingerprints open the same way: the same tier,
    folder, contexts, claims, priority, entry, name and ``panel.py`` presence.
    Page file content is not part of it; a page edit reloads in place.
    """
    return (
        panel.owner_kind.value,
        panel.owner_name,
        str(panel.root),
        panel.api_version,
        tuple(panel.contexts),
        tuple(panel.types),
        panel.priority,
        panel.entry,
        panel.name,
        panel.description,
        panel.version,
        panel.has_python,
    )


@internal()
@dataclass(frozen=True)
class RegistryDiff:
    """What changed between two panel catalogs, and who has to hear about it."""

    added: frozenset[str] = frozenset()
    removed: frozenset[str] = frozenset()
    changed: frozenset[str] = frozenset()
    #: Type claims (``panel.json`` spelling) whose routing candidates changed.
    preview_types: frozenset[str] = frozenset()
    miniapps_changed: bool = False
    catalog_changed: bool = False
    legacy_reloaded: bool = False

    @property
    def invalidated(self) -> frozenset[str]:
        """Panel ids whose open contexts no longer match the catalog."""
        return self.removed | self.changed

    @property
    def preview_candidates_changed(self) -> bool:
        return bool(self.preview_types) or self.legacy_reloaded

    @property
    def empty(self) -> bool:
        return not (
            self.added
            or self.removed
            or self.changed
            or self.preview_types
            or self.miniapps_changed
            or self.catalog_changed
            or self.legacy_reloaded
        )

    def to_event_data(self) -> dict[str, object]:
        return {
            "added": [],
            "removed": [],
            "reloaded": [],
            "registry": "panels",
            "panels": {
                "added": sorted(self.added),
                "removed": sorted(self.removed),
                "changed": sorted(self.changed),
            },
            "miniapps_changed": self.miniapps_changed,
            "preview_candidates_changed": self.preview_candidates_changed,
            "preview_types": sorted(self.preview_types),
            "legacy_reloaded": self.legacy_reloaded,
        }


def diff_panels(
    old: Mapping[str, PanelDescriptor],
    new: Mapping[str, PanelDescriptor],
    *,
    old_candidates: Iterable[tuple[object, ...]] = (),
    new_candidates: Iterable[tuple[object, ...]] = (),
    catalog_changed: bool = False,
    legacy_reloaded: bool = False,
) -> RegistryDiff:
    """Compare two catalogs of winning panels by fingerprint.

    ``old_candidates`` / ``new_candidates`` are routing candidate keys
    ``(claim, id, tier, priority)``; the claims of every key present on one side
    only are the preview types whose open previews must re-route.
    """
    added = frozenset(new.keys() - old.keys())
    removed = frozenset(old.keys() - new.keys())
    changed = frozenset(
        panel_id
        for panel_id in old.keys() & new.keys()
        if panel_fingerprint(old[panel_id]) != panel_fingerprint(new[panel_id])
    )
    before, after = set(old_candidates), set(new_candidates)
    preview_types = frozenset(str(key[0]) for key in before ^ after)
    touched = added | removed | changed
    miniapps_changed = any(
        "miniapp" in panel.contexts
        for panel_id in touched
        for panel in (old.get(panel_id), new.get(panel_id))
        if panel is not None
    )
    return RegistryDiff(
        added=added,
        removed=removed,
        changed=changed,
        preview_types=preview_types,
        miniapps_changed=miniapps_changed,
        catalog_changed=catalog_changed,
        legacy_reloaded=legacy_reloaded,
    )
