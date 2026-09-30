"""The forget step (ADR-056 FR-009, first half; spec NEW-014)."""

from __future__ import annotations

import importlib
import os
import py_compile
import sys
from pathlib import Path

from scistudio.core.user_code import (
    build_user_import_path,
    forget_user_modules,
    install_user_import_path,
    load_user_module,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_a_single_file_module_is_forgotten_and_its_bytecode_deleted(tmp_path: Path) -> None:
    source = _write(tmp_path / "types" / "scistudio_forget_single.py", "VALUE = 1\n")
    install_user_import_path([source.parent])
    module = importlib.import_module("scistudio_forget_single")
    cached = Path(importlib.util.cache_from_source(module.__file__))
    # The test run may set PYTHONDONTWRITEBYTECODE; write the cache explicitly.
    py_compile.compile(module.__file__, cfile=str(cached), doraise=True)
    assert cached.exists()

    forgotten = forget_user_modules()

    assert forgotten == ("scistudio_forget_single",)
    assert "scistudio_forget_single" not in sys.modules
    assert not cached.exists()


def test_a_package_is_forgotten_with_its_submodules(tmp_path: Path) -> None:
    package = tmp_path / "types" / "scistudio_forget_pkg"
    _write(package / "__init__.py", "from scistudio_forget_pkg.base import BASE\n")
    _write(package / "base.py", "BASE = 'old'\n")
    install_user_import_path([package.parent])
    assert importlib.import_module("scistudio_forget_pkg").BASE == "old"

    forgotten = forget_user_modules()

    assert forgotten == ("scistudio_forget_pkg", "scistudio_forget_pkg.base")
    _write(package / "base.py", "BASE = 'new'\n")
    assert importlib.import_module("scistudio_forget_pkg").BASE == "new"


def test_modules_outside_the_user_import_path_are_kept(tmp_path: Path) -> None:
    directory = tmp_path / "types"
    directory.mkdir()
    install_user_import_path([directory])

    forget_user_modules()

    assert "json" in sys.modules or importlib.import_module("json")
    assert "scistudio.core.user_code" in sys.modules


def test_after_a_project_switch_no_module_of_the_previous_project_resolves(tmp_path: Path) -> None:
    old_project = tmp_path / "old"
    new_project = tmp_path / "new"
    _write(old_project / "types" / "scistudio_switch_only_old.py", "WHO = 'old'\n")
    _write(old_project / "types" / "scistudio_switch_shared.py", "WHO = 'old'\n")
    _write(new_project / "types" / "scistudio_switch_shared.py", "WHO = 'new'\n")
    install_user_import_path(build_user_import_path(old_project))
    importlib.import_module("scistudio_switch_only_old")
    importlib.import_module("scistudio_switch_shared")

    # The drivers install the new path and then forget: the previous path is
    # still covered because the replaced entries are remembered.
    install_user_import_path(build_user_import_path(new_project))
    forgotten = forget_user_modules()

    assert set(forgotten) == {"scistudio_switch_only_old", "scistudio_switch_shared"}
    assert importlib.util.find_spec("scistudio_switch_only_old") is None
    assert importlib.import_module("scistudio_switch_shared").WHO == "new"


def test_an_edit_within_the_same_second_takes_effect(tmp_path: Path) -> None:
    source = _write(tmp_path / "blocks" / "scistudio_same_second.py", "VALUE = 'aaa'\n")
    install_user_import_path([source.parent])
    assert load_user_module("scistudio_same_second").module.VALUE == "aaa"
    # A cached .pyc of the first version, whatever PYTHONDONTWRITEBYTECODE says.
    py_compile.compile(str(source), cfile=importlib.util.cache_from_source(str(source)), doraise=True)
    stat = source.stat()

    # Same length, same whole-second mtime: CPython would accept the old .pyc.
    source.write_text("VALUE = 'bbb'\n", encoding="utf-8")
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    forget_user_modules()

    loaded = load_user_module("scistudio_same_second")
    assert loaded.module.VALUE == "bbb"
    assert loaded.mtime_ns == stat.st_mtime_ns


def test_extra_dirs_are_forgotten_too(tmp_path: Path) -> None:
    directory = tmp_path / "elsewhere"
    _write(directory / "scistudio_forget_extra.py", "VALUE = 1\n")
    sys.path.append(str(directory))
    try:
        importlib.import_module("scistudio_forget_extra")
        assert forget_user_modules(extra_dirs=[directory]) == ("scistudio_forget_extra",)
    finally:
        sys.path.remove(str(directory))
