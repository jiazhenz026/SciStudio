"""Four-tier discovery and a single namespace shared with legacy previewers."""

from __future__ import annotations

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
from scistudio.stability import internal, provisional

TIER_ORDER = {OwnerKind.PROJECT: 0, OwnerKind.USER: 1, OwnerKind.PACKAGE: 2, OwnerKind.CORE: 3}


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
