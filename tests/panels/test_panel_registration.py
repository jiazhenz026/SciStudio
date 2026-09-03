"""Registration is a directory, not a Python object (T-015).

ADR-054 spec 1, FR-045 to FR-047 and SC-014. Three claims:

* a package registers a panel through the ``scistudio.panels`` entry-point
  group, whose value resolves to a directory and never to a constructed object;
* the user library and the open project register one by *containing* a
  directory, and a directory added or removed takes effect on the next rebuild;
* a declaration may name a Python provider, resolved from the tier the panel was
  discovered in, and one that fails to import is a discovery diagnostic naming
  the panel rather than a load failure at mount.

The entry-point half is asserted with an import tripwire rather than by reading
the source: ``EntryPoint.load``, ``importlib.import_module`` and
``importlib.util.find_spec`` all consult ``sys.meta_path``, so any of the three
creeping in trips it.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from importlib.abc import MetaPathFinder
from pathlib import Path
from typing import Any

import pytest

from scistudio.core.entry_points import (
    LIVE_ENTRY_POINT_GROUPS,
    METADATA_ONLY_GROUPS,
    PANELS_ENTRY_POINT_GROUP,
    PREVIEWERS_ENTRY_POINT_GROUP,
)
from scistudio.core.panels import PanelCapability, PanelTier
from scistudio.panels.discovery import (
    discover_panels,
    discover_tier,
    package_panel_roots,
    register_discovered_panels,
)
from scistudio.panels.models import PanelSpec
from scistudio.panels.project import (
    LEGACY_PROJECT_PANELS_MANIFEST,
    PROJECT_PANELS_MANIFEST,
    load_project_panels,
)
from scistudio.panels.providers import resolve_declared_provider
from scistudio.panels.registry import PanelRegistry
from tests.panels.conftest import write_panel

FIXTURE_PACKAGE_PANELS = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "scistudio-blocks-fixture"
    / "src"
    / "scistudio_blocks_fixture"
    / "panels"
)


# ---------------------------------------------------------------------------
# Entry-point stand-ins
# ---------------------------------------------------------------------------


@dataclass
class _EntryPointStub:
    name: str
    value: str
    group: str
    dist: Any = None
    loads: list[str] = field(default_factory=list)

    @property
    def module(self) -> str:
        return self.value.split(":", 1)[0]

    def load(self) -> Any:  # pragma: no cover - a call here is the failure
        self.loads.append(self.value)
        raise AssertionError("the panel group must not import the package to register a panel")


@dataclass
class _FakeDistribution:
    root: Path
    dist_name: str

    @property
    def name(self) -> str:
        return self.dist_name

    def locate_file(self, path: Any) -> Path:
        return self.root / str(path)

    @property
    def files(self) -> tuple[Any, ...]:
        return ()


class _ImportTripwire(MetaPathFinder):
    """Records every attempt to import a name under *prefix*."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.attempts: list[str] = []

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> None:
        if fullname == self.prefix or fullname.startswith(f"{self.prefix}."):
            self.attempts.append(fullname)
        return None


@pytest.fixture
def import_tripwire() -> Iterator[Any]:
    installed: list[_ImportTripwire] = []

    def make(prefix: str) -> _ImportTripwire:
        tripwire = _ImportTripwire(prefix)
        sys.meta_path.insert(0, tripwire)
        installed.append(tripwire)
        return tripwire

    yield make
    for tripwire in installed:
        if tripwire in sys.meta_path:
            sys.meta_path.remove(tripwire)


def _install_entry_points(monkeypatch: pytest.MonkeyPatch, entry_points: list[_EntryPointStub]) -> None:
    import importlib.metadata

    def fake(*, group: str | None = None, **_: Any) -> tuple[_EntryPointStub, ...]:
        return tuple(ep for ep in entry_points if group is None or ep.group == group)

    monkeypatch.setattr(importlib.metadata, "entry_points", fake)


# ---------------------------------------------------------------------------
# FR-045 — the entry-point group
# ---------------------------------------------------------------------------


def test_the_panel_group_is_live_and_metadata_only() -> None:
    """FR-045: the payload is a directory, so the group is exempt from the
    callable contract for the same structural reason the tutorial group is."""
    assert PANELS_ENTRY_POINT_GROUP == "scistudio.panels"
    assert PANELS_ENTRY_POINT_GROUP in LIVE_ENTRY_POINT_GROUPS
    assert PANELS_ENTRY_POINT_GROUP in METADATA_ONLY_GROUPS


def test_the_previewer_group_stays_live_for_the_migration() -> None:
    """FR-045/FR-020: the retired group keeps being discovered."""
    assert PREVIEWERS_ENTRY_POINT_GROUP in LIVE_ENTRY_POINT_GROUPS


def test_a_package_registers_a_panel_with_a_directory_and_no_python_object(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    import_tripwire: Any,
) -> None:
    """SC-014, first half."""
    module = "scistudio_panel_probe_pkg.panels"
    root = tmp_path / Path(*module.split("."))
    root.mkdir(parents=True)
    write_panel(root, "probe.table", capability="producing")
    tripwire = import_tripwire("scistudio_panel_probe_pkg")
    entry_point = _EntryPointStub(
        name="probe",
        value=module,
        group=PANELS_ENTRY_POINT_GROUP,
        dist=_FakeDistribution(root=tmp_path, dist_name="scistudio-panel-probe"),
    )
    _install_entry_points(monkeypatch, [entry_point])

    roots = package_panel_roots()

    assert roots == [(root, "scistudio-panel-probe")]
    assert entry_point.loads == [], "registration must not call EntryPoint.load()"
    assert tripwire.attempts == []
    assert "scistudio_panel_probe_pkg" not in sys.modules

    discovery = discover_panels(core_root=tmp_path / "absent", package_roots=roots)
    assert discovery.get("probe.table").tier is PanelTier.PACKAGE
    assert discovery.get("probe.table").owner_name == "scistudio-panel-probe"


def test_an_unresolvable_entry_point_is_a_diagnostic_not_a_failed_scan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    entry_point = _EntryPointStub(name="broken", value="nowhere.panels", group=PANELS_ENTRY_POINT_GROUP, dist=None)
    _install_entry_points(monkeypatch, [entry_point])

    diagnostics: list[Any] = []
    assert package_panel_roots(diagnostics=diagnostics) == []
    assert [d.entry_point for d in diagnostics] == ["broken"]


def test_the_in_repo_fixture_package_ships_a_panel_directory() -> None:
    """SC-014: the fixture is the evidence, so it has to actually be there."""
    assert FIXTURE_PACKAGE_PANELS.is_dir()
    panels, diagnostics = discover_tier(PanelTier.PACKAGE, (FIXTURE_PACKAGE_PANELS,), owner_name="fixture")
    assert diagnostics == []
    assert [panel.panel_id for panel in panels] == ["fixture.image.viewer"]
    assert panels[0].manifest.target_types == ("FixtureImage",)


# ---------------------------------------------------------------------------
# FR-046 — the user library and the project register by containing a directory
# ---------------------------------------------------------------------------


def test_a_project_registers_a_panel_by_containing_a_directory(tier_roots: dict[str, Path]) -> None:
    """SC-014, second half."""
    write_panel(tier_roots["project"], "project.table")

    discovery = discover_panels(
        core_root=tier_roots["core"],
        package_roots=[],
        user_roots=(tier_roots["user"],),
        project_roots=(tier_roots["project"],),
    )

    assert discovery.get("project.table").tier is PanelTier.PROJECT


def test_a_directory_added_or_removed_takes_effect_on_the_next_rebuild(tier_roots: dict[str, Path]) -> None:
    """FR-046: a rebuild is the one trigger, so discovery is a pure function of
    what is on disk when it runs — nothing is cached across passes."""

    def rebuild() -> set[str]:
        return set(
            discover_panels(
                core_root=tier_roots["core"],
                package_roots=[],
                user_roots=(tier_roots["user"],),
                project_roots=(tier_roots["project"],),
            ).panels
        )

    assert rebuild() == set()

    directory = write_panel(tier_roots["project"], "project.table")
    assert rebuild() == {"project.table"}

    (directory / "panel.json").unlink()
    assert rebuild() == set()


# ---------------------------------------------------------------------------
# FR-047 — the optional provider
# ---------------------------------------------------------------------------


def test_a_panel_needs_no_provider(tmp_path: Path) -> None:
    """A-010: the shared bounded data-access layer windows every core type."""
    root = tmp_path / "project"
    root.mkdir()
    write_panel(root, "acme.table")

    panels, diagnostics = discover_tier(PanelTier.PROJECT, (root,))

    assert panels[0].manifest.provider is None
    assert panels[0].provider is None
    assert diagnostics == []


def test_a_declared_provider_is_resolved_at_discovery(tmp_path: Path) -> None:
    root = tmp_path / "package"
    root.mkdir()
    write_panel(root, "acme.plot", provider="scistudio.panels.fallbacks:plot_panel")

    panels, diagnostics = discover_tier(PanelTier.PACKAGE, (root,), owner_name="acme")

    assert diagnostics == []
    assert callable(panels[0].provider)


def test_a_provider_that_fails_to_import_is_a_discovery_diagnostic_naming_the_panel(tmp_path: Path) -> None:
    """FR-047: a diagnostic while the person is looking at the list of panels,
    not a load failure the next time somebody opens a file."""
    root = tmp_path / "package"
    root.mkdir()
    write_panel(root, "acme.broken", provider="no_such_module_at_all:render")

    panels, diagnostics = discover_tier(PanelTier.PACKAGE, (root,), owner_name="acme")

    assert len(diagnostics) == 1
    assert "acme.broken" in diagnostics[0]
    assert "no_such_module_at_all:render" in diagnostics[0]
    # The panel is still discovered: a person whose provider is broken still
    # needs to see the panel they have to fix.
    assert [panel.panel_id for panel in panels] == ["acme.broken"]
    assert panels[0].provider is None


def test_a_provider_naming_an_absent_attribute_is_a_diagnostic() -> None:
    resolution = resolve_declared_provider("scistudio.panels.fallbacks:no_such_attribute", panel_id="acme.thing")

    assert resolution.provider is None
    assert "acme.thing" in resolution.error
    assert "no_such_attribute" in resolution.error


def test_a_provider_that_is_not_callable_is_a_diagnostic() -> None:
    resolution = resolve_declared_provider("scistudio.core.panels:PANEL_API_VERSION", panel_id="acme.thing")

    assert resolution.provider is None
    assert "callable" in resolution.error


def test_a_drop_in_provider_resolves_from_the_tier_the_panel_was_found_in(tmp_path: Path) -> None:
    """FR-047: a user-library panel never resolves its provider out of the
    project's directory, and vice versa."""
    project_root = tmp_path / "project"
    user_root = tmp_path / "user"
    project_root.mkdir()
    user_root.mkdir()
    (project_root / "renderer.py").write_text("def render(request):\n    return 'project'\n", encoding="utf-8")
    (user_root / "renderer.py").write_text("def render(request):\n    return 'user'\n", encoding="utf-8")
    write_panel(project_root, "shared.table", provider="renderer:render")
    write_panel(user_root, "other.table", provider="renderer:render")

    project_panels, project_diagnostics = discover_tier(PanelTier.PROJECT, (project_root,))
    user_panels, user_diagnostics = discover_tier(PanelTier.USER, (user_root,))

    assert project_diagnostics == [] and user_diagnostics == []
    assert project_panels[0].provider(None) == "project"
    assert user_panels[0].provider(None) == "user"


def test_a_drop_in_provider_that_raises_on_import_names_the_panel(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "renderer.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    write_panel(root, "acme.exploding", provider="renderer:render")

    _, diagnostics = discover_tier(PanelTier.PROJECT, (root,))

    assert len(diagnostics) == 1
    assert "acme.exploding" in diagnostics[0]
    assert "boom" in diagnostics[0]


def test_provider_resolution_can_be_turned_off_for_a_listing(tmp_path: Path) -> None:
    """A listing that must not execute package code asks for the declarations
    only; the reference stays on the manifest either way."""
    root = tmp_path / "package"
    root.mkdir()
    write_panel(root, "acme.plot", provider="no_such_module_at_all:render")

    panels, diagnostics = discover_tier(PanelTier.PACKAGE, (root,), resolve_providers=False)

    assert diagnostics == []
    assert panels[0].provider is None
    assert panels[0].manifest.provider == "no_such_module_at_all:render"


# ---------------------------------------------------------------------------
# FR-046 / FR-020 — the project's default-panel declaration, carried over
# ---------------------------------------------------------------------------


def _project_with(tmp_path: Path, filename: str, defaults: dict[str, str]) -> Path:
    project = tmp_path / "project"
    (project / ".scistudio").mkdir(parents=True, exist_ok=True)
    (project / filename).write_text(json.dumps({"default_panels": defaults}), encoding="utf-8")
    return project


def test_the_panel_named_declaration_sets_the_project_defaults(tmp_path: Path) -> None:
    """FR-046: carried over under the panel naming, behaviour unchanged."""
    project = _project_with(tmp_path, PROJECT_PANELS_MANIFEST, {"DataFrame": "project.table"})
    registry = PanelRegistry()

    load_project_panels(registry, project)

    assert registry.project_default_for("DataFrame") == "project.table"
    assert registry.diagnostics == []


def test_a_project_that_still_has_the_old_file_keeps_working(tmp_path: Path) -> None:
    """FR-020: a project on disk predates the build that opens it."""
    project = _project_with(tmp_path, LEGACY_PROJECT_PANELS_MANIFEST, {"DataFrame": "legacy.table"})
    registry = PanelRegistry()

    load_project_panels(registry, project)

    assert registry.project_default_for("DataFrame") == "legacy.table"
    assert registry.diagnostics == []


def test_when_both_declarations_exist_the_panel_named_one_is_used_entire(tmp_path: Path) -> None:
    """Not merged. Two files declaring the same defaults produce a state neither
    of them describes, and "which file am I editing" then has no answer. The
    diagnostic says which one won, because a person who copied one to the other
    has to be able to find that out."""
    project = _project_with(
        tmp_path, LEGACY_PROJECT_PANELS_MANIFEST, {"DataFrame": "legacy.table", "Series": "legacy.line"}
    )
    (project / PROJECT_PANELS_MANIFEST).write_text(
        json.dumps({"default_panels": {"DataFrame": "current.table"}}), encoding="utf-8"
    )
    registry = PanelRegistry()

    load_project_panels(registry, project)

    assert registry.project_default_for("DataFrame") == "current.table"
    assert registry.project_default_for("Series") is None, "the ignored file contributes nothing at all"
    assert any(PROJECT_PANELS_MANIFEST in message for message in registry.diagnostics)
    assert any(LEGACY_PROJECT_PANELS_MANIFEST in message for message in registry.diagnostics)


def test_the_older_declaration_is_never_rewritten_or_deleted(tmp_path: Path) -> None:
    """Reverting to an earlier build must find the file exactly as it was."""
    project = _project_with(tmp_path, LEGACY_PROJECT_PANELS_MANIFEST, {"DataFrame": "legacy.table"})
    (project / PROJECT_PANELS_MANIFEST).write_text(json.dumps({"default_panels": {}}), encoding="utf-8")
    before = (project / LEGACY_PROJECT_PANELS_MANIFEST).read_bytes()

    load_project_panels(PanelRegistry(), project)

    assert (project / LEGACY_PROJECT_PANELS_MANIFEST).read_bytes() == before


# ---------------------------------------------------------------------------
# FR-046 — a directory-registered panel reaches the routing ladder
# ---------------------------------------------------------------------------


def test_a_directory_registered_panel_becomes_routable(tmp_path: Path) -> None:
    """Registration is a directory, so nobody writes a PanelSpec for it."""
    root = tmp_path / "project"
    root.mkdir()
    write_panel(root, "acme.frame", target_types=["DataFrame", "Series"], capability="producing", priority=7)
    discovery = discover_panels(core_root=tmp_path / "absent", package_roots=[], project_roots=(root,))
    registry = PanelRegistry()

    register_discovered_panels(registry, discovery)

    spec = registry.get("acme.frame")
    assert spec is not None
    assert spec.owner_kind is PanelTier.PROJECT
    assert spec.target_type_names == ("DataFrame", "Series")
    assert spec.capability is PanelCapability.PRODUCING
    assert spec.priority == 7


def test_a_directory_does_not_add_a_second_entry_for_a_panel_already_registered(tmp_path: Path) -> None:
    """A built-in has both a spec (its Python provider and its place in the
    ladder, FR-033) and a directory (its document). They are one panel joined by
    its id, and an edited copy in a project keeps that id (FR-027), so the
    routing entry never moves — only the document served for it does."""
    root = tmp_path / "project"
    root.mkdir()
    write_panel(root, "core.dataframe.basic", display_name="my table")
    discovery = discover_panels(core_root=tmp_path / "absent", package_roots=[], project_roots=(root,))
    registry = PanelRegistry()
    registry.register(
        PanelSpec(
            previewer_id="core.dataframe.basic",
            owner_kind=PanelTier.CORE,
            owner_name="scistudio",
            target_type="DataFrame",
        )
    )

    register_discovered_panels(registry, discovery)

    assert len(registry.all_specs()) == 1
    assert registry.get("core.dataframe.basic").owner_kind is PanelTier.CORE
    assert discovery.get("core.dataframe.basic").manifest.display_name == "my table"


def test_a_block_addressed_panel_claims_nothing_in_the_type_ladder(tmp_path: Path) -> None:
    """FR-017: it is addressed by the block that opens it, not by a data type,
    so it is discovered and listed but never routed to."""
    root = tmp_path / "project"
    root.mkdir()
    directory = root / "acme.block.panel"
    directory.mkdir()
    (directory / "panel.json").write_text(
        json.dumps(
            {
                "panel_id": "acme.block.panel",
                "display_name": "Block panel",
                "target_types": [],
                "capability": "producing",
                "entry": "index.html",
                "api_version": "1",
            }
        ),
        encoding="utf-8",
    )
    (directory / "index.html").write_text("<title>x</title>", encoding="utf-8")
    discovery = discover_panels(core_root=tmp_path / "absent", package_roots=[], project_roots=(root,))
    registry = PanelRegistry()

    register_discovered_panels(registry, discovery)

    assert discovery.get("acme.block.panel") is not None
    assert registry.all_specs() == []


def test_every_discovery_diagnostic_reaches_the_registry_surface(tmp_path: Path) -> None:
    """The same surface that reports a refused drop-in today."""
    root = tmp_path / "project"
    root.mkdir()
    broken = root / "broken"
    broken.mkdir()
    (broken / "panel.json").write_text(json.dumps({"panel_id": "broken"}), encoding="utf-8")
    discovery = discover_panels(core_root=tmp_path / "absent", package_roots=[], project_roots=(root,))
    registry = PanelRegistry()

    register_discovered_panels(registry, discovery)

    assert registry.diagnostics == discovery.diagnostics
    assert registry.diagnostics
