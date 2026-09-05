"""The tutorial-scoped library — a teaching tier real projects never see.

``docs/specs/adr-053-learning-center.md`` FR-070 to FR-073. One designed
scenario has the user save a custom type to My Library so the next scenario can
reuse it. Without an isolated library that would deposit a teaching type into
every real project the user opened afterwards, which is the reason the swap
exists rather than a convenience.

The mechanism is one root, not a fourth tier: a project under
``~/SciStudio Tutorials`` resolves its user tier to ``.library`` where a real
project resolves it to ``~/.scistudio``
(:func:`scistudio.core.dropins.library_root_for_project`). These tests hold both
halves — that the tutorial project sees it and that the real project does not —
plus the clearing that removes it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.core import dropins
from scistudio.tutorials import projects as tutorial_projects

_TEACHING_TYPE_SOURCE = """from scistudio.core.types.base import DataObject


class TeachingType(DataObject):
    \"\"\"A type saved to the library during a tutorial.\"\"\"
"""

_TEACHING_PANEL_SOURCE = """from scistudio.panels.models import OwnerKind, PanelSpec


def get_previewers():
    return [
        PanelSpec(
            previewer_id="tutorial.image.viewer",
            owner_kind=OwnerKind.USER,
            owner_name="tutorial-library",
            target_type="Image",
        )
    ]
"""

_PROJECT_PANEL_SOURCE = """from scistudio.panels.models import OwnerKind, PanelSpec


def get_previewers():
    return [
        PanelSpec(
            previewer_id="project.image.viewer",
            owner_kind=OwnerKind.PROJECT,
            owner_name="tutorial-project",
            target_type="Image",
        )
    ]
"""


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``Path.home()`` at an isolated directory."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return fake_home


@pytest.fixture
def tutorial_project(home: Path) -> Path:
    """A tutorial project directory under the tutorial parent."""
    path = tutorial_projects.tutorial_project_path(tutorial_projects.TutorialKey.core("welcome"))
    (path / "types").mkdir(parents=True)
    (path / "blocks").mkdir(parents=True)
    return path


@pytest.fixture
def real_project(tmp_path: Path) -> Path:
    """A user project stored outside the tutorial parent."""
    path = tmp_path / "my-analysis"
    (path / "types").mkdir(parents=True)
    (path / "blocks").mkdir(parents=True)
    return path


# ---------------------------------------------------------------------------
# FR-070 / FR-071 — the swap, and its one-sidedness
# ---------------------------------------------------------------------------


def test_tutorial_project_scans_the_scoped_library_in_place_of_the_user_one(home: Path, tutorial_project: Path) -> None:
    """FR-070: the user tier of a tutorial project is ``.library``."""
    library = dropins.tutorial_library_dir()

    assert list(dropins.block_scan_dirs(tutorial_project)) == [tutorial_project / "blocks", library / "blocks"]
    assert list(dropins.type_scan_dirs(tutorial_project)) == [tutorial_project / "types", library / "types"]
    assert list(dropins.panel_scan_dirs(tutorial_project)) == [
        tutorial_project / "previewers",
        library / "previewers",
    ]
    assert dropins.user_library_dir() not in {path.parent for path in dropins.type_scan_dirs(tutorial_project)}
    assert dropins.user_library_dir() not in {path.parent for path in dropins.panel_scan_dirs(tutorial_project)}


def test_real_project_never_scans_the_scoped_library(home: Path, real_project: Path) -> None:
    """FR-071: the swap is one-sided."""
    library = dropins.tutorial_library_dir()

    assert list(dropins.block_scan_dirs(real_project)) == [
        real_project / "blocks",
        home / ".scistudio" / "blocks",
    ]
    assert list(dropins.type_scan_dirs(real_project)) == [
        real_project / "types",
        home / ".scistudio" / "types",
    ]
    assert list(dropins.panel_scan_dirs(real_project)) == [
        real_project / "previewers",
        home / ".scistudio" / "previewers",
    ]
    assert library not in {path.parent for path in dropins.type_scan_dirs(real_project)}
    assert library not in {path.parent for path in dropins.block_scan_dirs(real_project)}
    assert library not in {path.parent for path in dropins.panel_scan_dirs(real_project)}


def test_no_project_context_keeps_the_user_library(home: Path) -> None:
    """The swap needs a tutorial project; without one the user tier stands."""
    assert list(dropins.type_scan_dirs(None)) == [home / ".scistudio" / "types"]
    assert list(dropins.panel_scan_dirs(None)) == [home / ".scistudio" / "previewers"]
    assert dropins.library_root_for_project(None) == dropins.user_library_dir()


def test_the_scoped_library_carries_all_three_tiers(home: Path) -> None:
    """FR-070 names ``blocks/``, ``types/``, and ``previewers/`` (#2086).

    Eager creation matters for the same reason it does for the other two: the
    save-to-library action a tutorial teaches has to land somewhere, and a step
    that fails on a missing directory teaches the wrong lesson.
    """
    root = tutorial_projects.ensure_scoped_library()

    assert [path.name for path in tutorial_projects.scoped_library_dirs()] == ["blocks", "types", "previewers"]
    assert (root / "previewers").is_dir()


def test_a_teaching_type_resolves_inside_the_tutorial_and_nowhere_else(
    home: Path, tutorial_project: Path, real_project: Path
) -> None:
    """FR-070/FR-071 behaviourally: the registry answers differently.

    The directory lists above are the mechanism; this is the consequence the
    scenario depends on. A type saved to the library during a tutorial is
    resolvable by the next tutorial and invisible to the user's own project.
    """
    from scistudio.core.types.registry import TypeRegistry

    library_types = dropins.tutorial_library_dir() / "types"
    library_types.mkdir(parents=True)
    (library_types / "teaching_type.py").write_text(_TEACHING_TYPE_SOURCE, encoding="utf-8")

    def _resolved(project_dir: Path) -> bool:
        registry = TypeRegistry()
        dropins.register_type_scan_dirs(registry, project_dir)
        registry.scan_builtins()
        registry._scan_filesystem_dirs()
        try:
            registry.resolve("TeachingType")
        except Exception:
            return False
        return True

    assert _resolved(tutorial_project) is True
    assert _resolved(real_project) is False


def test_a_teaching_panel_registers_inside_the_tutorial_and_nowhere_else(
    home: Path, tutorial_project: Path, real_project: Path
) -> None:
    """FR-070/FR-071 for the third kind (#2086), behaviourally.

    The panel a tutorial saves must be resolvable by the next tutorial
    project — that reuse is the levels' teaching spine — and invisible to the
    user's own projects, exactly as the teaching type above.
    """
    from scistudio.panels.project import load_user_panels
    from scistudio.panels.registry import PanelRegistry

    library_panels = dropins.tutorial_library_dir() / "previewers"
    library_panels.mkdir(parents=True)
    (library_panels / "teaching_image_panel.py").write_text(_TEACHING_PANEL_SOURCE, encoding="utf-8")

    def _registered(project_dir: Path | None) -> set[str]:
        registry = PanelRegistry()
        load_user_panels(registry, project_dir)
        return {spec.previewer_id for spec in registry.all_specs()}

    assert "tutorial.image.viewer" in _registered(tutorial_project)
    assert "tutorial.image.viewer" not in _registered(real_project)
    assert "tutorial.image.viewer" not in _registered(None)


def test_a_scoped_library_panel_rides_the_user_tier_and_the_project_tier_still_wins(
    home: Path, tutorial_project: Path
) -> None:
    """#2086's shape claim: the swap is a root, not a fourth tier.

    A scoped-library panel registers as ``OwnerKind.USER`` — the entry the
    panel listing reports as the user tier while a tutorial project is
    open — so routing precedence stays project > user > package > core with
    nothing new in the ladder. Both halves are held: the scoped panel wins
    for its type, and a project panel for the same type shadows it.
    """
    from scistudio.panels.models import OwnerKind, PreviewTarget, TargetKind
    from scistudio.panels.project import load_project_panels, load_user_panels
    from scistudio.panels.registry import PanelRegistry
    from scistudio.panels.router import PreviewRouter

    library_panels = dropins.tutorial_library_dir() / "previewers"
    library_panels.mkdir(parents=True)
    (library_panels / "teaching_image_panel.py").write_text(_TEACHING_PANEL_SOURCE, encoding="utf-8")
    target = PreviewTarget(kind=TargetKind.DATA_REF, ref="r", recorded_type="Image", type_chain=("Image",))

    registry = PanelRegistry()
    load_project_panels(registry, tutorial_project)
    load_user_panels(registry, tutorial_project)

    scoped = registry.get("tutorial.image.viewer")
    assert scoped is not None
    assert scoped.owner_kind is OwnerKind.USER
    assert PreviewRouter(registry).resolve(target).previewer_id == "tutorial.image.viewer"

    (tutorial_project / "previewers").mkdir()
    (tutorial_project / "previewers" / "project_image_panel.py").write_text(_PROJECT_PANEL_SOURCE, encoding="utf-8")
    shadowing = PanelRegistry()
    load_project_panels(shadowing, tutorial_project)
    load_user_panels(shadowing, tutorial_project)

    assert PreviewRouter(shadowing).resolve(target).previewer_id == "project.image.viewer"


def test_import_roots_carry_the_swap(home: Path, tutorial_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-071 holds for module resolution, not only for registration.

    A teaching type has to be importable by a drop-in block inside the tutorial
    and by nothing outside it, so the ``sys.path`` roots swap with the scan dirs
    rather than staying pinned to ``~/.scistudio``.
    """
    monkeypatch.setattr(dropins, "user_python_import_roots", tuple)

    assert list(dropins.dropin_import_roots(tutorial_project)) == [
        tutorial_project / "types",
        dropins.tutorial_library_dir() / "types",
    ]
    # And the same answer when the caller holds block dirs instead.
    assert list(dropins.dropin_type_roots_for_block_dirs(dropins.block_scan_dirs(tutorial_project))) == [
        tutorial_project / "types",
        dropins.tutorial_library_dir() / "types",
    ]


def test_the_scoped_library_is_still_guarded_against_shadowing(home: Path, tutorial_project: Path) -> None:
    """FR-016 does not lapse inside a tutorial.

    ``guard_dropin_type_roots`` selects roots by the ``types`` directory name,
    and the scoped library keeps the tier shape, so a teaching type called
    ``json`` is refused there exactly as it would be in the user's own library.
    """
    library_types = dropins.tutorial_library_dir() / "types"
    library_types.mkdir(parents=True)
    (library_types / "json.py").write_text("X = 1\n", encoding="utf-8")

    collisions = dropins.guard_dropin_type_roots(dropins.type_scan_dirs(tutorial_project), bind=False)

    assert [collision.stem for collision in collisions] == ["json"]


# ---------------------------------------------------------------------------
# FR-016 / FR-031 — the tutorial drop-in tier
# ---------------------------------------------------------------------------


def test_tutorial_tier_resolves_the_same_two_tiers_as_blocks_and_types(home: Path, real_project: Path) -> None:
    """FR-016: user and project tutorial sources, one tier definition."""
    assert list(dropins.tutorial_scan_dirs(real_project)) == [
        real_project / "tutorials",
        home / ".scistudio" / "tutorials",
    ]
    assert dropins.user_tutorials_dir() == home / ".scistudio" / "tutorials"
    assert dropins.project_tutorials_dir(real_project) == real_project / "tutorials"


def test_tutorial_tier_keeps_the_user_tutorials_dir_inside_a_tutorial(home: Path, tutorial_project: Path) -> None:
    """The library swap must not reach the tutorial *source* tier.

    The user's own tutorials live in ``~/.scistudio/tutorials`` and have to stay
    listed while a tutorial is running; swapping this tier the way the library
    tier swaps would empty the user group from the catalogue for the duration.
    """
    assert list(dropins.tutorial_scan_dirs(tutorial_project)) == [
        tutorial_project / "tutorials",
        home / ".scistudio" / "tutorials",
    ]


def test_tutorial_tier_is_not_an_import_root(home: Path, real_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-020a: a tutorial directory claims no top-level module name.

    A ``.py`` beside a manifest in ``{project}/tutorials`` would be importable
    if the tier joined ``sys.path``, which is exactly the exposure the tier
    grading closes. Discovery reads those directories as files instead.
    """
    monkeypatch.setattr(dropins, "user_python_import_roots", tuple)

    roots = set(dropins.dropin_import_roots(real_project))

    assert real_project / "tutorials" not in roots
    assert dropins.user_tutorials_dir() not in roots


# ---------------------------------------------------------------------------
# FR-073 — clearing removes the library with the projects
# ---------------------------------------------------------------------------


def test_clearing_removes_the_scoped_library_and_the_projects(home: Path, tutorial_project: Path) -> None:
    """FR-073: no orphaned teaching types survive clearing."""
    library = tutorial_projects.ensure_scoped_library()
    (library / "types" / "teaching_type.py").write_text(_TEACHING_TYPE_SOURCE, encoding="utf-8")
    assert tutorial_project.is_dir()

    preview = tutorial_projects.clear_preview()
    assert set(preview) == {tutorial_project, library}
    # The library is named last: the projects are what the user thinks they are
    # clearing, and the library is the part the confirmation has to disclose.
    assert preview[-1] == library

    deleted = tutorial_projects.clear_tutorial_data()

    assert set(deleted) == {tutorial_project, library}
    assert not tutorial_project.exists()
    assert not library.exists()
    # The parent stays, empty, ready for the next bootstrap.
    assert dropins.tutorial_parent_dir().is_dir()
    assert list(dropins.tutorial_parent_dir().iterdir()) == []


def test_clearing_leaves_the_user_library_alone(home: Path, tutorial_project: Path) -> None:
    """FR-073 must not reach ``~/.scistudio``.

    The two libraries have the same shape and differ only by root, which is
    exactly the confusion clearing has to avoid making.
    """
    user_types = dropins.user_types_dir()
    user_types.mkdir(parents=True)
    (user_types / "my_own_type.py").write_text(_TEACHING_TYPE_SOURCE, encoding="utf-8")
    tutorial_projects.ensure_scoped_library()

    tutorial_projects.clear_tutorial_data()

    assert (user_types / "my_own_type.py").is_file()


def test_clearing_refuses_a_directory_outside_the_tutorial_parent(home: Path, real_project: Path) -> None:
    """FR-073's promise is enforced at the delete, not at the caller.

    Every deleting entry point in the module checks containment, so no argument
    can make it remove a user project.
    """
    with pytest.raises(ValueError, match="not inside"):
        tutorial_projects.delete_tutorial_project(real_project)

    assert real_project.is_dir()


def test_clearing_an_empty_machine_is_a_no_op(home: Path) -> None:
    """Nothing to clear reports nothing cleared, rather than failing."""
    assert tutorial_projects.clear_preview() == ()
    assert tutorial_projects.clear_tutorial_data() == ()
