"""The name check before import (ADR-056 FR-008; spec NEW-012)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from scistudio.core.user_code import check_user_import_path, install_user_import_path
from scistudio.core.user_code.names import CONFLICT, INSTALLED, STDLIB


def _write(path: Path, text: str = "VALUE = 1\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture()
def tiers(tmp_path: Path) -> dict[str, Path]:
    dirs = {
        "project_types": tmp_path / "project" / "types",
        "project_blocks": tmp_path / "project" / "blocks",
        "library_types": tmp_path / "library" / "types",
        "library_blocks": tmp_path / "library" / "blocks",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True)
    return dirs


def _by_path(refusals: tuple) -> dict[Path, object]:
    return {refusal.path: refusal for refusal in refusals}


def test_a_standard_library_stem_is_refused_with_a_rename_message(tiers: dict[str, Path]) -> None:
    refused = _write(tiers["project_blocks"] / "json.py").resolve()

    refusals = _by_path(check_user_import_path(tiers.values()))

    assert refusals[refused].reason == STDLIB
    assert "Rename it" in refusals[refused].message
    assert refusals[refused].error_type == "UserModuleNameCollision"


def test_an_installed_package_stem_is_refused_and_still_resolves_to_the_package(tiers: dict[str, Path]) -> None:
    refused = _write(tiers["project_types"] / "numpy.py").resolve()
    install_user_import_path(tiers.values())

    refusals = _by_path(check_user_import_path(tiers.values()))

    assert refusals[refused].reason == INSTALLED
    assert "numpy" in refusals[refused].detail
    module = importlib.import_module("numpy")
    assert Path(module.__file__).resolve().parent != tiers["project_types"].resolve()


def test_a_package_directory_counts_as_a_stem(tiers: dict[str, Path]) -> None:
    package = tiers["library_types"] / "collections"
    _write(package / "__init__.py")
    _write(tiers["library_types"] / "namespace_only" / "module.py")

    refusals = _by_path(check_user_import_path(tiers.values()))

    assert refusals[package.resolve()].reason == STDLIB
    assert all(path.name != "namespace_only" for path in refusals)


def test_same_tier_duplicate_across_types_and_blocks_refuses_every_file(tiers: dict[str, Path]) -> None:
    in_types = _write(tiers["project_types"] / "scistudio_util_dup.py").resolve()
    in_blocks = _write(tiers["project_blocks"] / "scistudio_util_dup.py").resolve()

    refusals = _by_path(check_user_import_path(tiers.values()))

    assert refusals[in_types].reason == CONFLICT
    assert refusals[in_blocks].reason == CONFLICT
    assert "blocks/scistudio_util_dup.py" in refusals[in_types].message
    assert refusals[in_blocks].error_type == "UserModuleNameConflict"


def test_cross_tier_same_stem_is_not_refused_and_the_project_file_wins(tiers: dict[str, Path]) -> None:
    project_file = _write(tiers["project_types"] / "scistudio_shared_stem.py", "WHERE = 'project'\n")
    _write(tiers["library_types"] / "scistudio_shared_stem.py", "WHERE = 'library'\n")
    install_user_import_path(tiers.values())

    assert check_user_import_path(tiers.values()) == ()
    module = importlib.import_module("scistudio_shared_stem")
    assert module.WHERE == "project"
    assert Path(module.__file__).resolve() == project_file.resolve()


def test_an_imported_user_module_is_not_mistaken_for_an_installed_one(tiers: dict[str, Path]) -> None:
    _write(tiers["project_blocks"] / "scistudio_already_loaded.py")
    install_user_import_path(tiers.values())
    importlib.import_module("scistudio_already_loaded")
    assert "scistudio_already_loaded" in sys.modules

    assert check_user_import_path(tiers.values()) == ()


def test_the_check_imports_nothing_and_installs_no_finder(tiers: dict[str, Path]) -> None:
    _write(tiers["project_types"] / "scistudio_never_imported.py", "raise RuntimeError('imported')\n")
    _write(tiers["project_blocks"] / "json.py")
    meta_path = list(sys.meta_path)

    check_user_import_path(tiers.values())

    assert "scistudio_never_imported" not in sys.modules
    assert sys.meta_path == meta_path
