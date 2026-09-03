"""Four-tier discovery of on-disk panels (FR-018, FR-019, FR-045 to FR-047).

A panel is registered by *existing as a directory* in a tier. No tier
constructs a Python object to register one, which is what lets a person — and
the agent working on their behalf — register a panel by writing files:

* **core** — the directory the application ships,
  ``src/scistudio/panels/builtin/`` (D-015). It is read off disk like every
  other tier rather than compiled in, which is the precondition for copying a
  built-in panel into a project (A-003, FR-037).
* **package** — every directory the ``scistudio.panels`` entry-point group
  resolves to (FR-045). The group is metadata-only: the entry point's value
  names a package directory and is resolved from the declaring distribution's
  own metadata, so registering a panel needs no importable Python at all.
* **user library** and **project** — the ``panels/`` directory under the user
  library root and under the open project (FR-046). A directory added, changed
  or removed takes effect on the next registry rebuild, which is the one
  trigger (FR-023).

**Shadowing is between tiers; a collision inside one is an error.** A panel in a
lower tier shadows a same-id panel in a higher one, in the order project, user
library, package, core (FR-019) — the mechanism the editing story rests on,
because a copy that keeps its id is what makes the copy take effect (FR-027).
Two declarations of one id inside a *single* tier is a discovery error instead,
reported through :meth:`scistudio.panels.registry.PanelRegistry.record_diagnostic`
— the same surface that reports a refused drop-in today — because nothing inside
the tier decides which of the two wins.

**Every refusal is a diagnostic, never an exception.** One broken declaration,
one unreadable directory, or one provider with a typo in its import path must
not cost the rest of the tier, so :func:`discover_panels` returns what it found
together with what it refused. That includes FR-047's provider rule: a provider
that fails to import is a diagnostic naming the panel, recorded while the person
is looking at the list of panels, rather than a load failure the next time
somebody opens a file.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scistudio.core.entry_points import (
    PANELS_ENTRY_POINT_GROUP,
    DiagnosticSink,
    EntryPointDiagnostic,
    distribution_name,
    entry_point_name,
    enumerate_group,
    prepared_plugin_import_roots,
    resolve_entry_point_directory,
)
from scistudio.core.panels import (
    PANEL_DECLARATION_FILENAME,
    PANEL_TIER_ORDER,
    PanelDeclarationError,
    PanelManifest,
    PanelTier,
    read_panel_declaration,
)
from scistudio.panels.providers import resolve_declared_provider
from scistudio.stability import internal

logger = logging.getLogger(__name__)

__all__ = [
    "BUILTIN_PANELS_ROOT",
    "DiscoveredPanel",
    "PanelDiscovery",
    "builtin_panels_root",
    "discover_panels",
    "discover_tier",
    "iter_panel_directories",
    "package_panel_roots",
]


def builtin_panels_root() -> Path:
    """Return the core tier root, ``src/scistudio/panels/builtin/`` (D-015).

    A directory on disk, resolved from this module's own location, rather than a
    compiled-in list: FR-021 serves all four tiers through one asset route with
    one confinement check differing only in the root, and a core tier that was
    not a directory could not take part in that.
    """
    return Path(__file__).resolve().parent / "builtin"


#: The core tier root. Resolved once at import; tests pass their own root to
#: :func:`discover_panels` rather than writing into this one.
BUILTIN_PANELS_ROOT = builtin_panels_root()


@internal()
@dataclass(frozen=True)
class DiscoveredPanel:
    """One panel found on disk, with where it was found and what it resolved to."""

    manifest: PanelManifest
    """The validated declaration (FR-003)."""
    tier: PanelTier
    """The tier the directory was found in; sets shadowing (FR-019) and the
    write target when the panel is edited (FR-025)."""
    directory: Path
    """The panel directory itself, holding ``panel.json`` and the entry document."""
    root: Path
    """The tier root *directory* sits under. The asset route resolves a panel id
    to this root and joins the requested file under it (FR-021)."""
    owner_name: str = ""
    """The distribution that declared a package panel, or ``""``."""
    provider: Any = None
    """The resolved Python provider, or ``None`` when the panel declares none
    and its windowed reads come from the shared data-access layer (FR-047)."""

    @property
    def panel_id(self) -> str:
        return self.manifest.panel_id

    @property
    def entry_path(self) -> Path:
        """The entry document's path on disk."""
        return self.directory / self.manifest.entry


@internal()
@dataclass
class PanelDiscovery:
    """What one discovery pass found, shadowed, and refused."""

    panels: dict[str, DiscoveredPanel] = field(default_factory=dict)
    """The resolved panel per id, after FR-019 shadowing."""
    shadowed: list[DiscoveredPanel] = field(default_factory=list)
    """Panels a lower tier shadowed. Kept rather than dropped so the discovery
    surface can show which tier each panel resolved from, which is where the
    answer belongs when a person's copy keeps winning after an update."""
    diagnostics: list[str] = field(default_factory=list)
    """Every refusal, in discovery order."""

    def get(self, panel_id: str) -> DiscoveredPanel | None:
        return self.panels.get(panel_id)

    def all_panels(self) -> list[DiscoveredPanel]:
        return list(self.panels.values())

    def panels_for_tier(self, tier: PanelTier) -> list[DiscoveredPanel]:
        return [panel for panel in self.panels.values() if panel.tier is tier]


def iter_panel_directories(root: Path) -> Iterator[Path]:
    """Yield the immediate child directories of *root* holding a declaration.

    One level, deliberately. A panel is a directory containing ``panel.json``
    and its entry document (FR-002), and a recursive search would make a panel's
    own asset subdirectory a candidate panel the moment somebody put a
    ``panel.json`` example in it.

    A root that does not exist or cannot be listed yields nothing; the caller
    records the reason.
    """
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and (entry / PANEL_DECLARATION_FILENAME).is_file():
            yield entry


def discover_tier(
    tier: PanelTier,
    roots: Iterable[Path],
    *,
    owner_name: str = "",
    resolve_providers: bool = True,
) -> tuple[list[DiscoveredPanel], list[str]]:
    """Read every panel directory under *roots* as one tier.

    Returns the panels found and the diagnostics for what was refused. A second
    declaration of an id already claimed **within this tier** is refused with a
    diagnostic naming both directories (the Edge Cases entry: shadowing is
    between tiers, a collision inside one is an error).
    """
    found: dict[str, DiscoveredPanel] = {}
    ordered: list[DiscoveredPanel] = []
    diagnostics: list[str] = []

    for root in roots:
        if not root.is_dir():
            continue
        try:
            directories = list(iter_panel_directories(root))
        except OSError as exc:
            diagnostics.append(f"{tier.value} panel root {root} could not be listed ({exc})")
            continue

        for directory in directories:
            try:
                manifest = read_panel_declaration(directory)
            except PanelDeclarationError as exc:
                logger.warning("Refusing panel at %s: %s", directory, exc.message)
                diagnostics.append(exc.message)
                continue

            existing = found.get(manifest.panel_id)
            if existing is not None:
                diagnostics.append(
                    f"duplicate panel id {manifest.panel_id!r} in the {tier.value} tier: "
                    f"{directory} collides with {existing.directory}; keeping the first"
                )
                continue

            provider: Any = None
            if manifest.provider is not None and resolve_providers:
                owning_root = root if tier in (PanelTier.USER, PanelTier.PROJECT) else None
                resolution = resolve_declared_provider(
                    manifest.provider,
                    panel_id=manifest.panel_id,
                    owning_root=owning_root,
                )
                if resolution.error is not None:
                    # FR-047: a provider that fails to import is a discovery
                    # diagnostic naming the panel. The panel is still
                    # discovered and listed — a person whose provider is broken
                    # still needs to see the panel they have to fix.
                    diagnostics.append(resolution.error)
                provider = resolution.provider

            panel = DiscoveredPanel(
                manifest=manifest,
                tier=tier,
                directory=directory,
                root=root,
                owner_name=owner_name,
                provider=provider,
            )
            found[manifest.panel_id] = panel
            ordered.append(panel)

    return ordered, diagnostics


def package_panel_roots(
    *,
    diagnostics: DiagnosticSink | None = None,
) -> list[tuple[Path, str]]:
    """Return every ``(directory, distribution name)`` the panel group declares.

    FR-045: the entry point resolves to one or more panel directories inside the
    package, and a package must not need to construct a Python object to
    register a panel. The group is therefore read the way
    ``scistudio.tutorials`` is — through
    :func:`scistudio.core.entry_points.resolve_entry_point_directory`, from the
    declaring distribution's metadata, without importing the package.

    The value may name either a directory of panel directories or a single panel
    directory; both are returned as roots and
    :func:`iter_panel_directories` picks the panels out, so a package shipping
    one panel need not invent a wrapper directory for it.
    """
    roots: list[tuple[Path, str]] = []
    sink: DiagnosticSink = [] if diagnostics is None else diagnostics
    with prepared_plugin_import_roots():
        entry_points = enumerate_group(PANELS_ENTRY_POINT_GROUP, diagnostics=sink)
        for entry_point in entry_points:
            directory = resolve_entry_point_directory(entry_point, diagnostics=sink)
            if directory is None:
                continue
            owner = distribution_name(getattr(entry_point, "dist", None), default=entry_point_name(entry_point))
            roots.append((directory, owner))
    return roots


def discover_panels(
    *,
    core_root: Path | None = None,
    package_roots: Sequence[tuple[Path, str]] | None = None,
    user_roots: Sequence[Path] = (),
    project_roots: Sequence[Path] = (),
    resolve_providers: bool = True,
) -> PanelDiscovery:
    """Discover panels across the four tiers and apply FR-019 shadowing.

    Args:
        core_root: The core tier root; :data:`BUILTIN_PANELS_ROOT` when omitted.
            Tests pass a fixture directory of their own rather than writing into
            the shipped one.
        package_roots: ``(directory, distribution name)`` pairs, as
            :func:`package_panel_roots` returns them. ``None`` reads the
            entry-point group; an empty sequence deliberately reads nothing,
            which is what a test asking about the other three tiers wants.
        user_roots: The user library's panel roots.
        project_roots: The open project's panel roots.
        resolve_providers: Whether to resolve declared Python providers. Off in
            a listing that must not execute package code.

    Returns:
        A :class:`PanelDiscovery` whose ``panels`` maps each id to the panel
        that won, whose ``shadowed`` records the ones it beat, and whose
        ``diagnostics`` carries every refusal.
    """
    if core_root is None:
        core_root = BUILTIN_PANELS_ROOT
    entry_point_diagnostics: list[EntryPointDiagnostic] = []
    if package_roots is None:
        package_roots = package_panel_roots(diagnostics=entry_point_diagnostics)

    discovery = PanelDiscovery()
    discovery.diagnostics.extend(str(diagnostic) for diagnostic in entry_point_diagnostics)

    by_tier: dict[PanelTier, list[DiscoveredPanel]] = {}

    core_panels, core_diagnostics = discover_tier(
        PanelTier.CORE, (core_root,), owner_name="scistudio", resolve_providers=resolve_providers
    )
    by_tier[PanelTier.CORE] = core_panels
    discovery.diagnostics.extend(core_diagnostics)

    package_panels: list[DiscoveredPanel] = []
    for directory, owner in package_roots:
        panels, package_diagnostics = discover_tier(
            PanelTier.PACKAGE, (directory,), owner_name=owner, resolve_providers=resolve_providers
        )
        # One package's ids collide with another's the same way two directories
        # in one root do: the package tier is one tier, so the second is refused
        # rather than silently shadowing.
        for panel in panels:
            if any(existing.panel_id == panel.panel_id for existing in package_panels):
                discovery.diagnostics.append(
                    f"duplicate panel id {panel.panel_id!r} in the package tier: "
                    f"{panel.directory} collides with an already-registered package panel; keeping the first"
                )
                continue
            package_panels.append(panel)
        discovery.diagnostics.extend(package_diagnostics)
    by_tier[PanelTier.PACKAGE] = package_panels

    user_panels, user_diagnostics = discover_tier(PanelTier.USER, user_roots, resolve_providers=resolve_providers)
    by_tier[PanelTier.USER] = user_panels
    discovery.diagnostics.extend(user_diagnostics)

    project_panels, project_diagnostics = discover_tier(
        PanelTier.PROJECT, project_roots, resolve_providers=resolve_providers
    )
    by_tier[PanelTier.PROJECT] = project_panels
    discovery.diagnostics.extend(project_diagnostics)

    # FR-019: walk the tiers most-shadowing first, so the first claim on an id
    # wins and everything behind it is recorded as shadowed.
    for tier in PANEL_TIER_ORDER:
        for panel in by_tier.get(tier, ()):
            winner = discovery.panels.get(panel.panel_id)
            if winner is None:
                discovery.panels[panel.panel_id] = panel
            else:
                discovery.shadowed.append(panel)
    return discovery
