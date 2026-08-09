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
    assert dropins.user_library_dir() not in {path.parent for path in dropins.type_scan_dirs(tutorial_project)}


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
    assert library not in {path.parent for path in dropins.type_scan_dirs(real_project)}
    assert library not in {path.parent for path in dropins.block_scan_dirs(real_project)}


def test_no_project_context_keeps_the_user_library(home: Path) -> None:
    """The swap needs a tutorial project; without one the user tier stands."""
    assert list(dropins.type_scan_dirs(None)) == [home / ".scistudio" / "types"]
    assert dropins.library_root_for_project(None) == dropins.user_library_dir()


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
