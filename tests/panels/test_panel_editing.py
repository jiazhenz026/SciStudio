"""Reading, writing, copy-on-write, and revert (T-010, FR-024 to FR-029).

The behaviour, tested below the route so the arguments are about where an edit
lands rather than about status codes; ``tests/api/test_panel_source_routes.py``
covers the HTTP surface over it.

Two properties carry the story:

* **The system does not ask where to save** (FR-025). A project or user-library
  panel is written back in place; a core or package panel is copied into the
  open project under the same id and the read-only original is untouched
  (FR-026, FR-027). Keeping the id is the whole mechanism — the FR-019 tier
  ordering is then what makes the copy take effect, with nothing new added.
* **The write path is confined.** This is a filesystem write driven by an HTTP
  request, the surface #2038, #2037 and #2039 were all filed against, so the
  adversarial cases are here rather than left to the happy path: a panel id that
  is a traversal, a declaration that renames the panel out from under the
  shadowing rule, an entry naming a file outside its own directory, an entry of
  a type the asset route would refuse to serve, a symlinked panel directory, and
  a revert on a panel that shadows nothing.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from scistudio.core.panels import PanelTier
from scistudio.panels.discovery import DiscoveredPanel, PanelDiscovery, discover_panels
from scistudio.panels.editing import (
    PanelEditError,
    PanelNotEditableError,
    PanelOverrideNotFoundError,
    confined_panel_directory,
    read_panel_source,
    revert_panel_override,
    save_panel_source,
)
from tests.panels.conftest import write_panel

DOCUMENT = "<!doctype html><title>edited</title><body>edited</body>\n"


@pytest.fixture
def roots(tmp_path: Path) -> dict[str, Path]:
    """Return the four tier roots, empty and created."""
    made = {}
    for name in ("core", "package", "user", "project"):
        root = tmp_path / name
        root.mkdir()
        made[name] = root
    return made


def _discover(roots: dict[str, Path]) -> PanelDiscovery:
    return discover_panels(
        core_root=roots["core"],
        package_roots=[(roots["package"], "acme")],
        user_roots=(roots["user"],),
        project_roots=(roots["project"],),
    )


def _panel(roots: dict[str, Path], panel_id: str) -> DiscoveredPanel:
    panel = _discover(roots).get(panel_id)
    assert panel is not None
    return panel


# ---------------------------------------------------------------------------
# FR-024: read any resolved panel, whichever tier it came from
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tier_name", ["core", "package", "user", "project"])
def test_the_source_of_a_panel_reads_from_every_tier(roots: dict[str, Path], tier_name: str) -> None:
    """FR-024: a core panel reads exactly the way a project panel does."""
    directory = write_panel(roots[tier_name], "probe.read")
    (directory / "index.html").write_text(DOCUMENT, encoding="utf-8")
    discovery = _discover(roots)
    panel = discovery.get("probe.read")
    assert panel is not None

    source = read_panel_source(panel, discovery)
    assert source.source == DOCUMENT
    assert json.loads(source.declaration)["panel_id"] == "probe.read"
    assert source.entry == "index.html"
    assert source.tier is PanelTier(tier_name)
    assert source.editable is (tier_name in {"user", "project"})


def test_reading_reports_the_tier_a_panel_shadows(roots: dict[str, Path]) -> None:
    """What tells a caller whether a revert has anything to restore (FR-029)."""
    write_panel(roots["core"], "probe.shadow")
    write_panel(roots["project"], "probe.shadow")
    discovery = _discover(roots)
    panel = discovery.get("probe.shadow")
    assert panel is not None
    assert read_panel_source(panel, discovery).shadows is PanelTier.CORE

    write_panel(roots["user"], "probe.alone")
    discovery = _discover(roots)
    alone = discovery.get("probe.alone")
    assert alone is not None
    assert read_panel_source(alone, discovery).shadows is None


# ---------------------------------------------------------------------------
# FR-025: the save target is the tier the panel resolved from
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tier_name", ["user", "project"])
def test_an_editable_panel_is_written_back_in_place(roots: dict[str, Path], tier_name: str) -> None:
    """FR-025 with Story 2 scenario 3: no second copy is made."""
    directory = write_panel(roots[tier_name], "probe.inplace")
    panel = _panel(roots, "probe.inplace")

    saved = save_panel_source(panel, DOCUMENT, project_panels_root=roots["project"])

    assert saved.copied is False
    assert saved.tier is PanelTier(tier_name)
    assert saved.directory == directory.resolve()
    assert (directory / "index.html").read_text(encoding="utf-8") == DOCUMENT
    # No second copy: the other roots are untouched.
    others = [name for name in ("core", "package", "user", "project") if name != tier_name]
    assert all(not (roots[name] / "probe.inplace").exists() for name in others)


@pytest.mark.parametrize("tier_name", ["core", "package"])
def test_editing_a_read_only_panel_copies_it_into_the_project(roots: dict[str, Path], tier_name: str) -> None:
    """FR-026 and FR-027: the copy keeps the id, and the original is not written."""
    original = write_panel(roots[tier_name], "probe.readonly")
    (original / "assets").mkdir()
    (original / "assets" / "style.css").write_text("body{}", encoding="utf-8")
    before = (original / "index.html").read_text(encoding="utf-8")

    panel = _panel(roots, "probe.readonly")
    saved = save_panel_source(panel, DOCUMENT, project_panels_root=roots["project"])

    assert saved.copied is True
    assert saved.tier is PanelTier.PROJECT
    copy = roots["project"] / "probe.readonly"
    assert (copy / "index.html").read_text(encoding="utf-8") == DOCUMENT
    # FR-027: the id is kept, which is what makes the ordering do the work.
    assert json.loads((copy / "panel.json").read_text(encoding="utf-8"))["panel_id"] == "probe.readonly"
    # The whole directory came across, not just the entry document.
    assert (copy / "assets" / "style.css").read_text(encoding="utf-8") == "body{}"
    # FR-026: the read-only original is not written.
    assert (original / "index.html").read_text(encoding="utf-8") == before


def test_the_copy_then_shadows_the_original(roots: dict[str, Path]) -> None:
    """FR-019 is the mechanism; the copy needs no new one (Story 2 scenario 4)."""
    write_panel(roots["core"], "probe.shadowed")
    panel = _panel(roots, "probe.shadowed")
    save_panel_source(panel, DOCUMENT, project_panels_root=roots["project"])

    discovery = _discover(roots)
    resolved = discovery.get("probe.shadowed")
    assert resolved is not None
    assert resolved.tier is PanelTier.PROJECT
    assert [entry.tier for entry in discovery.shadowed if entry.panel_id == "probe.shadowed"] == [PanelTier.CORE]


def test_a_second_save_to_a_copied_panel_writes_in_place(roots: dict[str, Path]) -> None:
    """Once copied, the panel resolves from the project and is edited there."""
    write_panel(roots["core"], "probe.again")
    save_panel_source(_panel(roots, "probe.again"), DOCUMENT, project_panels_root=roots["project"])

    second = save_panel_source(
        _panel(roots, "probe.again"), "<!doctype html>second\n", project_panels_root=roots["project"]
    )
    assert second.copied is False
    assert (roots["project"] / "probe.again" / "index.html").read_text(encoding="utf-8") == "<!doctype html>second\n"


def test_editing_a_read_only_panel_with_no_project_open_is_refused(roots: dict[str, Path]) -> None:
    """FR-026 names the open project as the destination and gives no second answer.

    Depositing the edit somewhere the person did not ask for would be worse than
    telling them there is nowhere to put it.
    """
    write_panel(roots["core"], "probe.noproject")
    with pytest.raises(PanelNotEditableError, match="no project is open"):
        save_panel_source(_panel(roots, "probe.noproject"), DOCUMENT, project_panels_root=None)


# ---------------------------------------------------------------------------
# FR-029: revert deletes the shadowing copy
# ---------------------------------------------------------------------------


def test_revert_deletes_the_copy_and_restores_what_it_shadowed(roots: dict[str, Path]) -> None:
    write_panel(roots["core"], "probe.revert")
    save_panel_source(_panel(roots, "probe.revert"), DOCUMENT, project_panels_root=roots["project"])
    copy = roots["project"] / "probe.revert"
    assert copy.is_dir()

    discovery = _discover(roots)
    panel = discovery.get("probe.revert")
    assert panel is not None
    reverted = revert_panel_override(panel, discovery)

    assert reverted.removed_tier is PanelTier.PROJECT
    assert reverted.restored_tier is PanelTier.CORE
    assert not copy.exists()
    restored = _discover(roots).get("probe.revert")
    assert restored is not None
    assert restored.tier is PanelTier.CORE


def test_revert_refuses_a_panel_that_shadows_nothing(roots: dict[str, Path]) -> None:
    """Deleting the only copy of a panel is a different request nobody made."""
    write_panel(roots["project"], "probe.only")
    discovery = _discover(roots)
    panel = discovery.get("probe.only")
    assert panel is not None
    with pytest.raises(PanelOverrideNotFoundError, match="shadows nothing"):
        revert_panel_override(panel, discovery)
    assert (roots["project"] / "probe.only").is_dir()


@pytest.mark.parametrize("tier_name", ["core", "package"])
def test_revert_refuses_a_read_only_tier(roots: dict[str, Path], tier_name: str) -> None:
    write_panel(roots[tier_name], "probe.ro")
    discovery = _discover(roots)
    panel = discovery.get("probe.ro")
    assert panel is not None
    with pytest.raises(PanelOverrideNotFoundError, match="holds no override"):
        revert_panel_override(panel, discovery)
    assert (roots[tier_name] / "probe.ro").is_dir()


# ---------------------------------------------------------------------------
# The write path's confinement, adversarially
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "panel_id",
    ["..", "../escape", "..\\escape", "/etc/panels", "C:/panels", "a/b", "", "."],
)
def test_a_panel_id_that_escapes_the_root_is_refused(tmp_path: Path, panel_id: str) -> None:
    """The one join the write path performs, refused before it happens."""
    root = tmp_path / "panels"
    root.mkdir()
    with pytest.raises(PanelEditError):
        confined_panel_directory(root, panel_id)


def test_a_confined_panel_id_resolves_under_the_root(tmp_path: Path) -> None:
    root = tmp_path / "panels"
    root.mkdir()
    assert confined_panel_directory(root, "core.plot.basic") == (root / "core.plot.basic").resolve()


def test_a_declaration_that_renames_the_panel_is_refused(roots: dict[str, Path]) -> None:
    """FR-027: a save that renamed the panel would leave the original visible.

    The edit would then look lost — the person saved, and the panel they were
    looking at did not change — so the id is pinned rather than trusted.
    """
    write_panel(roots["project"], "probe.rename")
    panel = _panel(roots, "probe.rename")
    renamed = json.dumps({**json.loads((panel.directory / "panel.json").read_text()), "panel_id": "probe.other"})

    with pytest.raises(PanelEditError, match="must keep the panel id"):
        save_panel_source(panel, DOCUMENT, project_panels_root=roots["project"], declaration=renamed)
    # Nothing was written: the refusal happens before the entry document is touched.
    assert (panel.directory / "index.html").read_text(encoding="utf-8") != DOCUMENT


def test_a_declaration_that_does_not_parse_is_refused(roots: dict[str, Path]) -> None:
    write_panel(roots["project"], "probe.badjson")
    panel = _panel(roots, "probe.badjson")
    with pytest.raises(PanelEditError, match="not valid JSON"):
        save_panel_source(panel, DOCUMENT, project_panels_root=roots["project"], declaration="{not json")
    with pytest.raises(PanelEditError, match="required field"):
        save_panel_source(
            panel,
            DOCUMENT,
            project_panels_root=roots["project"],
            declaration=json.dumps({"panel_id": "probe.badjson"}),
        )


def test_a_valid_declaration_is_written_beside_the_document(roots: dict[str, Path]) -> None:
    write_panel(roots["project"], "probe.decl")
    panel = _panel(roots, "probe.decl")
    body = json.loads((panel.directory / "panel.json").read_text(encoding="utf-8"))
    body["display_name"] = "Renamed For The Person"
    save_panel_source(panel, DOCUMENT, project_panels_root=roots["project"], declaration=json.dumps(body))

    written = json.loads((panel.directory / "panel.json").read_text(encoding="utf-8"))
    assert written["display_name"] == "Renamed For The Person"
    assert written["panel_id"] == "probe.decl"


def _with_entry(panel: DiscoveredPanel, entry: str) -> DiscoveredPanel:
    """Return *panel* with a forged ``entry``, bypassing discovery's own check.

    Discovery refuses a declaration whose entry document the directory does not
    contain, so these two cases cannot arrive through it. They are still tested:
    the write path must not *trust* the manifest it is handed, because a second
    caller could one day hand it one discovery never saw.
    """
    return DiscoveredPanel(
        manifest=replace(panel.manifest, entry=entry),
        tier=panel.tier,
        directory=panel.directory,
        root=panel.root,
    )


def test_an_entry_naming_a_file_outside_the_panel_directory_is_refused(roots: dict[str, Path]) -> None:
    """A declaration cannot make the write land somewhere else.

    ``entry`` is author-supplied, so it is confined to the panel's own directory
    the same way a served asset path is.
    """
    write_panel(roots["project"], "probe.escapeentry")
    panel = _with_entry(_panel(roots, "probe.escapeentry"), "../escaped.html")
    with pytest.raises(PanelEditError, match="outside its own directory"):
        save_panel_source(panel, DOCUMENT, project_panels_root=roots["project"])
    assert not (roots["project"] / "escaped.html").exists()


def test_an_entry_of_a_type_the_asset_route_refuses_is_refused(roots: dict[str, Path]) -> None:
    """A panel a person can save and then never load is not worth saving."""
    write_panel(roots["project"], "probe.badentry")
    panel = _with_entry(_panel(roots, "probe.badentry"), "panel.py")
    with pytest.raises(PanelEditError, match="not a file type the panel asset route serves"):
        save_panel_source(panel, DOCUMENT, project_panels_root=roots["project"])
    assert not (roots["project"] / "probe.badentry" / "panel.py").exists()


def test_an_oversized_document_is_refused_rather_than_stored(roots: dict[str, Path]) -> None:
    """The asset route would refuse to serve it, so storing it stores a dead panel."""
    from scistudio.panels import editing

    write_panel(roots["project"], "probe.huge")
    panel = _panel(roots, "probe.huge")
    with pytest.raises(PanelEditError, match="larger than"):
        save_panel_source(
            panel,
            "x" * (editing.MAX_PANEL_SOURCE_BYTES + 1),
            project_panels_root=roots["project"],
        )


def test_a_panel_resolving_outside_its_own_tier_root_is_refused(roots: dict[str, Path], tmp_path: Path) -> None:
    """The confinement is checked against the tier root, not assumed from it."""
    write_panel(roots["project"], "probe.outside")
    panel = _panel(roots, "probe.outside")
    forged = DiscoveredPanel(
        manifest=panel.manifest,
        tier=panel.tier,
        directory=tmp_path / "elsewhere" / "probe.outside",
        root=roots["project"],
    )
    with pytest.raises(PanelEditError, match="outside its tier root"):
        save_panel_source(forged, DOCUMENT, project_panels_root=roots["project"])


def test_a_symlinked_panel_directory_is_not_deleted_through(roots: dict[str, Path], tmp_path: Path) -> None:
    """Revert removes a directory; it must not remove one somewhere else."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    write_panel(elsewhere, "probe.link")
    write_panel(roots["core"], "probe.link")
    try:
        (roots["project"] / "probe.link").symlink_to(elsewhere / "probe.link", target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
        pytest.skip("this platform will not create a symlink without elevation")

    discovery = _discover(roots)
    panel = discovery.get("probe.link")
    assert panel is not None
    with pytest.raises(PanelEditError):
        revert_panel_override(panel, discovery)
    assert (elsewhere / "probe.link" / "index.html").is_file()


def test_the_copy_skips_a_symlink_rather_than_following_it(roots: dict[str, Path], tmp_path: Path) -> None:
    """Copy-on-write must not pull an arbitrary file into the project.

    Following the link would copy whatever it pointed at into a directory the
    asset route then serves.
    """
    outside = tmp_path / "outside.js"
    outside.write_text("stolen\n", encoding="utf-8")
    directory = write_panel(roots["core"], "probe.copylink")
    try:
        (directory / "linked.js").symlink_to(outside)
    except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
        pytest.skip("this platform will not create a symlink without elevation")

    save_panel_source(_panel(roots, "probe.copylink"), DOCUMENT, project_panels_root=roots["project"])
    assert not (roots["project"] / "probe.copylink" / "linked.js").exists()
    assert (roots["project"] / "probe.copylink" / "index.html").read_text(encoding="utf-8") == DOCUMENT
