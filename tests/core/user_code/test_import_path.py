"""The user import path (ADR-056 FR-001, FR-012; spec NEW-011)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scistudio.core.user_code import (
    USER_IMPORT_PATH_ENV_VAR,
    build_user_import_path,
    ensure_user_import_path,
    install_user_import_path,
    install_user_import_path_from_env,
    installed_user_import_path,
    parse_user_import_path,
    serialise_user_import_path,
    user_import_path_env,
    user_import_path_from_env,
)


@pytest.fixture()
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def _mkdirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def test_order_is_entry_project_types_project_blocks_library_types_library_blocks(home: Path, tmp_path: Path) -> None:
    project = tmp_path / "project"
    entry = project / "panels" / "viewer"
    library = home / ".scistudio"
    _mkdirs(entry, project / "types", project / "blocks", library / "types", library / "blocks")

    path = build_user_import_path(project, entry_folder=entry)

    assert path == (
        entry.resolve(),
        (project / "types").resolve(),
        (project / "blocks").resolve(),
        (library / "types").resolve(),
        (library / "blocks").resolve(),
    )


def test_missing_directories_contribute_no_entry(home: Path, tmp_path: Path) -> None:
    project = tmp_path / "project"
    _mkdirs(project / "blocks", home / ".scistudio" / "types")

    assert build_user_import_path(project) == (
        (project / "blocks").resolve(),
        (home / ".scistudio" / "types").resolve(),
    )
    assert build_user_import_path(None, entry_folder=tmp_path / "absent") == (
        (home / ".scistudio" / "types").resolve(),
    )


def test_tutorial_project_uses_the_tutorial_scoped_library(home: Path) -> None:
    tutorial_project = home / "SciStudio Tutorials" / "what-is-a-type"
    scoped = home / "SciStudio Tutorials" / ".library"
    _mkdirs(tutorial_project / "types", scoped / "types", home / ".scistudio" / "types")

    path = build_user_import_path(tutorial_project)

    assert path == ((tutorial_project / "types").resolve(), (scoped / "types").resolve())


def test_install_appends_after_everything_already_on_sys_path(tmp_path: Path) -> None:
    first, second = tmp_path / "types", tmp_path / "blocks"
    _mkdirs(first, second)
    before = list(sys.path)

    installed = install_user_import_path([first, second])

    assert installed == (first.resolve(), second.resolve())
    assert sys.path[: len(before)] == before
    assert sys.path[-2:] == [str(first.resolve()), str(second.resolve())]
    assert installed_user_import_path() == installed


def test_install_replaces_the_previous_project(tmp_path: Path) -> None:
    old = tmp_path / "old" / "types"
    new = tmp_path / "new" / "types"
    _mkdirs(old, new)
    install_user_import_path([old])

    install_user_import_path([new])

    assert str(old.resolve()) not in sys.path
    assert sys.path[-1] == str(new.resolve())
    assert installed_user_import_path() == (new.resolve(),)


def test_an_entry_already_on_sys_path_moves_to_the_end(tmp_path: Path) -> None:
    directory = tmp_path / "types"
    directory.mkdir()
    sys.path.insert(0, str(directory.resolve()))
    try:
        install_user_import_path([directory])
        assert sys.path.count(str(directory.resolve())) == 1
        assert sys.path[-1] == str(directory.resolve())
    finally:
        install_user_import_path(())
    assert str(directory.resolve()) not in sys.path


def test_ensure_adds_a_tier_in_fr001_order_and_keeps_installed_entries(tmp_path: Path) -> None:
    installed = tmp_path / "entry"
    tier = tmp_path / "project"
    _mkdirs(installed, tier / "types", tier / "blocks")
    install_user_import_path([installed])

    result = ensure_user_import_path([tier / "blocks"])

    assert result == (installed.resolve(), (tier / "types").resolve(), (tier / "blocks").resolve())
    assert ensure_user_import_path([tier / "types"]) == result


def test_serialised_path_round_trips_through_the_child_environment(tmp_path: Path) -> None:
    dirs = [tmp_path / "a b", tmp_path / "c:d"]
    _mkdirs(*dirs)

    env = user_import_path_env(dirs)

    assert set(env) == {USER_IMPORT_PATH_ENV_VAR}
    assert user_import_path_from_env(env) == tuple(dirs)
    assert parse_user_import_path(serialise_user_import_path(dirs)) == tuple(dirs)
    assert install_user_import_path_from_env(env) == tuple(path.resolve() for path in dirs)
    assert sys.path[-2:] == [str(path.resolve()) for path in dirs]


@pytest.mark.parametrize("raw", ["", "not json", "{}", '["", 3]'])
def test_malformed_environment_values_yield_no_directories(raw: str) -> None:
    assert parse_user_import_path(raw) == ()


def test_an_absent_variable_installs_nothing(tmp_path: Path) -> None:
    directory = tmp_path / "types"
    directory.mkdir()
    install_user_import_path([directory])

    assert install_user_import_path_from_env({}) == (directory.resolve(),)
