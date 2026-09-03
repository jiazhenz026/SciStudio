"""Four-tier discovery and the FR-019 shadowing order.

ADR-054 spec 1, T-003. Covers FR-018, FR-019, FR-037, the Edge Cases entry on
same-tier collisions, and the core tier being a directory on disk (D-015).

The core tier is exercised against a fixture root rather than against the
shipped ``src/scistudio/panels/builtin/``. What is under test is the *rule* —
a core panel is read off disk and is shadowable on the same terms as any other
— and a test that asserted against the real built-in set would fail whenever
one of those panels was edited, which is a different thing entirely.
"""

from __future__ import annotations

import json
from pathlib import Path

from scistudio.core.panels import PanelCapability, PanelTier
from scistudio.panels.discovery import (
    BUILTIN_PANELS_ROOT,
    builtin_panels_root,
    discover_panels,
    discover_tier,
    iter_panel_directories,
)
from tests.panels.conftest import write_panel


def _discover(roots: dict[str, Path], **overrides: object) -> object:
    """Discover across the four fixture roots, package tier off unless asked."""
    kwargs: dict[str, object] = {
        "core_root": roots["core"],
        "package_roots": [],
        "user_roots": (roots["user"],),
        "project_roots": (roots["project"],),
    }
    kwargs.update(overrides)
    return discover_panels(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# FR-018 / D-015 — four tiers, and the core one is a directory
# ---------------------------------------------------------------------------


def test_the_core_tier_root_is_a_directory_under_the_panel_subsystem() -> None:
    """D-015/A-003: the built-in documents live on disk, not in the bundle."""
    assert BUILTIN_PANELS_ROOT == builtin_panels_root()
    assert BUILTIN_PANELS_ROOT.name == "builtin"
    assert BUILTIN_PANELS_ROOT.parent.name == "panels"


def test_each_tier_is_discovered_and_records_where_it_came_from(tier_roots: dict[str, Path]) -> None:
    write_panel(tier_roots["core"], "core.table")
    write_panel(tier_roots["user"], "user.table")
    write_panel(tier_roots["project"], "project.table")
    package_root = tier_roots["package"]
    write_panel(package_root, "acme.table")

    discovery = _discover(tier_roots, package_roots=[(package_root, "acme")])

    assert {panel_id: panel.tier for panel_id, panel in discovery.panels.items()} == {
        "core.table": PanelTier.CORE,
        "acme.table": PanelTier.PACKAGE,
        "user.table": PanelTier.USER,
        "project.table": PanelTier.PROJECT,
    }
    assert discovery.diagnostics == []
    assert discovery.get("acme.table").owner_name == "acme"


def test_a_missing_tier_root_is_not_an_error(tmp_path: Path) -> None:
    """The user library exists whether or not anybody has written a panel yet."""
    discovery = discover_panels(
        core_root=tmp_path / "absent-core",
        package_roots=[],
        user_roots=(tmp_path / "absent-user",),
        project_roots=(tmp_path / "absent-project",),
    )

    assert discovery.panels == {}
    assert discovery.diagnostics == []


def test_a_directory_without_a_declaration_is_not_a_panel(tmp_path: Path) -> None:
    """Only a directory holding ``panel.json`` is a candidate; an assets
    directory beside one is not."""
    (tmp_path / "notes").mkdir()
    write_panel(tmp_path, "acme.thing")

    assert [directory.name for directory in iter_panel_directories(tmp_path)] == ["acme.thing"]


def test_the_search_does_not_recurse_into_a_panels_own_assets(tmp_path: Path) -> None:
    panel = write_panel(tmp_path, "acme.thing")
    nested = panel / "examples" / "acme.other"
    nested.mkdir(parents=True)
    (nested / "panel.json").write_text("{}", encoding="utf-8")

    assert [directory.name for directory in iter_panel_directories(tmp_path)] == ["acme.thing"]


# ---------------------------------------------------------------------------
# FR-019 / FR-037 — shadowing between tiers
# ---------------------------------------------------------------------------


def test_a_lower_tier_shadows_a_higher_one_in_the_stated_order(tier_roots: dict[str, Path]) -> None:
    package_root = tier_roots["package"]
    for name, root in (("core", tier_roots["core"]), ("package", package_root), ("user", tier_roots["user"])):
        write_panel(root, "core.table", display_name=f"{name} table")
    write_panel(tier_roots["project"], "core.table", display_name="project table")

    discovery = _discover(tier_roots, package_roots=[(package_root, "acme")])

    winner = discovery.get("core.table")
    assert winner.tier is PanelTier.PROJECT
    assert winner.manifest.display_name == "project table"
    assert sorted(panel.tier.value for panel in discovery.shadowed) == ["core", "package", "user"]


def test_a_builtin_panel_is_shadowable_from_the_user_library(tier_roots: dict[str, Path]) -> None:
    """FR-037: on the same terms as any other panel, which is what makes
    copy-on-write editing work at all."""
    write_panel(tier_roots["core"], "core.dataframe.basic", display_name="built in")
    write_panel(tier_roots["user"], "core.dataframe.basic", display_name="mine")

    discovery = _discover(tier_roots)

    assert discovery.get("core.dataframe.basic").tier is PanelTier.USER
    assert discovery.get("core.dataframe.basic").manifest.display_name == "mine"


def test_a_builtin_panel_is_shadowable_from_the_project(tier_roots: dict[str, Path]) -> None:
    write_panel(tier_roots["core"], "core.dataframe.basic", display_name="built in")
    write_panel(tier_roots["project"], "core.dataframe.basic", display_name="ours")

    discovery = _discover(tier_roots)

    assert discovery.get("core.dataframe.basic").tier is PanelTier.PROJECT


def test_the_shadowed_panel_is_kept_rather_than_dropped(tier_roots: dict[str, Path]) -> None:
    """The discovery surface shows which tier each panel resolved from, which is
    where the answer belongs when a person's copy keeps winning after an
    update (Edge Cases)."""
    write_panel(tier_roots["core"], "core.table")
    write_panel(tier_roots["project"], "core.table")

    discovery = _discover(tier_roots)

    assert [panel.tier for panel in discovery.shadowed] == [PanelTier.CORE]


# ---------------------------------------------------------------------------
# Edge case — a collision inside one tier is an error, not shadowing
# ---------------------------------------------------------------------------


def test_two_declarations_of_one_id_in_a_tier_is_a_discovery_error(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    write_panel(root, "acme.table", directory_name="first")
    write_panel(root, "acme.table", directory_name="second")

    panels, diagnostics = discover_tier(PanelTier.PROJECT, (root,))

    assert [panel.directory.name for panel in panels] == ["first"]
    assert len(diagnostics) == 1
    assert "duplicate panel id 'acme.table'" in diagnostics[0]
    assert "project" in diagnostics[0]
    assert "second" in diagnostics[0]


def test_two_packages_declaring_one_id_collide_within_the_package_tier(tmp_path: Path) -> None:
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    write_panel(first, "shared.table")
    write_panel(second, "shared.table")

    discovery = discover_panels(
        core_root=tmp_path / "absent",
        package_roots=[(first, "one"), (second, "two")],
    )

    assert discovery.get("shared.table").owner_name == "one"
    assert any("duplicate panel id 'shared.table' in the package tier" in d for d in discovery.diagnostics)


# ---------------------------------------------------------------------------
# FR-003 at the discovery surface — a refusal is a diagnostic, not a crash
# ---------------------------------------------------------------------------


def test_one_broken_declaration_does_not_cost_the_rest_of_the_tier(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    broken = root / "broken"
    broken.mkdir()
    (broken / "panel.json").write_text(json.dumps({"panel_id": "broken"}), encoding="utf-8")
    write_panel(root, "acme.good")

    panels, diagnostics = discover_tier(PanelTier.PROJECT, (root,))

    assert [panel.panel_id for panel in panels] == ["acme.good"]
    assert len(diagnostics) == 1
    assert "display_name" in diagnostics[0]
    assert str(broken) in diagnostics[0]


def test_a_declared_target_type_nothing_registers_is_still_discovered(tmp_path: Path) -> None:
    """Edge Cases: it is discovered, listed, and never routed to — which is how
    a package author learns their target type name is wrong."""
    root = tmp_path / "project"
    root.mkdir()
    write_panel(root, "acme.thing", target_types=["NoSuchType"])

    panels, diagnostics = discover_tier(PanelTier.PROJECT, (root,))

    assert [panel.manifest.target_types for panel in panels] == [("NoSuchType",)]
    assert diagnostics == []


def test_a_discovered_panel_knows_its_root_and_entry_document(tmp_path: Path) -> None:
    """The asset route resolves a panel id to its tier root and joins the file
    under it (FR-021), so discovery has to hand both back."""
    root = tmp_path / "project"
    root.mkdir()
    directory = write_panel(root, "acme.thing", capability="producing")

    panels, _ = discover_tier(PanelTier.PROJECT, (root,))

    assert panels[0].root == root
    assert panels[0].directory == directory
    assert panels[0].entry_path == directory / "index.html"
    assert panels[0].manifest.capability is PanelCapability.PRODUCING
